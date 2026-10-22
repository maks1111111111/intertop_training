"""PDF text extraction for the Content Engine import pipeline."""

from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader as _PypdfReader

from app.content.source_document import (
    SourceBoundary,
    SourceDocument,
    SourceParagraph,
    SourceProvenance,
    build_source_image,
    document_name,
)


class PdfReader:
    """Extract plain text from PDF files."""

    def read(self, path: Path) -> str:
        """Read and extract text from all pages of a PDF file.

        Args:
            path: Path to the PDF file.

        Returns:
            Extracted text with pages joined by newlines, or an empty string
            when no text is available.
        """
        reader = _PypdfReader(str(path))
        pages_text = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages_text)

    def read_document(self, path: Path) -> SourceDocument:
        """Read PDF page evidence without changing legacy plain-text output.

        pypdf exposes page text and embedded images but not dependable visual
        reading order, heading semantics, table structure, or image geometry.
        Elements are consequently ordered as page boundary, extracted text,
        then pypdf's image iteration order for each page.
        """
        reader = _PypdfReader(str(path))
        name = document_name(path)
        elements = []
        order = 0
        for page_number, page in enumerate(reader.pages, start=1):
            order += 1
            elements.append(
                SourceBoundary(
                    kind="page_break",
                    provenance=SourceProvenance(
                        document=name,
                        order=order,
                        position=0,
                        page=page_number,
                    ),
                )
            )
            position = 1
            text = (page.extract_text() or "").strip()
            if text:
                order += 1
                elements.append(
                    SourceParagraph(
                        text=text,
                        provenance=SourceProvenance(
                            document=name,
                            order=order,
                            position=position,
                            page=page_number,
                        ),
                    )
                )
                position += 1
            try:
                images = page.images
            except Exception:
                images = ()
            for image in images:
                content = getattr(image, "data", None)
                if not content:
                    continue
                order += 1
                provenance = SourceProvenance(
                    document=name,
                    order=order,
                    position=position,
                    page=page_number,
                )
                elements.append(
                    build_source_image(
                        document=name,
                        content=bytes(content),
                        provenance=provenance,
                    )
                )
                position += 1
        return SourceDocument(name=name, source_format="pdf", elements=tuple(elements))
