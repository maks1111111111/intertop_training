"""Tests for Knowledge Base answer prompt builder."""

from __future__ import annotations

import unittest

from app.ai.knowledge_answer_interfaces import KnowledgeAnswerRequest
from app.ai.knowledge_answer_prompt_builder import (
    KnowledgeAnswerPromptBuilder,
    KnowledgeAnswerPromptBuildingError,
)
from app.knowledge.context_builder import (
    KnowledgeContextSource,
    KnowledgeRetrievalContext,
)


def _context_with_sources(
    query: str = "Как оформить возврат?",
    *,
    language: str = "ru",
) -> KnowledgeRetrievalContext:
    source_text = "Возврат товара возможен в течение 14 дней."
    context_text = (
        "[Source 1 | document=return-policy | chunk=0]\n"
        f"{source_text}"
    )
    return KnowledgeRetrievalContext(
        query=query,
        sources=(
            KnowledgeContextSource(
                company_id="company-a",
                document_id="return-policy",
                chunk_index=0,
                text=source_text,
                start_char=0,
                end_char=len(source_text),
            ),
        ),
        context_text=context_text,
        source_count=1,
        total_chars=len(source_text),
        truncated=False,
    )


def _empty_context(query: str = "Как оформить возврат?") -> KnowledgeRetrievalContext:
    return KnowledgeRetrievalContext(
        query=query,
        sources=(),
        context_text="",
        source_count=0,
        total_chars=0,
        truncated=False,
    )


