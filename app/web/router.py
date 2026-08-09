"""Read-only Web UI routes backed by ContentRuntime."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.mappers import course_mapper
from app.content.runtime import ContentRuntime
from app.repositories import quiz_repository
from app.repositories.progress_repository import ProgressRepository
from app.web.admin_service import AdminService
from app.web.dashboard_service import DashboardService
from app.web.progress_service import WebProgressService
from app.web.quiz_scoring import (
    build_quiz_page_view,
    build_quiz_summary_view,
    format_score_percent,
    score_web_quiz,
)

router = APIRouter(tags=["web"])

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def get_content_runtime(request: Request) -> ContentRuntime:
    """Return the ContentRuntime instance attached to the application."""
    return request.app.state.content_runtime


def get_db_path(request: Request) -> Path:
    """Return the SQLite database path attached to the application."""
    return request.app.state.db_path


def get_progress_service(db_path: Path = Depends(get_db_path)) -> WebProgressService:
    """Return the Web progress service for the current database."""
    return WebProgressService(db_path)


def get_dashboard_service(
    runtime: ContentRuntime = Depends(get_content_runtime),
    db_path: Path = Depends(get_db_path),
) -> DashboardService:
    """Return the dashboard service wired to the application runtime."""
    return DashboardService(
        runtime,
        ProgressRepository(),
        quiz_repository,
        db_path,
    )


def get_admin_service(
    runtime: ContentRuntime = Depends(get_content_runtime),
) -> AdminService:
    """Return the admin service wired to the application runtime."""
    return AdminService(runtime)


# TODO: Replace with authenticated web user identity when auth is implemented.
_WEB_DASHBOARD_TELEGRAM_ID = 1


def _parse_quiz_answers(form_data) -> dict[str, str]:
    """Extract question answers from submitted form fields."""
    answers: dict[str, str] = {}
    for key in form_data.keys():
        if not key.startswith("answer_"):
            continue
        answers[key[len("answer_"):]] = str(form_data[key])
    return answers


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Redirect the site root to the course catalog."""
    return RedirectResponse(url="/courses", status_code=302)


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
def dashboard_page(
    request: Request,
    dashboard_service: DashboardService = Depends(get_dashboard_service),
) -> HTMLResponse:
    """Render the student dashboard with course progress and quiz stats."""
    courses = dashboard_service.get_courses_for_user(_WEB_DASHBOARD_TELEGRAM_ID)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "active_nav": "dashboard",
            "courses": courses,
            "courses_count": len(courses),
        },
    )


@router.get("/admin", response_class=HTMLResponse, include_in_schema=False)
def admin_dashboard_page(
    request: Request,
    admin_service: AdminService = Depends(get_admin_service),
) -> HTMLResponse:
    """Render the admin course management dashboard."""
    courses = admin_service.get_courses()
    return templates.TemplateResponse(
        request,
        "admin_dashboard.html",
        {
            "active_nav": "admin",
            "courses": courses,
            "courses_count": len(courses),
        },
    )


@router.get(
    "/admin/courses/new",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def admin_course_create_page(
    request: Request,
    admin_service: AdminService = Depends(get_admin_service),
) -> HTMLResponse:
    """Render the first step of the course creation wizard."""
    create_view = admin_service.get_course_create_view()
    return templates.TemplateResponse(
        request,
        "admin_course_create.html",
        {
            "active_nav": "admin",
            "language_options": create_view.language_options,
        },
    )


@router.get("/courses", response_class=HTMLResponse, include_in_schema=False)
def courses_page(
    request: Request,
    content_runtime: ContentRuntime = Depends(get_content_runtime),
) -> HTMLResponse:
    """Render the published course catalog."""
    courses = content_runtime.get_courses()
    course_list = course_mapper.to_summary_list(courses)
    return templates.TemplateResponse(
        request,
        "courses.html",
        {
            "courses": course_list.items,
            "courses_count": len(course_list.items),
            "active_nav": "courses",
        },
    )


@router.get(
    "/courses/{slug}",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def course_detail_page(
    slug: str,
    request: Request,
    content_runtime: ContentRuntime = Depends(get_content_runtime),
    progress_service: WebProgressService = Depends(get_progress_service),
) -> HTMLResponse:
    """Render one published course and its lesson list."""
    course = content_runtime.get_course(slug)
    if course is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Курс не найден",
                "message": "Запрошенный курс недоступен или не существует.",
            },
            status_code=404,
        )

    course_detail = course_mapper.to_detail(course)
    progress = progress_service.build_course_progress_view(
        slug,
        course_detail.lessons,
        has_quiz=course.quiz is not None,
    )
    quiz_summary = None
    if course.quiz is not None:
        quiz_summary = build_quiz_summary_view(course.quiz)
    return templates.TemplateResponse(
        request,
        "course_detail.html",
        {
            "course": course_detail,
            "progress": progress,
            "quiz": quiz_summary,
        },
    )


