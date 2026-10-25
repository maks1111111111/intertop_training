"""Tests for deterministic visual source preparation without provider calls."""

from __future__ import annotations

import io
import unittest
from pathlib import Path
from typing import Union

from PIL import Image

from app.ai.visual_analysis_interfaces import MAX_VISUAL_INPUT_BYTES
from app.content.importer import CourseImporter
from app.content.source_document import (
    SourceBoundary,
    SourceDocument,
    SourceImage,
    SourceProvenance,
    build_source_image,
)
from app.content.vector_image_renderer import VectorImageRenderError
from app.content.visual_source_analyzer import VisualSourceAnalyzer
from app.content.visual_enrichment import VisualInputTransform, compute_content_hash


def _image_bytes(
    *,
    size: tuple[int, int] = (640, 360),
    color: tuple[int, int, int] = (20, 80, 140),
    image_format: str = "PNG",
) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", size=size, color=color).save(output, format=image_format)
    return output.getvalue()


def _source_with_images(
    contents: tuple[bytes, ...], *, name: str = "guide.pdf"
) -> SourceDocument:
    images = tuple(
        build_source_image(
            document=name,
            content=content,
            provenance=SourceProvenance(
                document=name,
                order=index,
                position=index,
                page=index,
            ),
        )
        for index, content in enumerate(contents, start=1)
    )
    return SourceDocument(name=name, source_format="pdf", elements=images)


def _wmf_bytes(payload: bytes = b"vector") -> bytes:
    """Minimal placeable-WMF signature for controlled analyzer tests."""
    return b"\xd7\xcd\xc6\x9a" + payload


class _FakeVectorRenderer:
    def __init__(self, result: Union[bytes, VectorImageRenderError]) -> None:
        self.result = result
        self.calls: list[tuple[bytes, str]] = []

    def render_png(self, content: bytes, *, source_format: str) -> bytes:
        self.calls.append((content, source_format))
        if isinstance(self.result, VectorImageRenderError):
            raise self.result
        return self.result


class VisualSourceAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analyzer = VisualSourceAnalyzer()

    def test_supported_source_image_is_selected_unchanged(self) -> None:
        content = _image_bytes()
        source = _source_with_images((content,))

        result = self.analyzer.prepare(source)

        self.assertEqual(len(result.requests), 1)
        item = result.requests[0].inputs[0]
        self.assertEqual(item.content, content)
        self.assertIsNone(item.transform)
        self.assertEqual(item.source_content_hash, compute_content_hash(content))
        self.assertEqual(item.input_content_hash, item.source_content_hash)
        self.assertLessEqual(len(item.content), MAX_VISUAL_INPUT_BYTES)

    def test_exact_duplicate_bytes_preserve_first_source_occurrence(self) -> None:
        content = _image_bytes()
        source = _source_with_images((content, content))

        result = self.analyzer.prepare(source)

        first, second = source.elements
        self.assertEqual(result.requests[0].inputs[0].source_asset_id, first.asset_id)
        self.assertEqual(len(result.skipped), 1)
        self.assertEqual(result.skipped[0].code, "duplicate_content")
        self.assertEqual(result.skipped[0].source_asset_id, second.asset_id)
        self.assertEqual(result.skipped[0].canonical_source_asset_id, first.asset_id)

    def test_unsupported_image_is_skipped(self) -> None:
        source = _source_with_images((_image_bytes(image_format="GIF"),))

        result = self.analyzer.prepare(source)

        self.assertEqual(result.requests, ())
        self.assertEqual(result.skipped[0].code, "unsupported_media_type")

    def test_corrupt_image_does_not_abort_preparation(self) -> None:
        provenance = SourceProvenance(document="guide.pdf", order=1, position=1, page=1)
        source = SourceDocument(
            name="guide.pdf",
            source_format="pdf",
            elements=(
                SourceImage(
                    asset_id="source-corrupt",
                    content=b"not-an-image",
                    media_type="image/png",
                    extension=".png",
                    provenance=provenance,
                ),
            ),
        )

        result = self.analyzer.prepare(source)

        self.assertEqual(result.requests, ())
        self.assertEqual(result.skipped[0].code, "corrupt_image")

    def test_tiny_decorative_image_is_filtered_conservatively(self) -> None:
        source = _source_with_images((_image_bytes(size=(40, 40)),))

        result = self.analyzer.prepare(source)

        self.assertEqual(result.requests, ())
        self.assertEqual(result.skipped[0].code, "tiny_image")

    def test_screenshot_sized_image_is_not_filtered_as_decorative(self) -> None:
        source = _source_with_images((_image_bytes(size=(100, 80)),))

        result = self.analyzer.prepare(source)

        self.assertEqual(len(result.requests[0].inputs), 1)
        self.assertEqual(result.skipped, ())

    def test_contain_resize_never_upscales_and_preserves_source_identity(self) -> None:
        content = _image_bytes(size=(5000, 100))
        source = _source_with_images((content,))

        result = self.analyzer.prepare(source)

        item = result.requests[0].inputs[0]
        with Image.open(io.BytesIO(item.content)) as prepared:
            self.assertLessEqual(max(prepared.size), 4096)
            self.assertLessEqual(prepared.size[0], 5000)
            self.assertLessEqual(prepared.size[1], 100)
        self.assertIsNotNone(item.transform)
        self.assertEqual(item.source_content_hash, compute_content_hash(content))
        self.assertNotEqual(item.input_content_hash, item.source_content_hash)

    def test_original_source_image_bytes_are_unchanged(self) -> None:
        content = _image_bytes(size=(5000, 100))
        source = _source_with_images((content,))
        original_hash = compute_content_hash(source.elements[0].content)

        self.analyzer.prepare(source)

        self.assertEqual(source.elements[0].content, content)
        self.assertEqual(compute_content_hash(source.elements[0].content), original_hash)

    def test_selected_inputs_are_batched_in_source_order(self) -> None:
        source = _source_with_images(
            tuple(_image_bytes(color=(index, 10, 20)) for index in range(17))
        )

        result = self.analyzer.prepare(source)
        prepared_ids = tuple(
            item.source_asset_id for request in result.requests for item in request.inputs
        )
        source_ids = tuple(image.asset_id for image in source.elements)

        self.assertEqual(tuple(len(request.inputs) for request in result.requests), (16, 1))
        self.assertEqual(prepared_ids, source_ids)
        self.assertEqual(result.selected_visual_ids, tuple(
            item.visual_id for request in result.requests for item in request.inputs
        ))

    def test_preparation_is_byte_identical_and_deterministic(self) -> None:
        source = _source_with_images(
            (_image_bytes(size=(5000, 100)), _image_bytes(color=(100, 10, 20)))
        )

        first = self.analyzer.prepare(source)
        second = self.analyzer.prepare(source)

        self.assertEqual(first, second)

    def test_page_and_slide_render_are_explicitly_unavailable(self) -> None:
        page_source = SourceDocument(
            name="guide.pdf",
            source_format="pdf",
            elements=(
                SourceBoundary(
                    "page_break",
                    SourceProvenance("guide.pdf", 1, 0, page=1),
                ),
            ),
        )
        slide_source = SourceDocument(
            name="guide.pptx",
            source_format="pptx",
            elements=(
                SourceBoundary(
                    "slide_boundary",
                    SourceProvenance("guide.pptx", 1, 0, slide=1),
                ),
            ),
        )

        page_result = self.analyzer.prepare(page_source)
        slide_result = self.analyzer.prepare(slide_source)

        self.assertEqual(page_result.requests, ())
        self.assertEqual(slide_result.requests, ())
        self.assertEqual(page_result.limitations[0].code, "unsupported_format")
        self.assertEqual(slide_result.limitations[0].code, "unsupported_format")

    def test_legacy_import_path_does_not_call_visual_source_analyzer(self) -> None:
        reader = _LegacyReader()

        result = CourseImporter(readers={"pdf": reader}).read_source(Path("guide.pdf"))

        self.assertEqual(result, "legacy source text")
        self.assertEqual(reader.read_document_calls, 0)

    def test_wmf_is_converted_only_for_provider_input(self) -> None:
        original = _wmf_bytes(b"cashier-screen")
        provenance = SourceProvenance("guide.docx", 1, 1)
        source_image = SourceImage(
            asset_id="source-vector",
            content=original,
            media_type=None,
            extension=None,
            provenance=provenance,
        )
        source = SourceDocument("guide.docx", "docx", (source_image,))
        rendered = _image_bytes(size=(794, 1123))
        renderer = _FakeVectorRenderer(rendered)

        result = VisualSourceAnalyzer(vector_renderer=renderer).prepare(source)

        self.assertEqual(renderer.calls, [(original, "wmf")])
        item = result.requests[0].inputs[0]
        self.assertEqual(item.content, rendered)
        self.assertEqual(item.media_type, "image/png")
        self.assertEqual(item.source_content_hash, compute_content_hash(original))
        self.assertEqual(item.input_content_hash, compute_content_hash(rendered))
        self.assertNotEqual(item.source_content_hash, item.input_content_hash)
        self.assertEqual(
            item.transform,
            VisualInputTransform(2, "none", None, "image/png", "wmf_to_png"),
        )
        self.assertEqual(source_image.content, original)
        self.assertEqual(result.skipped, ())

    def test_wmf_without_opt_in_renderer_is_typed_skip(self) -> None:
        original = _wmf_bytes()
        source = SourceDocument(
            "guide.docx",
            "docx",
            (
                SourceImage(
                    "source-vector", original, None, None,
                    SourceProvenance("guide.docx", 1, 1),
                ),
            ),
        )

        result = self.analyzer.prepare(source)

        self.assertEqual(result.requests, ())
        self.assertEqual(result.skipped[0].code, "renderer_unavailable")

    def test_exact_duplicate_vector_bytes_are_deduplicated_before_renderer(self) -> None:
        original = _wmf_bytes()
        source = SourceDocument(
            "guide.docx",
            "docx",
            tuple(
                SourceImage(
                    f"source-vector-{index}", original, None, None,
                    SourceProvenance("guide.docx", index, index),
                )
                for index in (1, 2)
            ),
        )
        renderer = _FakeVectorRenderer(_image_bytes())

        result = VisualSourceAnalyzer(vector_renderer=renderer).prepare(source)

        self.assertEqual(len(renderer.calls), 1)
        self.assertEqual(result.skipped[0].code, "duplicate_content")
        self.assertEqual(result.skipped[0].canonical_source_asset_id, "source-vector-1")

    def test_vector_renderer_failure_codes_become_typed_skips(self) -> None:
        source = SourceDocument(
            "guide.docx",
            "docx",
            (
                SourceImage(
                    "source-vector", _wmf_bytes(), None, None,
                    SourceProvenance("guide.docx", 1, 1),
                ),
            ),
        )
        for code in (
            "renderer_timeout",
            "malformed_vector",
            "rendered_output_invalid",
            "rendered_output_too_large",
            "rendered_dimensions_exceeded",
            "renderer_isolation_unavailable",
        ):
            with self.subTest(code=code):
                result = VisualSourceAnalyzer(
                    vector_renderer=_FakeVectorRenderer(VectorImageRenderError(code))
                ).prepare(source)
                self.assertEqual(result.requests, ())
                self.assertEqual(result.skipped[0].code, code)

    def test_invalid_or_oversized_vector_renderer_output_is_typed_skip(self) -> None:
        source = SourceDocument(
            "guide.docx",
            "docx",
            (
                SourceImage(
                    "source-vector", _wmf_bytes(), None, None,
                    SourceProvenance("guide.docx", 1, 1),
                ),
            ),
        )
        cases = (
            (b"not a PNG", "rendered_output_invalid"),
            (b"x" * (MAX_VISUAL_INPUT_BYTES + 1), "rendered_output_too_large"),
        )
        for rendered, reason in cases:
            with self.subTest(reason=reason):
                result = VisualSourceAnalyzer(
                    vector_renderer=_FakeVectorRenderer(rendered)
                ).prepare(source)
                self.assertEqual(result.requests, ())
                self.assertEqual(result.skipped[0].code, reason)

    def test_vector_render_with_excessive_dimensions_is_typed_skip(self) -> None:
        source = SourceDocument(
            "guide.docx",
            "docx",
            (
                SourceImage(
                    "source-vector", _wmf_bytes(), None, None,
                    SourceProvenance("guide.docx", 1, 1),
                ),
            ),
        )

        result = VisualSourceAnalyzer(
            vector_renderer=_FakeVectorRenderer(_image_bytes(size=(5000, 100)))
        ).prepare(source)

        self.assertEqual(result.requests, ())
        self.assertEqual(result.skipped[0].code, "rendered_dimensions_exceeded")


class _LegacyReader:
    def __init__(self) -> None:
        self.read_document_calls = 0

    def read(self, path: Path) -> str:
        return "legacy source text"

    def read_document(self, path: Path) -> object:
        self.read_document_calls += 1
        raise AssertionError("legacy import must not call visual source analyzer")


if __name__ == "__main__":
    unittest.main()
