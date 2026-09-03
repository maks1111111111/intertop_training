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


@dataclass(frozen=True)
class EmployeeQuizTopicClassification:
    strengths: tuple[EmployeeQuizTopicAnalytics, ...]
    development_areas: tuple[EmployeeQuizTopicAnalytics, ...]
    unclassified_topics_count: int


@dataclass(frozen=True)
class EmployeeQuizTopicCourseEvidence:
    course_slug: str
    course_title: str
    answers_count: int
    correct_answers_count: int
    accuracy_percent: float


@dataclass(frozen=True)
class EmployeeQuizTopicEvidence:
    tag: str
    courses: tuple[EmployeeQuizTopicCourseEvidence, ...]


@dataclass(frozen=True)
class EmployeePracticalTaskAttemptAnalytics:
    attempt_id: int
    course_slug: str
    course_title: str
    lesson_slug: str
    lesson_title: str
    task_title: str
    status: str
    score: Optional[int]
    max_score: Optional[int]
    score_percent: Optional[float]
    passed: Optional[bool]
    feedback_summary: Optional[str]
    strengths: tuple[str, ...]
    improvements: tuple[str, ...]
    started_at: str
    reviewed_at: Optional[str]


@dataclass(frozen=True)
class EmployeePracticalSignal:
    text: str
    evidence_count: int


@dataclass(frozen=True)
class EmployeePracticalSignalEvidence:
    text: str
    evidence_count: int


@dataclass(frozen=True)
class EmployeePracticalSignalEvidenceSet:
    strengths: tuple[EmployeePracticalSignalEvidence, ...]
    development_areas: tuple[EmployeePracticalSignalEvidence, ...]
    reviewed_attempts_count: int


@dataclass(frozen=True)
class EmployeeDevelopmentProfile:
    quiz_strengths: tuple[EmployeeQuizTopicAnalytics, ...]
    quiz_development_areas: tuple[EmployeeQuizTopicAnalytics, ...]
    practical_strengths: tuple[EmployeePracticalSignal, ...]
    practical_development_areas: tuple[EmployeePracticalSignal, ...]
    reviewed_practical_attempts_count: int
    has_sufficient_practical_evidence: bool
    quiz_strength_evidence: tuple[EmployeeQuizTopicEvidence, ...] = ()
    quiz_development_evidence: tuple[EmployeeQuizTopicEvidence, ...] = ()


@dataclass(frozen=True)
class EmployeePracticalTaskAnalytics:
    total_attempts_count: int
    reviewed_attempts_count: int
    passed_attempts_count: int
    failed_attempts_count: int
    pending_attempts_count: int
    scorable_attempts_count: int
    average_score_percent: Optional[float]
    best_score_percent: Optional[float]
    recent_attempts: tuple[EmployeePracticalTaskAttemptAnalytics, ...]


MIN_TOPIC_ANSWERS = 3
STRONG_TOPIC_ACCURACY_PERCENT = 80.0
DEVELOPMENT_TOPIC_ACCURACY_PERCENT = 70.0
MIN_PRACTICAL_SIGNAL_OCCURRENCES = 2


@dataclass
class _QuizTopicAggregation:
    tag_stats: dict[str, dict[str, int]]
    course_tag_stats: dict[str, dict[str, dict[str, int]]]
    course_titles: dict[str, str]
    total_tagged_answers_count: int


