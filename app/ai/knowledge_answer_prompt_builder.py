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
        f"- Write the answer string only in {label}.",
        "- The requested response language is authoritative.",
        (
            "- The language of the question or Knowledge Base sources MUST NOT "
            "change the requested response language."
        ),
        (
            "- Translate supported information from the supplied sources into "
            "the requested response language when necessary."
        ),
        "- Use the requested response language consistently throughout the answer.",
        (
            "- Translate ordinary business terminology into the requested response "
            "language, including section headings, workflow stage names, process "
            "step names, instructions, rules, and employee actions."
        ),
        (
            "- Do not preserve Russian or Kazakh workflow-stage labels merely "
            "because they appear as headings in the source document."
        ),
        (
            "- Only genuine proper nouns may remain in their original language "
            "when appropriate: company names, brand names, trademarks, product "
            "names, filenames, and document titles."
        ),
    ]

    if language == "en":
        lines.append(
            "- Do not write the answer in Russian or Kazakh, even when the supplied sources are in those languages."
        )
    elif language == "kk":
        lines.append(
            "- Do not write the answer in Russian or English, even when the supplied sources are in those languages."
        )
    elif language == "ru":
        lines.append(
            "- Do not write the answer in Kazakh or English, even when the supplied sources are in those languages."
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


def _answer_quality_rules_lines() -> list[str]:
    return [
        "",
        "Answer quality rules:",
        (
            "- The first sentence must read naturally and answer the user's "
            "question directly."
        ),
        (
            "- Do not begin the answer as if quoting the middle of a document "
            "or section heading."
        ),
        (
            "- Write as a helpful corporate assistant, not as a raw document "
            "fragment."
        ),
        (
            "- When listing items, include every item you can support from "
            "the supplied context."
        ),
        (
            "- Do not state a specific count such as '7 steps' unless the "
            "supplied context explicitly and completely supports that exact "
            "count."
        ),
        (
            "- If the exact count is uncertain, use phrasing such as "
            "'includes the following steps' without inventing a number."
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
        (
            "- answer: the opening sentence must be natural and respond to "
            "the question, not start like a document excerpt."
        ),
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
            *_answer_quality_rules_lines(),
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
