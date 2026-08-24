"""Employee learning analytics for manager Web views."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Optional

from app.content.runtime import ContentRuntime


@dataclass(frozen=True)
class EmployeeCourseQuizAnalytics:
    slug: str
    title: str
    attempts_count: int
    best_score_percent: float
    average_score_percent: float
    latest_score_percent: float
    latest_passed: bool
    ever_passed: bool


@dataclass(frozen=True)
class EmployeeQuizAnalytics:
    total_attempts_count: int
    tested_courses_count: int
    passed_courses_count: int
    latest_failed_courses_count: int
    best_score_percent: Optional[float]
    average_score_percent: Optional[float]
    courses: tuple[EmployeeCourseQuizAnalytics, ...]


@dataclass(frozen=True)
class EmployeeQuizTopicAnalytics:
    tag: str
    answers_count: int
    correct_answers_count: int
    accuracy_percent: float


@dataclass(frozen=True)
class EmployeeQuizTopicsAnalytics:
    total_tagged_answers_count: int
    topics: tuple[EmployeeQuizTopicAnalytics, ...]


class ManagerEmployeeAnalyticsService:
    """Build quiz analytics for one canonical employee."""

    def __init__(
        self,
        runtime: ContentRuntime,
        quiz_repository: ModuleType,
        db_path: Path,
    ) -> None:
        self._runtime = runtime
        self._quiz_repository = quiz_repository
        self._db_path = db_path

    def get_quiz_analytics(self, user_id: int) -> EmployeeQuizAnalytics:
        normalized_user_id = _validate_user_id(user_id)

        courses = []
        total_attempts = 0
        weighted_score_total = 0.0
        for course in self._runtime.get_courses():
            stats = self._quiz_repository.get_course_quiz_stats_for_user(
                self._db_path,
                normalized_user_id,
                course.slug,
            )

            attempts_count = int(stats["attempts_count"])
            if attempts_count == 0:
                continue

            average_score = float(stats["average_score_percent"])
            total_attempts += attempts_count
            weighted_score_total += average_score * attempts_count

            courses.append(
                EmployeeCourseQuizAnalytics(
                    slug=course.slug,
                    title=course.title,
                    attempts_count=attempts_count,
                    best_score_percent=float(stats["best_score_percent"]),
                    average_score_percent=average_score,
                    latest_score_percent=float(stats["latest_score_percent"]),
                    latest_passed=bool(stats["latest_passed"]),
                    ever_passed=bool(stats["ever_passed"]),
                )
            )

        return EmployeeQuizAnalytics(
            total_attempts_count=total_attempts,
            tested_courses_count=len(courses),
            passed_courses_count=sum(course.ever_passed for course in courses),
            latest_failed_courses_count=sum(
                not course.latest_passed for course in courses
            ),
            best_score_percent=(
                max(course.best_score_percent for course in courses)
                if courses
                else None
            ),
            average_score_percent=(
                round(weighted_score_total / total_attempts, 2)
                if total_attempts
                else None
            ),
            courses=tuple(courses),
        )

    def get_quiz_topics_analytics(self, user_id: int) -> EmployeeQuizTopicsAnalytics:
        normalized_user_id = _validate_user_id(user_id)

        tag_stats: dict[str, dict[str, int]] = {}
        total_tagged_answers_count = 0

        for course in self._runtime.get_courses():
            quiz = course.quiz
            if quiz is None:
                continue

            questions_by_id = {question.id: question for question in quiz.questions}
            answers = self._quiz_repository.get_finished_answers_for_user(
                self._db_path,
                normalized_user_id,
                course.slug,
            )

            for answer in answers:
                question = questions_by_id.get(answer["question_id"])
                if question is None:
                    continue

                normalized_tags = _normalize_question_tags(question.tags)
                if not normalized_tags:
                    continue

                is_correct = bool(int(answer["is_correct"]))
                for tag in normalized_tags:
                    stats = tag_stats.setdefault(
                        tag,
                        {"answers_count": 0, "correct_answers_count": 0},
                    )
                    stats["answers_count"] += 1
                    if is_correct:
                        stats["correct_answers_count"] += 1
                    total_tagged_answers_count += 1

        topics = tuple(
            _build_topic_analytics(tag, stats)
            for tag, stats in sorted(
                tag_stats.items(),
                key=lambda item: (
                    -_topic_accuracy_percent(item[1]),
                    -item[1]["answers_count"],
                    item[0].casefold(),
                    item[0],
                ),
            )
        )

        return EmployeeQuizTopicsAnalytics(
            total_tagged_answers_count=total_tagged_answers_count,
            topics=topics,
        )


def _normalize_question_tags(tags: list[str]) -> set[str]:
    normalized_tags: set[str] = set()
    for tag in tags:
        if not isinstance(tag, str):
            continue
        stripped = tag.strip()
        if stripped:
            normalized_tags.add(stripped)
    return normalized_tags


def _topic_accuracy_percent(stats: dict[str, int]) -> float:
    answers_count = stats["answers_count"]
    if answers_count == 0:
        return 0.0
    return round(stats["correct_answers_count"] * 100 / answers_count, 2)


def _build_topic_analytics(
    tag: str,
    stats: dict[str, int],
) -> EmployeeQuizTopicAnalytics:
    answers_count = stats["answers_count"]
    correct_answers_count = stats["correct_answers_count"]
    return EmployeeQuizTopicAnalytics(
        tag=tag,
        answers_count=answers_count,
        correct_answers_count=correct_answers_count,
        accuracy_percent=_topic_accuracy_percent(stats),
    )


def _validate_user_id(user_id: int) -> int:
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        raise ValueError("user_id must be an integer")
    if user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    return user_id