class ManagerEmployeeAnalyticsService:
    """Build quiz analytics for one canonical employee."""

    def __init__(
        self,
        runtime: ContentRuntime,
        quiz_repository: ModuleType,
        db_path: Path,
        practical_task_attempt_repository: Optional[ModuleType] = None,
    ) -> None:
        self._runtime = runtime
        self._quiz_repository = quiz_repository
        self._db_path = db_path
        if practical_task_attempt_repository is None:
            from app.repositories import practical_task_attempt_repository as default_repo

            practical_task_attempt_repository = default_repo
        self._practical_task_attempt_repository = practical_task_attempt_repository

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
        aggregation = self._aggregate_quiz_topic_data(normalized_user_id)
        return _build_quiz_topics_analytics(aggregation)

    def get_quiz_topic_classification(
        self,
        user_id: int,
    ) -> EmployeeQuizTopicClassification:
        _validate_user_id(user_id)
        topic_analytics = self.get_quiz_topics_analytics(user_id)
        return _build_quiz_topic_classification(topic_analytics)

    def get_practical_task_analytics(
        self,
        user_id: int,
        limit: int = 10,
    ) -> EmployeePracticalTaskAnalytics:
        normalized_user_id = _validate_user_id(user_id)
        normalized_limit = _validate_recent_attempts_limit(limit)

        aggregate = (
            self._practical_task_attempt_repository.get_attempts_aggregate_for_user(
                self._db_path,
                normalized_user_id,
            )
        )
        recent_rows = self._practical_task_attempt_repository.get_attempts_for_user(
            self._db_path,
            normalized_user_id,
            limit=normalized_limit,
        )
        course_titles, lesson_titles = _build_course_lesson_title_maps(self._runtime)

        recent_attempts = tuple(
            _build_practical_task_attempt_analytics(
                attempt,
                course_titles,
                lesson_titles,
            )
            for attempt in recent_rows
        )

        return EmployeePracticalTaskAnalytics(
            total_attempts_count=aggregate.total_attempts_count,
            reviewed_attempts_count=aggregate.reviewed_attempts_count,
            passed_attempts_count=aggregate.passed_attempts_count,
            failed_attempts_count=aggregate.failed_attempts_count,
            pending_attempts_count=aggregate.pending_attempts_count,
            scorable_attempts_count=aggregate.scorable_attempts_count,
            average_score_percent=aggregate.average_score_percent,
            best_score_percent=aggregate.best_score_percent,
            recent_attempts=recent_attempts,
        )

    def get_practical_signal_evidence(
        self,
        user_id: int,
    ) -> EmployeePracticalSignalEvidenceSet:
        normalized_user_id = _validate_user_id(user_id)
        feedback_rows = (
            self._practical_task_attempt_repository.get_reviewed_feedback_for_user(
                self._db_path,
                normalized_user_id,
            )
        )

        return EmployeePracticalSignalEvidenceSet(
            strengths=_collect_practical_signal_evidence(feedback_rows, "strengths"),
            development_areas=_collect_practical_signal_evidence(
                feedback_rows,
                "improvements",
            ),
            reviewed_attempts_count=len(feedback_rows),
        )

    def get_development_profile(self, user_id: int) -> EmployeeDevelopmentProfile:
        normalized_user_id = _validate_user_id(user_id)
        aggregation = self._aggregate_quiz_topic_data(normalized_user_id)
        topic_analytics = _build_quiz_topics_analytics(aggregation)
        topic_classification = _build_quiz_topic_classification(topic_analytics)
        signal_evidence = self.get_practical_signal_evidence(normalized_user_id)

        return EmployeeDevelopmentProfile(
            quiz_strengths=topic_classification.strengths,
            quiz_development_areas=topic_classification.development_areas,
            practical_strengths=_filter_recurring_practical_signals(
                signal_evidence.strengths,
            ),
            practical_development_areas=_filter_recurring_practical_signals(
                signal_evidence.development_areas,
            ),
            reviewed_practical_attempts_count=(
                signal_evidence.reviewed_attempts_count
            ),
            has_sufficient_practical_evidence=(
                signal_evidence.reviewed_attempts_count
                >= MIN_PRACTICAL_SIGNAL_OCCURRENCES
            ),
            quiz_strength_evidence=_build_quiz_topic_evidence(
                aggregation,
                topic_classification.strengths,
            ),
            quiz_development_evidence=_build_quiz_topic_evidence(
                aggregation,
                topic_classification.development_areas,
            ),
        )

    def _aggregate_quiz_topic_data(self, normalized_user_id: int) -> _QuizTopicAggregation:
        tag_stats: dict[str, dict[str, int]] = {}
        course_tag_stats: dict[str, dict[str, dict[str, int]]] = {}
        course_titles: dict[str, str] = {}
        total_tagged_answers_count = 0

        for course in self._runtime.get_courses():
            course_titles[course.slug] = getattr(course, "title", course.slug)
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
                course_stats = course_tag_stats.setdefault(course.slug, {})
                for tag in normalized_tags:
                    stats = tag_stats.setdefault(
                        tag,
                        {"answers_count": 0, "correct_answers_count": 0},
                    )
                    stats["answers_count"] += 1
                    if is_correct:
                        stats["correct_answers_count"] += 1
                    total_tagged_answers_count += 1

                    course_tag = course_stats.setdefault(
                        tag,
                        {"answers_count": 0, "correct_answers_count": 0},
                    )
                    course_tag["answers_count"] += 1
                    if is_correct:
                        course_tag["correct_answers_count"] += 1

        return _QuizTopicAggregation(
            tag_stats=tag_stats,
            course_tag_stats=course_tag_stats,
            course_titles=course_titles,
            total_tagged_answers_count=total_tagged_answers_count,
        )


