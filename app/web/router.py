"""Read-only Web UI routes backed by ContentRuntime."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.mappers import course_mapper
from app.content.runtime import ContentRuntime

router = APIRouter(tags=["web"])

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))


def get_content_runtime(request: Request) -> ContentRuntime:
    """Return the ContentRuntime instance attached to the application."""
    return request.app.state.content_runtime


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Redirect the site root to the course catalog."""
    return RedirectResponse(url="/courses", status_code=302)


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
    return templates.TemplateResponse(
        request,
        "course_detail.html",
        {"course": course_detail},
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
