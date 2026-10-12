"""Published course material as tenant-scoped Knowledge Base sources."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.content.runtime_loader import Course, Lesson
from app.knowledge.course_sources import PublishedCourseKnowledgeSource
from app.knowledge.retrieval import KnowledgeChunkRetrievalService


class _FakeRuntime:
    def __init__(self, courses: list[Course]) -> None:
        self._courses = courses

    def get_courses(self) -> list[Course]:
        return list(self._courses)


def _lesson() -> Lesson:
    return Lesson(
        path=Path("lesson-returns"),
        number=1,
        title="Оформление возврата",
        description="Перед возвратом сотрудник проверяет чек и состояние товара.",
        image_path=None,
        narration_path=None,
        practical_task="Объясните клиенту порядок возврата товара.",
        checklist=("Проверить чек", "Проверить товар"),
        common_mistakes=("Не обещать возврат без проверки чека",),
        key_takeaways=("Сначала проверяем покупку и товар",),
        application_tips=("Сохраняйте спокойный тон",),
    )


def _course(*, status: str = "published") -> Course:
    return Course(
        slug="returns",
        title="Возвраты товаров",
        status=status,
        version=1,
        lessons=[_lesson()],
        cover_path=None,
        quiz=None,
        description="Стандарты обработки возврата товара.",
    )


class PublishedCourseKnowledgeSourceTests(unittest.TestCase):
    def test_published_course_and_lessons_become_searchable_chunks(self) -> None:
        source = PublishedCourseKnowledgeSource(_FakeRuntime([_course()]))

        chunks = source.list_chunks(Path("unused.db"), "company-a")

        self.assertEqual([chunk.chunk_index for chunk in chunks], [0, 1])
        self.assertTrue(all(chunk.company_id == "company-a" for chunk in chunks))
        self.assertTrue(all(chunk.document_id == "course:returns" for chunk in chunks))
        self.assertIn("Возвраты товаров", chunks[0].text)
        self.assertIn("Проверить чек", chunks[1].text)
        self.assertIn("Не обещать возврат", chunks[1].text)

    def test_archived_course_is_not_exposed_to_knowledge_search(self) -> None:
        source = PublishedCourseKnowledgeSource(_FakeRuntime([_course(status="archived")]))

        self.assertEqual(source.list_chunks(Path("unused.db"), "company-a"), ())

    def test_retrieval_ranks_lesson_text_without_duplicate_database_document(self) -> None:
        source = PublishedCourseKnowledgeSource(_FakeRuntime([_course()]))
        retrieval = KnowledgeChunkRetrievalService(
            chunk_loader=lambda _db_path, company_id: (),
            course_chunk_loader=source.list_chunks,
        )

        results = retrieval.search(
            Path("unused.db"),
            company_id="company-a",
            query="как проверить чек при возврате",
        )

        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].chunk.document_id, "course:returns")
        self.assertEqual(results[0].chunk.chunk_index, 1)

    def test_source_links_to_the_course_page(self) -> None:
        source = PublishedCourseKnowledgeSource(_FakeRuntime([_course()]))

        resolved = source.get_source("company-a", "course:returns")

        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved.title, "Курс: Возвраты товаров")
        self.assertEqual(resolved.view_url, "/courses/returns")


if __name__ == "__main__":
    unittest.main()
