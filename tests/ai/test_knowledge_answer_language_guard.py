"""Tests for Knowledge Base answer language compliance guard."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from app.ai.knowledge_answer_interfaces import (
    KnowledgeAnswerCitation,
    KnowledgeAnswerResult,
)
from app.ai.knowledge_answer_language_guard import (
    KnowledgeAnswerLanguageGuard,
    KnowledgeAnswerLanguageRewriteError,
    build_language_rewrite_prompt,
    needs_language_rewrite,
)
from app.ai.knowledge_answer_service import (
    KnowledgeAnswerGenerationError,
    KnowledgeAnswerService,
)
from app.ai.knowledge_answer_interfaces import KnowledgeAnswerRequest
from app.knowledge.context_builder import (
    KnowledgeContextSource,
    KnowledgeRetrievalContext,
)


def _source(
    document_id: str = "doc-1",
    chunk_index: int = 0,
    text: str = "Return within 14 days.",
    company_id: str = "company-a",
) -> KnowledgeContextSource:
    return KnowledgeContextSource(
        company_id=company_id,
        document_id=document_id,
        chunk_index=chunk_index,
        text=text,
        start_char=0,
        end_char=len(text),
    )


def _context(
    sources: tuple[KnowledgeContextSource, ...] = (),
    query: str = "Question?",
) -> KnowledgeRetrievalContext:
    context_text = ""
    if sources:
        parts = []
        for index, source in enumerate(sources, start=1):
            parts.append(
                f"[Source {index} | document={source.document_id} | "
                f"chunk={source.chunk_index}]\n{source.text}"
            )
        context_text = "\n\n".join(parts)
    return KnowledgeRetrievalContext(
        query=query,
        sources=sources,
        context_text=context_text,
        source_count=len(sources),
        total_chars=len(context_text),
        truncated=False,
    )


def _result(
    answer: str,
    *,
    sufficient_context: bool = True,
) -> KnowledgeAnswerResult:
    return KnowledgeAnswerResult(
        answer=answer,
        citations=(KnowledgeAnswerCitation(1, "doc-1", 0),),
        sufficient_context=sufficient_context,
    )


class NeedsLanguageRewriteTests(unittest.TestCase):
    """Detection tests for cross-language leakage."""

    def test_clean_english_answer_no_rewrite(self) -> None:
        answer = (
            "The customer should ask the manager about the return policy "
            "within fourteen days."
        )
        self.assertFalse(needs_language_rewrite(answer, "en"))

    def test_english_with_meaningful_russian_prose_triggers_rewrite(self) -> None:
        answer = (
            "The customer should оформление возврата at the service desk "
            "before leaving the store."
        )
        self.assertTrue(needs_language_rewrite(answer, "en"))

    def test_english_with_single_untranslated_cyrillic_term_triggers_rewrite(
        self,
    ) -> None:
        answer = (
            'The "спрашивай" stage helps employees understand customer needs.'
        )
        self.assertTrue(needs_language_rewrite(answer, "en"))

    def test_english_with_legitimate_latin_brand_name_no_rewrite(self) -> None:
        answer = (
            "Visit the Intertop service desk if you need help with a return "
            "within fourteen days."
        )
        self.assertFalse(needs_language_rewrite(answer, "en"))

    def test_clean_russian_answer_no_rewrite(self) -> None:
        answer = (
            "Возврат оформляется в течение 14 дней при наличии чека "
            "и сохранённой упаковки."
        )
        self.assertFalse(needs_language_rewrite(answer, "ru"))

    def test_russian_with_kazakh_letters_triggers_rewrite(self) -> None:
        answer = "Қайтаруды 14 күн ішінде рәсімдеу керек."
        self.assertTrue(needs_language_rewrite(answer, "ru"))

    def test_russian_with_english_prose_triggers_rewrite(self) -> None:
        answer = (
            "Клиент должен contact the manager and complete the return "
            "process at the desk."
        )
        self.assertTrue(needs_language_rewrite(answer, "ru"))

    def test_clean_kazakh_answer_no_rewrite(self) -> None:
        answer = "Сатып алуды 14 күн ішінде рәсімдеу керек."
        self.assertFalse(needs_language_rewrite(answer, "kk"))

    def test_kazakh_with_embedded_russian_phrase_triggers_rewrite(self) -> None:
        answer = (
            'Этап "спрашивай и благодари" қызметкерге клиенттің '
            "қажеттіліктерін түсінуге көмектеседі."
        )
        self.assertTrue(needs_language_rewrite(answer, "kk"))

    def test_kazakh_with_single_quoted_russian_workflow_term_triggers_rewrite(
        self,
    ) -> None:
        answer = (
            "Этап «спрашивай» қызметкердің қажеттіліктерін "
            "түсінуге көмектеседі."
        )
        self.assertTrue(needs_language_rewrite(answer, "kk"))

    def test_kazakh_with_isolated_russian_business_term_triggers_rewrite(
        self,
    ) -> None:
        answer = "Клиентпен ненавязчиво қарым-қатынас жасау маңызды."
        self.assertTrue(needs_language_rewrite(answer, "kk"))

    def test_clean_rewritten_kazakh_answer_no_rewrite(self) -> None:
        answer = (
            "Клиентке қызмет көрсетудің негізгі қағидалары қызмет сапасын, "
            "сыпайылық пен түсінікті қамтамасыз ететін клиентпен "
            "қарым-қатынастың ережелері мен нормаларын қамтиды. Оларға "
            "клиентті дұрыс қарсы алу, сұрақтар қою, қажетті өнімдер мен "
            "қызметтерді ұсыну, төлемді дұрыс жасау және клиентке алғыс "
            "білдіру кезеңдері кіреді. Қызмет көрсету барысында маман "
            "клиентпен сенімді түрде «Сіз» деп сөйлесуі, қолжетімді "
            "болуы, әдепті әрі ұқыпты қарым-қатынас орнатуы тиіс. "
            "Клиенттің қажеттілігін анықтау үшін ашық және нақты "
            "сұрақтар қолданылып, қажетті өнімдерді көрсету арқылы "
            "көмектесу маңызды. Сонымен қатар, егер бірнеше клиентпен "
            "қатар жұмыс істесеңіз, уақытылы басқа сатушыға бағыттау "
            "қажет. Бұл қағидалар клиентпен тиімді әрі сыйластық "
            "қатынас құруға мүмкіндік береді."
        )
        self.assertFalse(needs_language_rewrite(answer, "kk"))

    def test_kazakh_shared_cyrillic_words_without_kazakh_letters_no_rewrite(
        self,
    ) -> None:
        answer = (
            "Қызмет көрсету барысында маман клиентпен сенімді түрде "
            "қарым-қатынас орнатуы тиіс."
        )
        self.assertFalse(needs_language_rewrite(answer, "kk"))

    def test_kazakh_with_russian_function_word_sequence_triggers_rewrite(
        self,
    ) -> None:
        answer = (
            "Клиентке қызмет көрсету барысында необходимо обратиться "
            "к менеджеру."
        )
        self.assertTrue(needs_language_rewrite(answer, "kk"))

    def test_kazakh_with_legitimate_latin_brand_name_no_rewrite(self) -> None:
        answer = (
            "Intertop дүкенінде сатып алуды 14 күн ішінде рәсімдеуге болады."
        )
        self.assertFalse(needs_language_rewrite(answer, "kk"))

    def test_russian_answer_requested_as_kazakh_triggers_rewrite(self) -> None:
        answer = (
            "Необходимо обратиться к менеджеру для оформления возврата "
            "товара в течение четырнадцати дней."
        )
        self.assertTrue(needs_language_rewrite(answer, "kk"))

    def test_isolated_foreign_brand_does_not_trigger_rewrite(self) -> None:
        answer = (
            "Обратитесь в Intertop за помощью при оформлении возврата "
            "в течение 14 дней."
        )
        self.assertFalse(needs_language_rewrite(answer, "ru"))

    def test_isolated_latin_acronym_does_not_trigger_rewrite(self) -> None:
        answer = "Отправьте PDF с заявлением на возврат в течение 14 дней."
        self.assertFalse(needs_language_rewrite(answer, "ru"))

    def test_unsupported_language_never_triggers_rewrite(self) -> None:
        answer = "Plain answer text."
        self.assertFalse(needs_language_rewrite(answer, "de"))


class BuildLanguageRewritePromptTests(unittest.TestCase):
    """Tests for deterministic rewrite prompt construction."""

    def test_prompt_includes_target_language(self) -> None:
        prompt = build_language_rewrite_prompt("Answer text.", "kk")
        self.assertIn("Kazakh", prompt)
        self.assertIn("language code: kk", prompt)

    def test_prompt_includes_original_answer(self) -> None:
        answer = "Mixed language answer."
        prompt = build_language_rewrite_prompt(answer, "en")
        self.assertIn(answer, prompt)

    def test_prompt_requires_plain_text_only(self) -> None:
        prompt = build_language_rewrite_prompt("Answer.", "ru")
        self.assertIn("Return ONLY the rewritten answer text.", prompt)
        self.assertIn("Do not return JSON", prompt)

    def test_kazakh_prompt_forbids_ordinary_russian_leakage(self) -> None:
        prompt = build_language_rewrite_prompt("Answer text.", "kk")
        self.assertIn("Write the entire answer in natural Kazakh.", prompt)
        self.assertIn(
            "Do not leave ordinary Russian words, Russian adverbs, "
            "Russian workflow terms, Russian business terminology, or "
            "Russian explanatory phrases in the answer.",
            prompt,
        )
        self.assertIn("ненавязчиво", prompt)
        self.assertIn("спрашивай", prompt)
        self.assertIn("благодари", prompt)
        self.assertIn("возврат", prompt)
        self.assertIn("оформление", prompt)

    def test_kazakh_prompt_requires_translating_ordinary_russian_terms(self) -> None:
        prompt = build_language_rewrite_prompt("Answer text.", "kk")
        self.assertIn(
            "Translate such terms into natural Kazakh equivalents.",
            prompt,
        )
        self.assertIn(
            "Do not copy Russian text from source documents merely because "
            "it appears in the source.",
            prompt,
        )

    def test_kazakh_prompt_requires_final_review_for_leakage(self) -> None:
        prompt = build_language_rewrite_prompt("Answer text.", "kk")
        self.assertIn(
            "Before returning, internally review the rewritten answer "
            "and remove any remaining ordinary Russian or English words.",
            prompt,
        )

    def test_russian_prompt_does_not_include_kazakh_specific_rules(self) -> None:
        prompt = build_language_rewrite_prompt("Answer text.", "ru")
        self.assertNotIn("Write the entire answer in natural Kazakh.", prompt)
        self.assertNotIn("ненавязчиво", prompt)

    def test_english_prompt_does_not_include_kazakh_specific_rules(self) -> None:
        prompt = build_language_rewrite_prompt("Answer text.", "en")
        self.assertNotIn("Write the entire answer in natural Kazakh.", prompt)
        self.assertNotIn("ненавязчиво", prompt)


class KnowledgeAnswerLanguageGuardTests(unittest.TestCase):
    """Tests for guard enforcement behavior."""

    def test_compliant_answer_returns_same_result(self) -> None:
        provider = MagicMock()
        guard = KnowledgeAnswerLanguageGuard(provider)
        result = _result("Возврат оформляется в течение 14 дней.")

        enforced = guard.enforce(result, "ru")

        self.assertIs(enforced, result)
        provider.generate.assert_not_called()

    def test_homoglyph_normalization_without_rewrite(self) -> None:
        provider = MagicMock()
        guard = KnowledgeAnswerLanguageGuard(provider)
        original = _result("Проверьте контрol качества перед открытием смены.")

        enforced = guard.enforce(original, "ru")

        provider.generate.assert_not_called()
        self.assertEqual(
            enforced.answer,
            "Проверьте контрол качества перед открытием смены.",
        )
        self.assertEqual(enforced.citations, original.citations)

    def test_violation_triggers_single_rewrite(self) -> None:
        provider = MagicMock()
        provider.generate.return_value = (
            "Қайтаруды рәсімдеу үшін басшыға хабарласыңыз."
        )
        guard = KnowledgeAnswerLanguageGuard(provider)
        original = _result(
            "Необходимо обратиться к менеджеру для оформления возврата."
        )

        enforced = guard.enforce(original, "kk")

        provider.generate.assert_called_once()
        self.assertEqual(
            enforced.answer,
            "Қайтаруды рәсімдеу үшін басшыға хабарласыңыз.",
        )
        self.assertEqual(enforced.citations, original.citations)
        self.assertEqual(enforced.sufficient_context, original.sufficient_context)

    def test_rewrite_preserves_citations_and_sufficient_context(self) -> None:
        provider = MagicMock()
        provider.generate.return_value = (
            "Клиент должен немедленно обратиться к менеджеру."
        )
        guard = KnowledgeAnswerLanguageGuard(provider)
        original = KnowledgeAnswerResult(
            answer="Клиент должен contact manager immediately.",
            citations=(
                KnowledgeAnswerCitation(1, "doc-a", 0),
                KnowledgeAnswerCitation(2, "doc-b", 3),
            ),
            sufficient_context=True,
        )

        enforced = guard.enforce(original, "ru")

        self.assertEqual(enforced.citations, original.citations)
        self.assertTrue(enforced.sufficient_context)

    def test_non_compliant_rewrite_raises_error_without_second_rewrite(
        self,
    ) -> None:
        provider = MagicMock()
        provider.generate.return_value = (
            "Клиентпен ненавязчиво қарым-қатынас жасау маңызды."
        )
        guard = KnowledgeAnswerLanguageGuard(provider)
        original = _result(
            "Необходимо обратиться к менеджеру для оформления возврата."
        )

        with self.assertRaises(KnowledgeAnswerLanguageRewriteError) as context:
            guard.enforce(original, "kk")

        self.assertEqual(
            context.exception.message,
            "Failed to rewrite knowledge answer for language compliance.",
        )
        provider.generate.assert_called_once()

    def test_rewrite_provider_failure_raises_rewrite_error(self) -> None:
        provider = MagicMock()
        provider.generate.side_effect = RuntimeError("provider down")
        guard = KnowledgeAnswerLanguageGuard(provider)
        original = _result("Клиент должен contact manager immediately.")

        with self.assertRaises(KnowledgeAnswerLanguageRewriteError) as context:
            guard.enforce(original, "ru")

        self.assertEqual(
            context.exception.message,
            "Failed to rewrite knowledge answer for language compliance.",
        )
        self.assertIsInstance(context.exception.__cause__, RuntimeError)

    def test_empty_rewrite_response_raises_rewrite_error(self) -> None:
        provider = MagicMock()
        provider.generate.return_value = "   "
        guard = KnowledgeAnswerLanguageGuard(provider)
        original = _result("Клиент должен contact manager immediately.")

        with self.assertRaises(KnowledgeAnswerLanguageRewriteError):
            guard.enforce(original, "ru")


class KnowledgeAnswerServiceLanguageGuardIntegrationTests(unittest.TestCase):
    """Integration tests for language guard inside answer service."""

    def _request(self, language: str = "ru") -> KnowledgeAnswerRequest:
        return KnowledgeAnswerRequest(
            question="Question?",
            context=_context(sources=(_source(),)),
            language=language,
        )

    def test_clean_answer_calls_provider_once(self) -> None:
        provider = MagicMock()
        provider.generate.return_value = '{"answer":"ok"}'
        service = KnowledgeAnswerService(provider=provider)
        parsed = _result("Возврат оформляется в течение 14 дней.")
        service._response_parser = MagicMock(parse=MagicMock(return_value=parsed))
        service._validator = MagicMock(validate=MagicMock(return_value=parsed))

        service.answer(self._request(language="ru"))

        self.assertEqual(provider.generate.call_count, 1)

    def test_language_violation_calls_provider_twice(self) -> None:
        provider = MagicMock()
        compliant_kazakh = (
            "Қайтаруды рәсімдеу үшін басшыға хабарласыңыз."
        )
        provider.generate.side_effect = [
            '{"answer":"ok"}',
            compliant_kazakh,
        ]
        service = KnowledgeAnswerService(provider=provider)
        violating = _result(
            "Необходимо обратиться к менеджеру для оформления возврата."
        )
        service._response_parser = MagicMock(
            parse=MagicMock(return_value=violating)
        )
        service._validator = MagicMock(validate=MagicMock(return_value=violating))

        result = service.answer(self._request(language="kk"))

        self.assertEqual(provider.generate.call_count, 2)
        self.assertEqual(result.answer, compliant_kazakh)
        self.assertEqual(result.citations, violating.citations)
        self.assertTrue(result.sufficient_context)

    def test_non_compliant_rewrite_wrapped_as_generation_error(self) -> None:
        provider = MagicMock()
        provider.generate.side_effect = [
            '{"answer":"ok"}',
            "Клиентпен ненавязчиво қарым-қатынас жасау маңызды.",
        ]
        service = KnowledgeAnswerService(provider=provider)
        violating = _result(
            "Необходимо обратиться к менеджеру для оформления возврата."
        )
        service._response_parser = MagicMock(
            parse=MagicMock(return_value=violating)
        )
        service._validator = MagicMock(validate=MagicMock(return_value=violating))

        with self.assertRaises(KnowledgeAnswerGenerationError) as context:
            service.answer(self._request(language="kk"))

        self.assertEqual(
            context.exception.message,
            "Failed to rewrite knowledge answer for language compliance.",
        )
        self.assertEqual(provider.generate.call_count, 2)

    def test_rewrite_failure_wrapped_as_generation_error(self) -> None:
        provider = MagicMock()
        provider.generate.side_effect = [
            '{"answer":"ok"}',
            RuntimeError("rewrite failed"),
        ]
        service = KnowledgeAnswerService(provider=provider)
        violating = _result("Клиент должен contact manager immediately.")
        service._response_parser = MagicMock(
            parse=MagicMock(return_value=violating)
        )
        service._validator = MagicMock(validate=MagicMock(return_value=violating))

        with self.assertRaises(KnowledgeAnswerGenerationError) as context:
            service.answer(self._request(language="ru"))

        self.assertEqual(
            context.exception.message,
            "Failed to rewrite knowledge answer for language compliance.",
        )
        self.assertEqual(provider.generate.call_count, 2)

    def test_disabled_language_guard_skips_rewrite(self) -> None:
        provider = MagicMock()
        provider.generate.return_value = '{"answer":"ok"}'
        service = KnowledgeAnswerService(provider=provider, language_guard=None)
        violating = _result("Клиент должен contact manager immediately.")
        service._response_parser = MagicMock(
            parse=MagicMock(return_value=violating)
        )
        service._validator = MagicMock(validate=MagicMock(return_value=violating))

        result = service.answer(self._request(language="ru"))

        self.assertEqual(provider.generate.call_count, 1)
        self.assertEqual(result.answer, violating.answer)

    def test_custom_language_guard_dependency_is_used(self) -> None:
        provider = MagicMock()
        provider.generate.return_value = '{"answer":"ok"}'
        custom_guard = MagicMock()
        custom_guard.enforce.side_effect = lambda result, language: KnowledgeAnswerResult(
            answer="Custom guarded answer.",
            citations=result.citations,
            sufficient_context=result.sufficient_context,
        )
        service = KnowledgeAnswerService(
            provider=provider,
            language_guard=custom_guard,
        )
        parsed = _result("Возврат оформляется в течение 14 дней.")
        service._response_parser = MagicMock(parse=MagicMock(return_value=parsed))
        service._validator = MagicMock(validate=MagicMock(return_value=parsed))

        result = service.answer(self._request(language="ru"))

        custom_guard.enforce.assert_called_once_with(parsed, "ru")
        self.assertEqual(result.answer, "Custom guarded answer.")


if __name__ == "__main__":
    unittest.main()