@router.get(
    "/courses/{slug}/lessons/{lesson_id}",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def lesson_detail_page(
    slug: str,
    lesson_id: str,
    request: Request,
    content_runtime: ContentRuntime = Depends(get_content_runtime),
    progress_service: WebProgressService = Depends(get_progress_service),
) -> HTMLResponse:
    """Render one published lesson."""
    course = content_runtime.get_course(slug)
    if course is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Курс не найден",
                "message": "Запрошенный курс недоступен или не существует.",
            },
            status_code=404,
        )

    for lesson in course.lessons:
        if lesson.path.name == lesson_id:
            progress_service.mark_lesson_completed(slug, lesson_id)
            lesson_detail = course_mapper.to_lesson_detail(course, lesson)
            return templates.TemplateResponse(
                request,
                "lesson_detail.html",
                {
                    "course": course_mapper.to_detail(course),
                    "lesson": lesson_detail,
                },
            )

    return templates.TemplateResponse(
        request,
        "not_found.html",
        {
            "title": "Урок не найден",
            "message": "Запрошенный урок недоступен или не существует.",
        },
        status_code=404,
    )


@router.get(
    "/courses/{slug}/quiz",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def quiz_page(
    slug: str,
    request: Request,
    content_runtime: ContentRuntime = Depends(get_content_runtime),
) -> HTMLResponse:
    """Render the course quiz form."""
    course = content_runtime.get_course(slug)
    if course is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Курс не найден",
                "message": "Запрошенный курс недоступен или не существует.",
            },
            status_code=404,
        )

    if course.quiz is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Тест недоступен",
                "message": "Для этого курса итоговый тест пока недоступен.",
            },
            status_code=404,
        )

    quiz = build_quiz_page_view(course.quiz)
    return templates.TemplateResponse(
        request,
        "quiz.html",
        {
            "course": course_mapper.to_detail(course),
            "quiz": quiz,
        },
    )


@router.post(
    "/courses/{slug}/quiz",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def quiz_submit_page(
    slug: str,
    request: Request,
    content_runtime: ContentRuntime = Depends(get_content_runtime),
) -> HTMLResponse:
    """Score submitted quiz answers and render the result page."""
    course = content_runtime.get_course(slug)
    if course is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Курс не найден",
                "message": "Запрошенный курс недоступен или не существует.",
            },
            status_code=404,
        )

    if course.quiz is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Тест недоступен",
                "message": "Для этого курса итоговый тест пока недоступен.",
            },
            status_code=404,
        )

    form_data = await request.form()
    answers = _parse_quiz_answers(form_data)
    result = score_web_quiz(course.quiz, answers)

    return templates.TemplateResponse(
        request,
        "quiz_result.html",
        {
            "course": course_mapper.to_detail(course),
            "score_percent": format_score_percent(result.score_percent),
            "correct_answers": result.correct_answers,
            "questions_count": result.questions_count,
            "passing_score": result.passing_score,
            "passed": result.passed,
            "reviews": result.reviews,
        },
    )
