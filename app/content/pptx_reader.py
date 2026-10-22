"""PPTX text extraction for the Content Engine import pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator

from pptx import Presentation as _PptxPresentation
from pptx.enum.shapes import MSO_SHAPE_TYPE

from app.content.source_document import (
    SourceBoundary,
    SourceDocument,
    SourceParagraph,
    SourceProvenance,
    SourceTable,
    build_source_image,
    document_name,
)


class PptxReader:
    """Extract plain text from PPTX files."""

    def read(self, path: Path) -> str:
        """Read and extract text from all slides of a PPTX file.

        Args:
            path: Path to the PPTX file.

        Returns:
            Extracted text with non-empty shape text joined by newlines, or
            an empty string when no text is available.
        """
        presentation = _PptxPresentation(str(path))
        lines: list[str] = []
        for slide in presentation.slides:
            for shape in slide.shapes:
                text = getattr(shape, "text", None)
                if text:
                    lines.append(text)
        return "\n".join(lines)

    def read_document(self, path: Path) -> SourceDocument:
        """Read PPTX slides and shape evidence in deterministic shape order."""
        presentation = _PptxPresentation(str(path))
        name = document_name(path)
        elements = []
        order = 0

        def append(element) -> None:
            nonlocal order
            order += 1
            elements.append(element(order))

        for slide_number, slide in enumerate(presentation.slides, start=1):
            append(
                lambda global_order: SourceBoundary(
                    kind="slide_boundary",
                    provenance=SourceProvenance(
                        document=name,
                        order=global_order,
                        position=0,
                        slide=slide_number,
                    ),
                )
            )
            for position, shape in enumerate(_iter_shapes(slide.shapes), start=1):
                shape_type = getattr(shape, "shape_type", None)
                if shape_type == MSO_SHAPE_TYPE.PICTURE:
                    image = getattr(shape, "image", None)
                    blob = getattr(image, "blob", None)
                    if blob:
                        append(
                            lambda global_order, blob=blob: build_source_image(
                                document=name,
                                content=bytes(blob),
                                provenance=SourceProvenance(
                                    document=name,
                                    order=global_order,
                                    position=position,
                                    slide=slide_number,
                                ),
                            )
                        )
                    continue
                if bool(getattr(shape, "has_table", False)):
                    table = shape.table
                    rows = tuple(
                        tuple(cell.text.strip() for cell in row.cells)
                        for row in table.rows
                    )
                    append(
                        lambda global_order: SourceTable(
                            rows=rows,
                            provenance=SourceProvenance(
                                document=name,
                                order=global_order,
                                position=position,
                                slide=slide_number,
                            ),
                        )
                    )
                    continue
                text = str(getattr(shape, "text", "") or "").strip()
                if text:
                    append(
                        lambda global_order: SourceParagraph(
                            text=text,
                            provenance=SourceProvenance(
                                document=name,
                                order=global_order,
                                position=position,
                                slide=slide_number,
                            ),
                        )
                    )
        return SourceDocument(name=name, source_format="pptx", elements=tuple(elements))


def _iter_shapes(shapes: Iterable[object]) -> Iterator[object]:
    """Yield shape-tree order, recursively flattening groups deterministically."""
    for shape in shapes:
        if getattr(shape, "shape_type", None) == MSO_SHAPE_TYPE.GROUP:
            yield from _iter_shapes(getattr(shape, "shapes", ()))
            continue
        yield shape
