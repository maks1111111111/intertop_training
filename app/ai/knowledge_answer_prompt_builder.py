"""Prompt builder for grounded Knowledge Base AI answering.

Assembles deterministic text prompts from answer requests.
No LLM calls or external dependencies are used here.
"""

from __future__ import annotations

from app.ai.knowledge_answer_interfaces import KnowledgeAnswerRequest
from app.ai.review_language import normalize_review_language
from app.knowledge.context_builder import KnowledgeRetrievalContext

_LANGUAGE_LABELS = {
    "ru": "Russian",
    "kk": "Kazakh",
    "en": "English",
}


class KnowledgeAnswerPromptBuildingError(Exception):
    """Raised when a knowledge-answer prompt request is invalid."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _language_instruction_lines(language: str) -> list[str]:
    label = _LANGUAGE_LABELS.get(language, language)
    lines = [
        "",
        "Response language:",
        f"- Language code: {language}",
        f"- Write the answer string in {label}.",
        "- Use the same response language consistently throughout the answer.",
        "- Do not mix languages within the answer unless source names or proper nouns require it.",
    ]
    if language != "en":
        lines.append(
            "- Do not reply in English unless the response language code is en."
        )
    return lines


def _empty_context_instruction_lines() -> list[str]:
    return [
        "",
        "Empty context notice:",
        "- No supporting corporate Knowledge Base sources were retrieved.",
        "- sufficient_context MUST be false.",
        "- Do not answer from general or outside knowledge.",
        "- citations MUST be an empty list [].",
        (
            "- The answer must clearly state that the available corporate "
            "knowledge does not contain enough information to answer reliably."
        ),
    ]


def _grounding_rules_lines() -> list[str]:
    return [
        "Grounding rules:",
        "- Answer ONLY from the supplied Knowledge Base context below.",
        "- Treat the supplied context as the only authoritative factual source.",
        "- Do not use outside, general, or world knowledge to fill gaps.",
        "- Do not infer company policy beyond what the context explicitly supports.",
        (
            "- Do not invent procedures, deadlines, permissions, exceptions, "
            "contacts, amounts, rules, or requirements."
        ),
        (
            "- If the context does not provide enough information to answer "
            "reliably, do NOT guess."
        ),
        (
            "- When information is incomplete or ambiguous, state that the "
            "available corporate knowledge is insufficient."
        ),
        (
            "- Distinguish 'not found in supplied context' from 'false' or "
            "'prohibited'."
        ),
        (
            "- Do not claim that something is prohibited, allowed, or does "
            "not exist merely because the context does not mention it."
        ),
    ]


def _citation_rules_lines() -> list[str]:
    return [
        "",
        "Citation rules:",
        (
            "- Every material factual claim in a successful answer must be "
            "supported by one or more supplied sources."
        ),
        "- citations must reference ONLY sources actually present in the supplied context.",
        (
            "- source_number is the exact 1-based number shown in the supplied "
            "context headers (for example, [Source 1 | ...])."
        ),
        "- Copy document_id and chunk_index exactly from the matching source header.",
        "- Never infer, guess, or renumber sources.",
        "- Never invent source numbers.",
        "- Never cite a source that does not support the answer.",
        "- Prefer the minimum sufficient set of relevant sources.",
        (
            "- If sufficient_context is false, citations may be empty or contain "
            "only sources that explain why the available information is insufficient."
        ),
        "- Do not include duplicate citations.",
        "- When sufficient_context is true, citations should normally be non-empty.",
        "- Do not expose internal reasoning or chain-of-thought.",
    ]


def _output_format_lines() -> list[str]:
    return [
        "",
        "Return ONLY valid JSON.",
        "Do not use Markdown.",
        "Do not wrap JSON in code fences.",
        "Do not include commentary outside JSON.",
        "Use exactly this schema:",
        "",
        "{",
        '  "answer": "...",',
        '  "sufficient_context": true,',
        '  "citations": [',
        "    {",
        '      "source_number": 1,',
        '      "document_id": "doc-id",',
        '      "chunk_index": 0',
        "    }",
        "  ]",
        "}",
        "",
        "Field rules:",
        "- answer: concise but complete; directly answers the user's question.",
        "- answer: must use the requested response language.",
        (
            "- answer: if sufficient_context is false, clearly say that the "
            "available corporate knowledge does not contain enough information "
            "to answer reliably."
        ),
        "- answer: do not fabricate an answer merely to be helpful.",
        (
            "- sufficient_context: true only when supplied context supports "
            "a reliable answer."
        ),
        (
            "- sufficient_context: false when context is empty, irrelevant, "
            "incomplete, contradictory, or insufficient for a reliable "
            "corporate answer."
        ),
        (
            "- citations: each citation must use the exact source_number, "
            "document_id, and chunk_index from the supplied context."
        ),
        (
            "- citations: document_id and chunk_index are the authoritative "
            "source identity; source_number must match the header label."
        ),
    ]


class KnowledgeAnswerPromptBuilder:
    """Build text prompts for grounded Knowledge Base AI answering."""

    def build(self, request: KnowledgeAnswerRequest) -> str:
        """Build a prompt for answering a question from retrieval context.

        Args:
            request: Answer input including question and retrieval context.

        Returns:
            A deterministic answering prompt.

        Raises:
            KnowledgeAnswerPromptBuildingError: If the question or language is invalid.
        """
        question = request.question.strip()
        if not question:
            raise KnowledgeAnswerPromptBuildingError("question must not be empty")

        language = normalize_review_language(request.language)
        if language is None:
            raise KnowledgeAnswerPromptBuildingError(
                "Unsupported response language."
            )

        context = request.context
        has_context = context.source_count > 0 and bool(context.context_text.strip())

        lines = [
            (
                "You are a corporate Knowledge Base assistant for a high-trust "
                "business environment."
            ),
            "Your role is to answer employee questions using ONLY the supplied sources.",
            *_grounding_rules_lines(),
            *_language_instruction_lines(language),
            "",
            "Question:",
            question,
            "",
            "Available Knowledge Base sources:",
        ]

        if has_context:
            lines.append(context.context_text)
        else:
            lines.append("(No supporting sources were retrieved.)")
            lines.extend(_empty_context_instruction_lines())

        lines.extend(_citation_rules_lines())
        lines.extend(_output_format_lines())
        lines.extend(
            [
                "",
                "Final reminder:",
                "- Ground every factual claim in the supplied sources only.",
                "- Never guess when context is insufficient.",
                "- Return valid JSON matching the schema above.",
            ]
        )

        return "\n".join(lines).rstrip("\n")