def _normalize_practical_signal(text: object) -> Optional[str]:
    if not isinstance(text, str):
        return None
    normalized = " ".join(text.split())
    if not normalized:
        return None
    return normalized


def _collect_practical_signal_evidence(
    feedback_rows,
    field: str,
) -> tuple[EmployeePracticalSignalEvidence, ...]:
    evidence: dict[str, dict[str, object]] = {}

    for row in feedback_rows:
        signals_in_attempt: set[str] = set()
        for item in getattr(row, field):
            normalized = _normalize_practical_signal(item)
            if normalized is None:
                continue

            signal_key = normalized.casefold()
            if signal_key in signals_in_attempt:
                continue

            signals_in_attempt.add(signal_key)
            if signal_key not in evidence:
                evidence[signal_key] = {"display": normalized, "count": 0}
            evidence[signal_key]["count"] = int(evidence[signal_key]["count"]) + 1

    return tuple(
        sorted(
            (
                EmployeePracticalSignalEvidence(
                    text=str(info["display"]),
                    evidence_count=int(info["count"]),
                )
                for info in evidence.values()
            ),
            key=lambda signal: (
                -signal.evidence_count,
                signal.text.casefold(),
                signal.text,
            ),
        )
    )


def _filter_recurring_practical_signals(
    evidence: tuple[EmployeePracticalSignalEvidence, ...],
) -> tuple[EmployeePracticalSignal, ...]:
    return tuple(
        EmployeePracticalSignal(
            text=signal.text,
            evidence_count=signal.evidence_count,
        )
        for signal in evidence
        if signal.evidence_count >= MIN_PRACTICAL_SIGNAL_OCCURRENCES
    )


def _validate_recent_attempts_limit(limit: int) -> int:
    if not isinstance(limit, int) or isinstance(limit, bool) or limit <= 0:
        raise ValueError("limit must be a positive integer")
    return limit


def _build_course_lesson_title_maps(
    runtime: ContentRuntime,
) -> tuple[dict[str, str], dict[tuple[str, str], str]]:
    course_titles: dict[str, str] = {}
    lesson_titles: dict[tuple[str, str], str] = {}

    for course in runtime.get_courses():
        course_titles[course.slug] = course.title
        for lesson in getattr(course, "lessons", ()):
            lesson_titles[(course.slug, lesson.path.name)] = lesson.title

    return course_titles, lesson_titles


def _attempt_score_percent(attempt) -> Optional[float]:
    if attempt.score is None or attempt.max_score is None:
        return None
    if attempt.max_score <= 0:
        return None
    return round(attempt.score * 100 / attempt.max_score, 2)


