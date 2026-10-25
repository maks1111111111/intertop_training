"""Static instructions for provider-neutral visual source analysis."""

from __future__ import annotations


def build_visual_analysis_instruction() -> str:
    """Return the fixed instruction used for a bounded image-analysis batch.

    This prompt deliberately contains no customer document text, identifiers,
    paths, or application state.  Images are supplied separately by the
    caller in their original request order.
    """
    return """Analyze each supplied source image as visible evidence only.

Return exactly one structured analysis for each image, in the same order as
the images. Do not invent text, controls, relationships, facts, or layout
details that are not visible. Preserve important visible wording exactly when
it can be read; otherwise record an appropriate limitation. For user-interface
screenshots, identify only visible labels and controls and describe their
apparent relation. For diagrams, return nodes and edges only when their
relationship is visually supported. For full-page learning material, retain
visible sections, tables, and layout semantics rather than rewriting it as a
course. Return structured JSON only."""
