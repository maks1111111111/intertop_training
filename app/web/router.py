"""Read-only Web UI routes backed by ContentRuntime."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.mappers import course_mapper
from app.content.runtime import ContentRuntime
from app.repositories import quiz_repository
from app.repositories.progress_repository import ProgressRepository
from app.web.admin_course_edit_service import (
    AdminCourseEditError,
    AdminCourseEditRequest,
    AdminCourseEditService,
)
from app.web.admin_lesson_create_service import (
    AdminLessonCreateError,
    AdminLessonCreateService,
)
from app.web.admin_lesson_edit_service import (
    AdminLessonEditError,
    AdminLessonEditRequest,
    AdminLessonEditService,
    _parse_multiline_list,
)
from app.web.admin_service import AdminService
from app.web.admin_generation_service import (
    AdminGenerationError,
    AdminGenerationRequest,
    AdminGenerationService,
)
from app.web.admin_upload_service import (
    AdminCourseFormValues,
    AdminReviewError,
    AdminUploadError,
    AdminUploadService,
    build_generation_review_view,
    build_upload_confirm_view,
    parse_admin_course_form,
)
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


def get_upload_service(request: Request) -> AdminUploadService:
    """Return the admin upload service for the configured upload directory."""
    return AdminUploadService(request.app.state.upload_dir)


def get_admin_generation_service(
    request: Request,
    upload_service: AdminUploadService = Depends(get_upload_service),
    runtime: ContentRuntime = Depends(get_content_runtime),
) -> AdminGenerationService:
    """Return the admin generation service for the current application."""
    override = getattr(request.app.state, "admin_generation_service", None)
    if override is not None:
        return override
    return AdminGenerationService(
        upload_service=upload_service,
        courses_dir=runtime.base_dir,
        runtime=runtime,
    )


def get_admin_course_edit_service(
    runtime: ContentRuntime = Depends(get_content_runtime),
) -> AdminCourseEditService:
    """Return the admin course edit service for the current application."""
    return AdminCourseEditService(runtime.base_dir, runtime)


def get_admin_lesson_edit_service(
    runtime: ContentRuntime = Depends(get_content_runtime),
) -> AdminLessonEditService:
    """Return the admin lesson edit service for the current application."""
    return AdminLessonEditService(runtime.base_dir, runtime)


def get_admin_lesson_create_service(
    runtime: ContentRuntime = Depends(get_content_runtime),
) -> AdminLessonCreateService:
    """Return the admin lesson create service for the current application."""
    return AdminLessonCreateService(runtime.base_dir, runtime)


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


def _render_admin_course_create_page(
    request: Request,
    admin_service: AdminService,
    *,
    error_message: str = "",
) -> HTMLResponse:
    """Render the course creation wizard form."""
    create_view = admin_service.get_course_create_view()
    return templates.TemplateResponse(
        request,
        "admin_course_create.html",
        {
            "active_nav": "admin",
            "create_view": create_view,
            "error_message": error_message,
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
    return _render_admin_course_create_page(request, admin_service)


@router.post(
    "/admin/courses/new",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def admin_course_create_submit(
    request: Request,
    admin_service: AdminService = Depends(get_admin_service),
    upload_service: AdminUploadService = Depends(get_upload_service),
) -> HTMLResponse:
    """Validate and store an uploaded source file, then show confirmation."""
    form = await request.form()
    form_values = parse_admin_course_form(form)
    upload_file = form.get("source_file")

    filename = getattr(upload_file, "filename", None)
    if upload_file is None or not filename:
        return _render_admin_course_create_page(
            request,
            admin_service,
            error_message="Файл не выбран. Загрузите документ или видео.",
        )

    content = await upload_file.read()
    try:
        saved = upload_service.save_upload(filename, content)
    except AdminUploadError as exc:
        return _render_admin_course_create_page(
            request,
            admin_service,
            error_message=exc.message,
        )

    confirm_view = build_upload_confirm_view(saved, form_values)
    return templates.TemplateResponse(
        request,
        "admin_course_upload_confirm.html",
        {
            "active_nav": "admin",
            "confirm": confirm_view,
        },
    )


@router.post(
    "/admin/courses/new/review",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def admin_course_generation_review(
    request: Request,
    admin_service: AdminService = Depends(get_admin_service),
    upload_service: AdminUploadService = Depends(get_upload_service),
) -> HTMLResponse:
    """Validate uploaded source and wizard options, then show review page."""
    form = await request.form()
    form_values = parse_admin_course_form(form)
    upload_id = str(form.get("upload_id") or "").strip()
    original_filename = str(form.get("original_filename") or "").strip()

    if not upload_id:
        return _render_admin_course_create_page(
            request,
            admin_service,
            error_message="Не указан загруженный файл. Загрузите файл заново.",
        )

    try:
        review_view = build_generation_review_view(
            upload_service,
            upload_id,
            form_values,
            original_filename=original_filename,
        )
    except AdminReviewError as exc:
        return _render_admin_course_create_page(
            request,
            admin_service,
            error_message=exc.message,
        )

    return templates.TemplateResponse(
        request,
        "admin_course_generation_review.html",
        {
            "active_nav": "admin",
            "review": review_view,
        },
    )


def _render_admin_generation_review_error(
    request: Request,
    admin_service: AdminService,
    upload_service: AdminUploadService,
    *,
    form_values: AdminCourseFormValues,
    upload_id: str,
    original_filename: str,
    error_message: str,
) -> HTMLResponse:
    """Return review page with a safe generation error message."""
    try:
        review_view = build_generation_review_view(
            upload_service,
            upload_id,
            form_values,
            original_filename=original_filename,
            error_message=error_message,
        )
    except AdminReviewError:
        return _render_admin_course_create_page(
            request,
            admin_service,
            error_message=error_message,
        )

    return templates.TemplateResponse(
        request,
        "admin_course_generation_review.html",
        {
            "active_nav": "admin",
            "review": review_view,
        },
    )


@router.post(
    "/admin/courses/new/generate",
    include_in_schema=False,
)
async def admin_course_generate(
    request: Request,
    admin_service: AdminService = Depends(get_admin_service),
    upload_service: AdminUploadService = Depends(get_upload_service),
    generation_service: AdminGenerationService = Depends(get_admin_generation_service),
):
    """Generate a course from validated upload and wizard options."""
    form = await request.form()
    form_values = parse_admin_course_form(form)
    upload_id = str(form.get("upload_id") or "").strip()
    original_filename = str(form.get("original_filename") or "").strip()

    if not upload_id:
        return _render_admin_course_create_page(
            request,
            admin_service,
            error_message="Не указан загруженный файл. Загрузите файл заново.",
        )

    try:
        result = generation_service.generate_course(
            AdminGenerationRequest(
                upload_id=upload_id,
                form_values=form_values,
                original_filename=original_filename,
            )
        )
    except AdminGenerationError as exc:
        return _render_admin_generation_review_error(
            request,
            admin_service,
            upload_service,
            form_values=form_values,
            upload_id=upload_id,
            original_filename=original_filename,
            error_message=exc.message,
        )

    return RedirectResponse(
        url=f"/admin/courses/{result.slug}/created",
        status_code=303,
    )


@router.get(
    "/admin/courses/{slug}/created",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def admin_course_created_page(
    slug: str,
    request: Request,
    generation_service: AdminGenerationService = Depends(get_admin_generation_service),
) -> HTMLResponse:
    """Render the post-generation success page for one course."""
    created = generation_service.build_created_view(slug)
    if created is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Курс не найден",
                "message": "Созданный курс недоступен или не существует.",
            },
            status_code=404,
        )

    return templates.TemplateResponse(
        request,
        "admin_course_created.html",
        {
            "active_nav": "admin",
            "created": created,
        },
    )


def _render_admin_course_detail_page(
    request: Request,
    detail,
    *,
    error_message: str = "",
) -> HTMLResponse:
    """Render the read-only admin overview for one course."""
    return templates.TemplateResponse(
        request,
        "admin_course_detail.html",
        {
            "active_nav": "admin",
            "detail": detail,
            "error_message": error_message,
        },
    )


@router.get("/admin/courses/{slug}", response_class=HTMLResponse, include_in_schema=False)
def admin_course_detail_page(
    slug: str,
    request: Request,
    admin_service: AdminService = Depends(get_admin_service),
) -> HTMLResponse:
    """Render the read-only admin overview for one published course."""
    detail = admin_service.get_course_detail(slug)
    if detail is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Курс не найден",
                "message": "Запрошенный курс недоступен или не существует.",
            },
            status_code=404,
        )

    return _render_admin_course_detail_page(request, detail)


def _render_admin_course_edit_page(
    request: Request,
    edit_view,
    *,
    error_message: str = "",
    form_title: Optional[str] = None,
    form_description: Optional[str] = None,
    form_language: Optional[str] = None,
) -> HTMLResponse:
    """Render the admin course metadata edit form."""
    return templates.TemplateResponse(
        request,
        "admin_course_edit.html",
        {
            "active_nav": "admin",
            "edit": edit_view,
            "error_message": error_message,
            "form_title": edit_view.title if form_title is None else form_title,
            "form_description": (
                edit_view.description if form_description is None else form_description
            ),
            "form_language": edit_view.language if form_language is None else form_language,
        },
    )


@router.get(
    "/admin/courses/{slug}/edit",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def admin_course_edit_page(
    slug: str,
    request: Request,
    edit_service: AdminCourseEditService = Depends(get_admin_course_edit_service),
) -> HTMLResponse:
    """Render the course metadata edit form for one published course."""
    edit_view = edit_service.get_edit_view(slug)
    if edit_view is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Курс не найден",
                "message": "Запрошенный курс недоступен или не существует.",
            },
            status_code=404,
        )

    return _render_admin_course_edit_page(request, edit_view)


@router.post(
    "/admin/courses/{slug}/edit",
    include_in_schema=False,
)
async def admin_course_edit_submit(
    slug: str,
    request: Request,
    edit_service: AdminCourseEditService = Depends(get_admin_course_edit_service),
):
    """Validate and persist updated course metadata, then redirect to detail."""
    edit_view = edit_service.get_edit_view(slug)
    if edit_view is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Курс не найден",
                "message": "Запрошенный курс недоступен или не существует.",
            },
            status_code=404,
        )

    form = await request.form()
    title = str(form.get("title") or "")
    description = str(form.get("description") or "")
    language = str(form.get("language") or "")

    try:
        result = edit_service.update_metadata(
            AdminCourseEditRequest(
                slug=slug,
                title=title,
                description=description,
                language=language,
            )
        )
    except AdminCourseEditError as exc:
        return _render_admin_course_edit_page(
            request,
            edit_view,
            error_message=exc.message,
            form_title=title,
            form_description=description,
            form_language=language,
        )

    return RedirectResponse(
        url=f"/admin/courses/{result.slug}",
        status_code=303,
    )


def _render_admin_lesson_edit_page(
    request: Request,
    edit_view,
    *,
    error_message: str = "",
    form_title: Optional[str] = None,
    form_description: Optional[str] = None,
    form_practical_task: Optional[str] = None,
    form_checklist: Optional[str] = None,
    form_key_takeaways: Optional[str] = None,
    form_application_tips: Optional[str] = None,
) -> HTMLResponse:
    """Render the admin lesson edit form."""
    return templates.TemplateResponse(
        request,
        "admin_lesson_edit.html",
        {
            "active_nav": "admin",
            "edit": edit_view,
            "error_message": error_message,
            "form_title": edit_view.title if form_title is None else form_title,
            "form_description": (
                edit_view.description if form_description is None else form_description
            ),
            "form_practical_task": (
                edit_view.practical_task
                if form_practical_task is None
                else form_practical_task
            ),
            "form_checklist": (
                edit_view.checklist_text if form_checklist is None else form_checklist
            ),
            "form_key_takeaways": (
                edit_view.key_takeaways_text
                if form_key_takeaways is None
                else form_key_takeaways
            ),
            "form_application_tips": (
                edit_view.application_tips_text
                if form_application_tips is None
                else form_application_tips
            ),
        },
    )


@router.get(
    "/admin/courses/{slug}/lessons/{lesson_id}/edit",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def admin_lesson_edit_page(
    slug: str,
    lesson_id: str,
    request: Request,
    edit_service: AdminLessonEditService = Depends(get_admin_lesson_edit_service),
) -> HTMLResponse:
    """Render the lesson edit form for one published lesson."""
    edit_view = edit_service.get_edit_view(slug, lesson_id)
    if edit_view is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Урок не найден",
                "message": "Запрошенный урок недоступен или не существует.",
            },
            status_code=404,
        )

    return _render_admin_lesson_edit_page(request, edit_view)


@router.post(
    "/admin/courses/{slug}/lessons/{lesson_id}/edit",
    include_in_schema=False,
)
async def admin_lesson_edit_submit(
    slug: str,
    lesson_id: str,
    request: Request,
    edit_service: AdminLessonEditService = Depends(get_admin_lesson_edit_service),
):
    """Validate and persist updated lesson content, then redirect to course detail."""
    edit_view = edit_service.get_edit_view(slug, lesson_id)
    if edit_view is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Урок не найден",
                "message": "Запрошенный урок недоступен или не существует.",
            },
            status_code=404,
        )

    form = await request.form()
    title = str(form.get("title") or "")
    description = str(form.get("description") or "")
    practical_task = str(form.get("practical_task") or "")
    checklist_raw = str(form.get("checklist") or "")
    key_takeaways_raw = str(form.get("key_takeaways") or "")
    application_tips_raw = str(form.get("application_tips") or "")

    try:
        result = edit_service.update_lesson(
            AdminLessonEditRequest(
                slug=slug,
                lesson_id=lesson_id,
                title=title,
                description=description,
                practical_task=practical_task,
                checklist=_parse_multiline_list(checklist_raw),
                key_takeaways=_parse_multiline_list(key_takeaways_raw),
                application_tips=_parse_multiline_list(application_tips_raw),
            )
        )
    except AdminLessonEditError as exc:
        return _render_admin_lesson_edit_page(
            request,
            edit_view,
            error_message=exc.message,
            form_title=title,
            form_description=description,
            form_practical_task=practical_task,
            form_checklist=checklist_raw,
            form_key_takeaways=key_takeaways_raw,
            form_application_tips=application_tips_raw,
        )

    return RedirectResponse(
        url=f"/admin/courses/{result.slug}",
        status_code=303,
    )


@router.post(
    "/admin/courses/{slug}/lessons/create",
    include_in_schema=False,
)
def admin_lesson_create(
    slug: str,
    request: Request,
    admin_service: AdminService = Depends(get_admin_service),
    create_service: AdminLessonCreateService = Depends(get_admin_lesson_create_service),
):
    """Create a new lesson and redirect to its edit page."""
    detail = admin_service.get_course_detail(slug)
    if detail is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Курс не найден",
                "message": "Запрошенный курс недоступен или не существует.",
            },
            status_code=404,
        )

    try:
        result = create_service.create_lesson(slug)
    except AdminLessonCreateError as exc:
        return _render_admin_course_detail_page(
            request,
            detail,
            error_message=exc.message,
        )

    return RedirectResponse(url=result.edit_url, status_code=303)


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