def _build_practical_task_attempt_analytics(
    attempt,
    course_titles: dict[str, str],
    lesson_titles: dict[tuple[str, str], str],
) -> EmployeePracticalTaskAttemptAnalytics:
    course_title = course_titles.get(attempt.course_slug, attempt.course_slug)
    lesson_title = lesson_titles.get(
        (attempt.course_slug, attempt.lesson_slug),
        attempt.lesson_slug,
    )
    return EmployeePracticalTaskAttemptAnalytics(
        attempt_id=attempt.id,
        course_slug=attempt.course_slug,
        course_title=course_title,
        lesson_slug=attempt.lesson_slug,
        lesson_title=lesson_title,
        task_title=attempt.task_title,
        status=attempt.status,
        score=attempt.score,
        max_score=attempt.max_score,
        score_percent=_attempt_score_percent(attempt),
        passed=attempt.passed,
        feedback_summary=attempt.feedback_summary,
        strengths=attempt.strengths,
        improvements=attempt.improvements,
        started_at=attempt.started_at,
        reviewed_at=attempt.reviewed_at,
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


def _build_quiz_topic_classification(
    topic_analytics: EmployeeQuizTopicsAnalytics,
) -> EmployeeQuizTopicClassification:
    strengths: list[EmployeeQuizTopicAnalytics] = []
    development_areas: list[EmployeeQuizTopicAnalytics] = []
    unclassified_topics_count = 0

    for topic in topic_analytics.topics:
        if topic.answers_count < MIN_TOPIC_ANSWERS:
            unclassified_topics_count += 1
            continue

        if topic.accuracy_percent >= STRONG_TOPIC_ACCURACY_PERCENT:
            strengths.append(topic)
        elif topic.accuracy_percent < DEVELOPMENT_TOPIC_ACCURACY_PERCENT:
            development_areas.append(topic)
        else:
            unclassified_topics_count += 1

    return EmployeeQuizTopicClassification(
        strengths=tuple(
            sorted(
                strengths,
                key=lambda topic: (
                    -topic.accuracy_percent,
                    -topic.answers_count,
                    topic.tag.casefold(),
                    topic.tag,
                ),
            )
        ),
        development_areas=tuple(
            sorted(
                development_areas,
                key=lambda topic: (
                    topic.accuracy_percent,
                    -topic.answers_count,
                    topic.tag.casefold(),
                    topic.tag,
                ),
            )
        ),
        unclassified_topics_count=unclassified_topics_count,
    )


def _build_quiz_topics_analytics(
    aggregation: _QuizTopicAggregation,
) -> EmployeeQuizTopicsAnalytics:
    topics = tuple(
        _build_topic_analytics(tag, stats)
        for tag, stats in sorted(
            aggregation.tag_stats.items(),
            key=lambda item: (
                -_topic_accuracy_percent(item[1]),
                -item[1]["answers_count"],
                item[0].casefold(),
                item[0],
            ),
        )
    )

    return EmployeeQuizTopicsAnalytics(
        total_tagged_answers_count=aggregation.total_tagged_answers_count,
        topics=topics,
    )


def _build_quiz_topic_evidence(
    aggregation: _QuizTopicAggregation,
    topics: tuple[EmployeeQuizTopicAnalytics, ...],
) -> tuple[EmployeeQuizTopicEvidence, ...]:
    evidence_items: list[EmployeeQuizTopicEvidence] = []

    for topic in topics:
        course_evidences: list[EmployeeQuizTopicCourseEvidence] = []
        for course_slug, tag_stats in aggregation.course_tag_stats.items():
            stats = tag_stats.get(topic.tag)
            if stats is None or stats["answers_count"] == 0:
                continue

            course_evidences.append(
                EmployeeQuizTopicCourseEvidence(
                    course_slug=course_slug,
                    course_title=aggregation.course_titles.get(
                        course_slug,
                        course_slug,
                    ),
                    answers_count=stats["answers_count"],
                    correct_answers_count=stats["correct_answers_count"],
                    accuracy_percent=_topic_accuracy_percent(stats),
                )
            )

        evidence_items.append(
            EmployeeQuizTopicEvidence(
                tag=topic.tag,
                courses=tuple(
                    sorted(
                        course_evidences,
                        key=lambda course: (
                            -course.answers_count,
                            course.course_title.casefold(),
                            course.course_slug,
                        ),
                    )
                ),
            )
        )

    return tuple(evidence_items)


def _validate_user_id(user_id: int) -> int:
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        raise ValueError("user_id must be an integer")
    if user_id <= 0:
        raise ValueError("user_id must be a positive integer")
    return user_id
