"""Deterministic text chunking for the corporate Knowledge Base."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Tuple

DEFAULT_TARGET_CHARS = 1200
DEFAULT_OVERLAP_CHARS = 150
DEFAULT_MIN_CHUNK_CHARS = 100

_SENTENCE_END_RE = re.compile(r"[.!?](?:\s|$)")


@dataclass(frozen=True)
class KnowledgeChunk:
    """One contiguous slice of normalized source text."""

    index: int
    text: str
    start_char: int
    end_char: int


@dataclass(frozen=True)
class KnowledgeChunkingOptions:
    """Tunable chunking parameters."""

    target_chars: int = DEFAULT_TARGET_CHARS
    overlap_chars: int = DEFAULT_OVERLAP_CHARS
    min_chunk_chars: int = DEFAULT_MIN_CHUNK_CHARS


def _validate_options(options: KnowledgeChunkingOptions) -> None:
    if options.target_chars <= 0:
        raise ValueError("target_chars must be positive")
    if options.overlap_chars < 0:
        raise ValueError("overlap_chars must be non-negative")
    if options.overlap_chars >= options.target_chars:
        raise ValueError("overlap_chars must be less than target_chars")
    if options.min_chunk_chars <= 0:
        raise ValueError("min_chunk_chars must be positive")
    if options.min_chunk_chars > options.target_chars:
        raise ValueError("min_chunk_chars must not exceed target_chars")


def _normalize_line_endings(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _find_paragraph_boundary(text: str, start: int, min_end: int, max_end: int) -> Optional[int]:
    best: Optional[int] = None
    search_from = start
    while search_from < max_end:
        idx = text.find("\n\n", search_from, max_end)
        if idx == -1:
            break
        candidate = idx + 2
        if candidate >= min_end:
            best = candidate
        search_from = idx + 1
    return best


def _find_sentence_boundary(text: str, start: int, min_end: int, max_end: int) -> Optional[int]:
    best: Optional[int] = None
    for match in _SENTENCE_END_RE.finditer(text, start, max_end):
        candidate = match.end()
        if candidate >= min_end:
            best = candidate
    return best


def _find_whitespace_boundary(text: str, start: int, min_end: int, max_end: int) -> Optional[int]:
    best: Optional[int] = None
    for index in range(min_end, max_end):
        if text[index].isspace():
            best = index + 1
    return best


def _find_chunk_end(text: str, start: int, options: KnowledgeChunkingOptions) -> int:
    text_length = len(text)
    max_end = min(start + options.target_chars, text_length)
    min_end = min(start + options.min_chunk_chars, max_end)

    if max_end <= start:
        return text_length

    paragraph_end = _find_paragraph_boundary(text, start, min_end, max_end)
    if paragraph_end is not None:
        return paragraph_end

    sentence_end = _find_sentence_boundary(text, start, min_end, max_end)
    if sentence_end is not None:
        return sentence_end

    whitespace_end = _find_whitespace_boundary(text, start, min_end, max_end)
    if whitespace_end is not None:
        return whitespace_end

    return max_end


class KnowledgeTextChunker:
    """Split normalized knowledge text into overlapping chunks."""

    def chunk(
        self,
        text: str,
        options: Optional[KnowledgeChunkingOptions] = None,
    ) -> Tuple[KnowledgeChunk, ...]:
        """Return deterministic chunks for the given text."""
        resolved = options or KnowledgeChunkingOptions()
        _validate_options(resolved)

        normalized = _normalize_line_endings(text)
        if not normalized.strip():
            return ()

        chunks: list[KnowledgeChunk] = []
        text_length = len(normalized)
        start = 0
        chunk_index = 0
        # Worst case advances one character per iteration; guard against bugs.
        max_iterations = text_length + 1
        iteration = 0

        while start < text_length:
            iteration += 1
            if iteration > max_iterations:
                break

            if text_length - start <= resolved.target_chars:
                end = text_length
            else:
                end = _find_chunk_end(normalized, start, resolved)

            remaining = text_length - end
            if (
                remaining > 0
                and remaining < resolved.min_chunk_chars
                and end < text_length
            ):
                end = text_length

            chunk_text = normalized[start:end]
            if not chunk_text.strip():
                if end >= text_length:
                    break
                start = max(start + 1, end)
                continue

            chunks.append(
                KnowledgeChunk(
                    index=chunk_index,
                    text=chunk_text,
                    start_char=start,
                    end_char=end,
                )
            )
            chunk_index += 1

            if end >= text_length:
                break

            next_start = end - resolved.overlap_chars
            if next_start <= start:
                next_start = end
            start = next_start

        return tuple(chunks)