class KnowledgeAnswerPromptBuilderTests(unittest.TestCase):
    """Tests for :class:`KnowledgeAnswerPromptBuilder`."""

    def setUp(self) -> None:
        self.builder = KnowledgeAnswerPromptBuilder()

    def test_russian_question_and_context_included(self) -> None:
        question = "Как оформить возврат?"
        context = _context_with_sources(query=question)
        request = KnowledgeAnswerRequest(
            question=question,
            context=context,
            language="ru",
        )

        prompt = self.builder.build(request)

        self.assertIn(question, prompt)
        self.assertIn(context.context_text, prompt)
        self.assertIn("Language code: ru", prompt)
        self.assertIn("Write the answer string only in Russian.", prompt)

    def test_kazakh_language_instruction(self) -> None:
        request = KnowledgeAnswerRequest(
            question="Қайтаруды қалай рәсімдеуге болады?",
            context=_context_with_sources(),
            language="kk",
        )

        prompt = self.builder.build(request)

        self.assertIn("Language code: kk", prompt)
        self.assertIn("Write the answer string only in Kazakh.", prompt)

    def test_english_language_instruction(self) -> None:
        request = KnowledgeAnswerRequest(
            question="How do I process a return?",
            context=_context_with_sources(),
            language="en",
        )

        prompt = self.builder.build(request)

        self.assertIn("Language code: en", prompt)
        self.assertIn("Write the answer string only in English.", prompt)
        self.assertNotIn(
            "Do not reply in English unless the response language code is en.",
            prompt,
        )

    def test_english_response_language_overrides_source_language(self) -> None:
        request = KnowledgeAnswerRequest(
            question="How many days does a customer have to return an item?",
            context=_context_with_sources(),
            language="en",
        )

        prompt = self.builder.build(request)

        self.assertIn("Language code: en", prompt)
        self.assertIn("Write the answer string only in English.", prompt)
        self.assertIn(
            "Do not write the answer in Russian or Kazakh",
            prompt,
        )
        self.assertIn(
            "The language of the question or Knowledge Base sources MUST NOT "
            "change the requested response language.",
            prompt,
        )
        self.assertIn(
            "Translate supported information from the supplied sources into "
            "the requested response language when necessary.",
            prompt,
        )

    def test_workflow_stage_names_must_be_translated(self) -> None:
        request = KnowledgeAnswerRequest(
            question="Расскажи про этап спрашивай",
            context=_context_with_sources(),
            language="en",
        )

        prompt = self.builder.build(request)

        self.assertIn(
            "Translate ordinary business terminology into the requested response language",
            prompt,
        )
        self.assertIn(
            "Do not preserve Russian or Kazakh workflow-stage labels",
            prompt,
        )

    def test_only_genuine_proper_nouns_may_remain_untranslated(self) -> None:
        request = KnowledgeAnswerRequest(
            question="Расскажи про этап спрашивай",
            context=_context_with_sources(),
            language="kk",
        )

        prompt = self.builder.build(request)

        self.assertIn(
            "Only genuine proper nouns may remain in their original language",
            prompt,
        )

    def test_source_headers_preserved(self) -> None:
        request = KnowledgeAnswerRequest(
            question="Question?",
            context=_context_with_sources(),
        )

        prompt = self.builder.build(request)

        self.assertIn("[Source 1 | document=return-policy | chunk=0]", prompt)

    def test_json_only_instruction_present(self) -> None:
        request = KnowledgeAnswerRequest(
            question="Question?",
            context=_context_with_sources(),
        )

        prompt = self.builder.build(request)

        self.assertIn("Return ONLY valid JSON.", prompt)
        self.assertIn("Do not use Markdown.", prompt)
        self.assertIn("Do not wrap JSON in code fences.", prompt)
        self.assertIn("Do not include commentary outside JSON.", prompt)

    def test_required_output_fields_present(self) -> None:
        request = KnowledgeAnswerRequest(
            question="Question?",
            context=_context_with_sources(),
        )

        prompt = self.builder.build(request)

        self.assertIn('"answer": "..."', prompt)
        self.assertIn('"sufficient_context": true', prompt)
        self.assertIn('"citations": [', prompt)
        self.assertIn('"source_number": 1', prompt)
        self.assertIn('"document_id": "doc-id"', prompt)
        self.assertIn('"chunk_index": 0', prompt)

    def test_grounding_only_instruction_present(self) -> None:
        request = KnowledgeAnswerRequest(
            question="Question?",
            context=_context_with_sources(),
        )

        prompt = self.builder.build(request)

        self.assertIn("Answer ONLY from the supplied Knowledge Base context below.", prompt)
        self.assertIn(
            "Treat the supplied context as the only authoritative factual source.",
            prompt,
        )

    def test_no_outside_knowledge_instruction_present(self) -> None:
        request = KnowledgeAnswerRequest(
            question="Question?",
            context=_context_with_sources(),
        )

        prompt = self.builder.build(request)

        self.assertIn(
            "Do not use outside, general, or world knowledge to fill gaps.",
            prompt,
        )

    def test_no_guessing_instruction_present(self) -> None:
        request = KnowledgeAnswerRequest(
            question="Question?",
            context=_context_with_sources(),
        )

        prompt = self.builder.build(request)

        self.assertIn(
            "If the context does not provide enough information to answer reliably, do NOT guess.",
            prompt,
        )

    def test_insufficient_context_behavior_present(self) -> None:
        request = KnowledgeAnswerRequest(
            question="Question?",
            context=_context_with_sources(),
        )

        prompt = self.builder.build(request)

        self.assertIn(
            "available corporate knowledge is insufficient",
            prompt,
        )
        self.assertIn(
            "sufficient_context is false",
            prompt.lower(),
        )

    def test_not_mentioned_vs_false_distinction_present(self) -> None:
        request = KnowledgeAnswerRequest(
            question="Question?",
            context=_context_with_sources(),
        )

        prompt = self.builder.build(request)

        self.assertIn(
            "Distinguish 'not found in supplied context' from 'false' or 'prohibited'.",
            prompt,
        )
        self.assertIn(
            "Do not claim that something is prohibited, allowed, or does not exist merely because the context does not mention it.",
            prompt,
        )

    def test_citations_must_reference_supplied_sources_only(self) -> None:
        request = KnowledgeAnswerRequest(
            question="Question?",
            context=_context_with_sources(),
        )

        prompt = self.builder.build(request)

        self.assertIn(
            "citations must reference ONLY sources actually present in the supplied context.",
            prompt,
        )
        self.assertIn("Never invent source numbers.", prompt)
        self.assertIn(
            "source_number is the exact 1-based number shown in the supplied context headers",
            prompt,
        )
        self.assertIn("Copy document_id and chunk_index exactly", prompt)
        self.assertIn("Never infer, guess, or renumber sources.", prompt)

    def test_material_claims_require_citations(self) -> None:
        request = KnowledgeAnswerRequest(
            question="Question?",
            context=_context_with_sources(),
        )

        prompt = self.builder.build(request)

        self.assertIn(
            "Every material factual claim in a successful answer must be supported by one or more supplied sources.",
            prompt,
        )

    def test_empty_context_forces_sufficient_context_false(self) -> None:
        request = KnowledgeAnswerRequest(
            question="Question?",
            context=_empty_context(),
        )

        prompt = self.builder.build(request)

        self.assertIn("sufficient_context MUST be false.", prompt)
        self.assertIn("(No supporting sources were retrieved.)", prompt)

    def test_empty_context_forces_empty_citations(self) -> None:
        request = KnowledgeAnswerRequest(
            question="Question?",
            context=_empty_context(),
        )

        prompt = self.builder.build(request)

        self.assertIn("citations MUST be an empty list [].", prompt)

    def test_empty_context_prohibits_general_knowledge_answer(self) -> None:
        request = KnowledgeAnswerRequest(
            question="Question?",
            context=_empty_context(),
        )

        prompt = self.builder.build(request)

        self.assertIn("Do not answer from general or outside knowledge.", prompt)

    def test_whitespace_question_rejected(self) -> None:
        request = KnowledgeAnswerRequest(
            question="   ",
            context=_context_with_sources(),
        )

        with self.assertRaises(KnowledgeAnswerPromptBuildingError) as ctx:
            self.builder.build(request)

        self.assertEqual(ctx.exception.message, "question must not be empty")

    def test_unsupported_language_rejected(self) -> None:
        request = KnowledgeAnswerRequest(
            question="Question?",
            context=_context_with_sources(),
            language="de",
        )

        with self.assertRaises(KnowledgeAnswerPromptBuildingError) as ctx:
            self.builder.build(request)

        self.assertEqual(ctx.exception.message, "Unsupported response language.")

    def test_prompt_deterministic_for_same_request(self) -> None:
        request = KnowledgeAnswerRequest(
            question="Как оформить возврат?",
            context=_context_with_sources(),
            language="ru",
        )

        first = self.builder.build(request)
        second = self.builder.build(request)

        self.assertEqual(first, second)

    def test_unicode_source_and_question_preserved(self) -> None:
        question = "Қайтару саясаты қандай? Әріптер: әіңғүұқөһ"
        source_text = "Қазақша мәтін: сатып алушы 14 күн ішінде қайтара алады."
        context_text = (
            "[Source 1 | document=kz-policy | chunk=0]\n"
            f"{source_text}"
        )
        context = KnowledgeRetrievalContext(
            query=question,
            sources=(
                KnowledgeContextSource(
                    company_id="company-a",
                    document_id="kz-policy",
                    chunk_index=0,
                    text=source_text,
                    start_char=0,
                    end_char=len(source_text),
                ),
            ),
            context_text=context_text,
            source_count=1,
            total_chars=len(source_text),
            truncated=False,
        )
        request = KnowledgeAnswerRequest(
            question=question,
            context=context,
            language="kk",
        )

        prompt = self.builder.build(request)

        self.assertIn(question, prompt)
        self.assertIn(source_text, prompt)
        self.assertIn("Қазақша мәтін", prompt)

    def test_no_filesystem_path_in_prompt(self) -> None:
        request = KnowledgeAnswerRequest(
            question="Question?",
            context=_context_with_sources(),
        )

        prompt = self.builder.build(request)

        self.assertNotIn("/Users/", prompt)
        self.assertNotIn("/tmp/", prompt)
        self.assertNotIn("courses/", prompt)

    def test_prompt_requires_natural_opening_sentence(self) -> None:
        request = KnowledgeAnswerRequest(
            question="Расскажи про этап спрашивай",
            context=_context_with_sources(query="Расскажи про этап спрашивай"),
        )

        prompt = self.builder.build(request)

        self.assertIn("The first sentence must read naturally", prompt)
        self.assertIn("Do not begin the answer as if quoting the middle", prompt)

    def test_prompt_forbids_invented_item_counts(self) -> None:
        request = KnowledgeAnswerRequest(
            question="Сколько этапов?",
            context=_context_with_sources(query="Сколько этапов?"),
        )

        prompt = self.builder.build(request)

        self.assertIn("Do not state a specific count such as '7 steps'", prompt)
        self.assertIn("includes the following steps", prompt)
