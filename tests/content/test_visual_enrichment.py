"""Tests for additive visual source enrichment contracts."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.content.importer import CourseImporter
from app.content.source_document import (
    SourceBoundary,
    SourceDocument,
    SourceImage,
    SourceParagraph,
    SourceProvenance,
    build_source_image,
)
from app.content.visual_enrichment import (
    AnalysisLimitation,
    DiagramEdge,
    DiagramNode,
    EnrichedSourceDocument,
    VisualAnalysis,
    VisualDiagram,
    VisualSection,
    VisualTable,
    VisualUIControl,
    VisualInputTransform,
    build_visual_id,
    compute_content_hash,
)


class VisualEnrichmentContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.page_provenance = SourceProvenance(
            document="guide.pdf", order=1, position=0, page=1
        )
        self.image_provenance = SourceProvenance(
            document="guide.pdf", order=3, position=2, page=1
        )
        self.image_content = b"source image evidence"
        self.source_image = build_source_image(
            document="guide.pdf",
            content=self.image_content,
            provenance=self.image_provenance,
        )
        self.source = SourceDocument(
            name="guide.pdf",
            source_format="pdf",
            elements=(
                SourceBoundary("page_break", self.page_provenance),
                SourceParagraph(
                    "Open the cash register.",
                    SourceProvenance(document="guide.pdf", order=2, position=1, page=1),
                ),
                self.source_image,
            ),
        )

    def _analysis(
        self,
        *,
        input_kind: str = "source_image",
        source_asset_id: str | None = None,
        provenance: SourceProvenance | None = None,
        source_content_hash: str | None = None,
        input_content_hash: str | None = None,
        confidence: float | None = 0.9,
        visual_id: str | None = None,
        diagrams: tuple[VisualDiagram, ...] = (),
        ui_controls: tuple[VisualUIControl, ...] = (),
        detected_text: tuple[str, ...] = ("Open shift",),
        input_transform: VisualInputTransform | None = None,
    ) -> VisualAnalysis:
        source_asset_id = (
            self.source_image.asset_id
            if source_asset_id is None and input_kind == "source_image"
            else source_asset_id
        )
        provenance = provenance or (
            self.image_provenance if input_kind == "source_image" else self.page_provenance
        )
        source_content_hash = source_content_hash or compute_content_hash(self.image_content)
        input_content_hash = input_content_hash or source_content_hash
        visual_id = visual_id or build_visual_id(
            self.source,
            input_kind=input_kind,
            provenance=provenance,
            source_content_hash=source_content_hash,
            source_asset_id=source_asset_id,
        )
        return VisualAnalysis(
            visual_id=visual_id,
            source_asset_id=source_asset_id,
            provenance=provenance,
            input_kind=input_kind,
            source_content_hash=source_content_hash,
            input_content_hash=input_content_hash,
            description="Cash register screen with a primary action.",
            detected_text=detected_text,
            sections=(VisualSection("Opening", "Choose the opening action.", 2),),
            tables=(VisualTable(("Step", "Action"), (("1", "Open"),)),),
            ui_controls=ui_controls,
            diagrams=diagrams,
            confidence=confidence,
            limitations=(AnalysisLimitation("layout_ambiguous", "No screen coordinates."),),
            input_transform=input_transform,
        )

    def test_valid_enriched_document_preserves_original_source(self) -> None:
        analysis = self._analysis(
            ui_controls=(VisualUIControl("button", "Open shift", "enabled"),),
            diagrams=(
                VisualDiagram(
                    kind="flow",
                    summary="Open the shift, then accept payment.",
                    nodes=(
                        DiagramNode("open", "Open shift", "process_step"),
                        DiagramNode("pay", "Accept payment", "process_step"),
                    ),
                    edges=(DiagramEdge("open", "pay", "flows_to"),),
                ),
            ),
        )

        enriched = EnrichedSourceDocument(self.source, 1, (analysis,))

        self.assertIs(enriched.source, self.source)
        self.assertEqual(enriched.source.elements, self.source.elements)
        self.assertEqual(enriched.analyses, (analysis,))

    def test_duplicate_visual_ids_are_rejected(self) -> None:
        analysis = self._analysis()
        duplicate = VisualAnalysis(
            visual_id=analysis.visual_id,
            source_asset_id=analysis.source_asset_id,
            provenance=analysis.provenance,
            input_kind=analysis.input_kind,
            source_content_hash=analysis.source_content_hash,
            input_content_hash=analysis.input_content_hash,
            description=analysis.description,
        )

        with self.assertRaisesRegex(ValueError, "unique"):
            EnrichedSourceDocument(self.source, 1, (analysis, duplicate))

    def test_unknown_source_asset_is_rejected(self) -> None:
        analysis = self._analysis(source_asset_id="unknown-asset")

        with self.assertRaisesRegex(ValueError, "not declared"):
            EnrichedSourceDocument(self.source, 1, (analysis,))

    def test_mismatched_provenance_is_rejected(self) -> None:
        mismatched = SourceProvenance(document="guide.pdf", order=2, position=1, page=1)
        analysis = self._analysis(provenance=mismatched)

        with self.assertRaisesRegex(ValueError, "provenance"):
            EnrichedSourceDocument(self.source, 1, (analysis,))

    def test_invalid_confidence_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "confidence"):
            self._analysis(confidence=1.1)

    def test_oversized_detected_text_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "maximum length"):
            self._analysis(detected_text=("x" * 2_001,))

    def test_unknown_diagram_kind_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported diagram kind"):
            VisualDiagram(
                kind="mind_map",
                summary="A diagram.",
                nodes=(DiagramNode("cash", "Cash", "concept"),),
                edges=(),
            )

    def test_unknown_visual_input_kind_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported input kind"):
            self._analysis(input_kind="raw_pdf")

    def test_transformed_input_preserves_source_observation_identity(self) -> None:
        source_hash = compute_content_hash(self.image_content)
        transformed_hash = compute_content_hash(b"resized and re-encoded image")
        original = self._analysis(source_content_hash=source_hash)
        transformed = self._analysis(
            source_content_hash=source_hash,
            input_content_hash=transformed_hash,
            input_transform=VisualInputTransform(1, "contain", 1600, "image/jpeg"),
        )

        enriched = EnrichedSourceDocument(self.source, 1, (transformed,))

        self.assertEqual(original.visual_id, transformed.visual_id)
        self.assertEqual(enriched.analyses[0].source_content_hash, source_hash)
        self.assertEqual(enriched.analyses[0].input_content_hash, transformed_hash)

    def test_vector_conversion_transform_is_explicit_and_versioned(self) -> None:
        transform = VisualInputTransform(
            2,
            "none",
            None,
            "image/png",
            "wmf_to_png",
        )

        self.assertEqual(transform.version, 2)
        self.assertEqual(transform.vector_conversion, "wmf_to_png")
        with self.assertRaisesRegex(ValueError, "requires transform version 2"):
            VisualInputTransform(1, "none", None, "image/png", "wmf_to_png")
        with self.assertRaisesRegex(ValueError, "requires vector conversion"):
            VisualInputTransform(2, "none", None, "image/png")

    def test_wrong_original_source_hash_is_rejected(self) -> None:
        analysis = self._analysis(source_content_hash=compute_content_hash(b"different bytes"))

        with self.assertRaisesRegex(ValueError, "content hash"):
            EnrichedSourceDocument(self.source, 1, (analysis,))

    def test_visual_id_changes_for_source_identity_changes(self) -> None:
        source_hash = compute_content_hash(self.image_content)
        image_id = build_visual_id(
            self.source,
            input_kind="source_image",
            provenance=self.image_provenance,
            source_content_hash=source_hash,
            source_asset_id=self.source_image.asset_id,
        )
        page_id = build_visual_id(
            self.source,
            input_kind="page_render",
            provenance=self.page_provenance,
            source_content_hash=source_hash,
            source_asset_id=None,
        )
        changed_hash_id = build_visual_id(
            self.source,
            input_kind="source_image",
            provenance=self.image_provenance,
            source_content_hash=compute_content_hash(b"changed source"),
            source_asset_id=self.source_image.asset_id,
        )

        self.assertNotEqual(image_id, page_id)
        self.assertNotEqual(image_id, changed_hash_id)

    def test_pdf_page_render_requires_matching_page_boundary(self) -> None:
        analysis = self._analysis(input_kind="page_render", source_asset_id=None)

        enriched = EnrichedSourceDocument(self.source, 1, (analysis,))

        self.assertEqual(enriched.analyses[0].input_kind, "page_render")

    def test_pptx_slide_render_requires_matching_slide_boundary(self) -> None:
        slide_provenance = SourceProvenance(
            document="guide.pptx", order=1, position=0, slide=1
        )
        source = SourceDocument(
            name="guide.pptx",
            source_format="pptx",
            elements=(SourceBoundary("slide_boundary", slide_provenance),),
        )
        source_hash = compute_content_hash(b"canonical slide evidence")
        analysis = VisualAnalysis(
            visual_id=build_visual_id(
                source,
                input_kind="slide_render",
                provenance=slide_provenance,
                source_content_hash=source_hash,
                source_asset_id=None,
            ),
            source_asset_id=None,
            provenance=slide_provenance,
            input_kind="slide_render",
            source_content_hash=source_hash,
            input_content_hash=source_hash,
            description="Presentation slide.",
        )

        self.assertEqual(EnrichedSourceDocument(source, 1, (analysis,)).analyses, (analysis,))

    def test_cross_use_of_page_and_slide_boundaries_is_rejected(self) -> None:
        slide_provenance = SourceProvenance(
            document="guide.pptx", order=1, position=0, slide=1
        )
        source = SourceDocument(
            name="guide.pptx",
            source_format="pptx",
            elements=(SourceBoundary("slide_boundary", slide_provenance),),
        )
        source_hash = compute_content_hash(b"canonical slide evidence")
        analysis = VisualAnalysis(
            visual_id=build_visual_id(
                source,
                input_kind="page_render",
                provenance=slide_provenance,
                source_content_hash=source_hash,
                source_asset_id=None,
            ),
            source_asset_id=None,
            provenance=slide_provenance,
            input_kind="page_render",
            source_content_hash=source_hash,
            input_content_hash=source_hash,
            description="Presentation slide.",
        )

        with self.assertRaisesRegex(ValueError, "requires a PDF"):
            EnrichedSourceDocument(source, 1, (analysis,))

    def test_pdf_page_cannot_be_used_as_slide_render(self) -> None:
        source_hash = compute_content_hash(b"canonical page evidence")
        analysis = VisualAnalysis(
            visual_id=build_visual_id(
                self.source,
                input_kind="slide_render",
                provenance=self.page_provenance,
                source_content_hash=source_hash,
                source_asset_id=None,
            ),
            source_asset_id=None,
            provenance=self.page_provenance,
            input_kind="slide_render",
            source_content_hash=source_hash,
            input_content_hash=source_hash,
            description="PDF page.",
        )

        with self.assertRaisesRegex(ValueError, "requires a PPTX"):
            EnrichedSourceDocument(self.source, 1, (analysis,))

    def test_docx_is_not_given_fake_page_render_provenance(self) -> None:
        provenance = SourceProvenance(document="guide.docx", order=1, position=1, page=1)
        source = SourceDocument(
            name="guide.docx",
            source_format="docx",
            elements=(SourceParagraph("Body text.", provenance),),
        )
        source_hash = compute_content_hash(b"imaginary docx page")
        analysis = VisualAnalysis(
            visual_id=build_visual_id(
                source,
                input_kind="page_render",
                provenance=provenance,
                source_content_hash=source_hash,
                source_asset_id=None,
            ),
            source_asset_id=None,
            provenance=provenance,
            input_kind="page_render",
            source_content_hash=source_hash,
            input_content_hash=source_hash,
            description="Not a real page render.",
        )

        with self.assertRaisesRegex(ValueError, "requires a PDF"):
            EnrichedSourceDocument(source, 1, (analysis,))

    def test_document_accepts_known_cashier_scale_of_198_image_analyses(self) -> None:
        elements = []
        analyses = []
        for index in range(1, 199):
            provenance = SourceProvenance(
                document="cashier.pdf", order=index, position=index, page=index
            )
            image = build_source_image(
                document="cashier.pdf",
                content=f"source-image-{index}".encode("utf-8"),
                provenance=provenance,
            )
            elements.append(image)
        source = SourceDocument("cashier.pdf", "pdf", tuple(elements))
        for image in elements:
            assert isinstance(image, SourceImage)
            source_hash = compute_content_hash(image.content)
            analyses.append(
                VisualAnalysis(
                    visual_id=build_visual_id(
                        source,
                        input_kind="source_image",
                        provenance=image.provenance,
                        source_content_hash=source_hash,
                        source_asset_id=image.asset_id,
                    ),
                    source_asset_id=image.asset_id,
                    provenance=image.provenance,
                    input_kind="source_image",
                    source_content_hash=source_hash,
                    input_content_hash=source_hash,
                    description="Source screenshot.",
                )
            )

        enriched = EnrichedSourceDocument(source, 1, tuple(analyses))

        self.assertEqual(len(enriched.analyses), 198)

    def test_legacy_importer_path_does_not_invoke_visual_analysis_contracts(self) -> None:
        reader = _LegacyReader()

        result = CourseImporter(readers={"pdf": reader}).read_source(Path("guide.pdf"))

        self.assertEqual(result, "legacy source text")
        self.assertEqual(reader.read_document_calls, 0)


class _LegacyReader:
    def __init__(self) -> None:
        self.read_document_calls = 0

    def read(self, path: Path) -> str:
        return "legacy source text"

    def read_document(self, path: Path) -> object:
        self.read_document_calls += 1
        raise AssertionError("legacy import path must not invoke structured visual analysis")


if __name__ == "__main__":
    unittest.main()
