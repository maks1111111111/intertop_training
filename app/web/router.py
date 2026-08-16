"""Read-only Web UI routes backed by ContentRuntime."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

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
from app.web.admin_lesson_practical_task_apply_service import (
    AdminLessonPracticalTaskApplyError,
    AdminLessonPracticalTaskApplyRequest,
    AdminLessonPracticalTaskApplyService,
)
from app.web.admin_lesson_practical_task_preview_service import (
    AdminLessonPracticalTaskPreviewError,
    AdminLessonPracticalTaskPreviewService,
)
from app.web.admin_lesson_practical_task_preview_store import (
    AdminLessonPracticalTaskPreviewStore,
)
from app.web.admin_lesson_question_apply_service import (
    AdminLessonQuestionApplyError,
    AdminLessonQuestionApplyRequest,
    AdminLessonQuestionApplyService,
    parse_question_edits_from_form,
    parse_selected_question_indexes,
)
from app.web.admin_lesson_question_preview_service import (
    AdminLessonQuestionPreviewError,
    AdminLessonQuestionPreviewService,
)
from app.web.admin_lesson_question_preview_store import (
    AdminLessonQuestionPreviewStore,
    AdminLessonQuestionPreviewStoreError,
)
from app.web.admin_quiz_edit_service import (
    AdminQuizEditError,
    AdminQuizEditRequest,
    AdminQuizEditService,
)
from app.web.admin_quiz_question_create_service import (
    AdminQuizQuestionCreateError,
    AdminQuizQuestionCreateRequest,
    AdminQuizQuestionCreateService,
    AdminQuizQuestionDeleteRequest,
)
from app.web.admin_quiz_question_edit_service import (
    AdminQuizQuestionEditError,
    AdminQuizQuestionEditRequest,
    AdminQuizQuestionEditService,
    parse_question_tags,
)
from app.web.admin_quiz_question_reorder_service import (
    AdminQuizQuestionReorderError,
    AdminQuizQuestionReorderRequest,
    AdminQuizQuestionReorderService,
)
from app.web.admin_service import AdminService
from app.web.admin_preview_service import PreviewContext, build_preview_progress_view
from app.web.admin_generation_service import (
    AdminGenerationError,
    AdminGenerationRequest,
    AdminGenerationService,
)
from app.web.admin_manual_course_create_service import (
    AdminManualCourseCreateError,
    AdminManualCourseCreateRequest,
    AdminManualCourseCreateService,
)
from app.web.admin_quiz_create_service import (
    AdminQuizCreateError,
    AdminQuizCreateService,
)
from app.web.admin_upload_service import (
    AdminCourseFormValues,
    AdminReviewError,
    AdminUploadError,
    AdminUploadService,
    build_generation_review_view,
    build_generation_loading_view,
    build_upload_confirm_view,
    parse_admin_course_form,
)
from app.ai.config import OpenAIConfig
from app.knowledge.question_answering_bootstrap import (
    create_knowledge_question_answering_service,
)
from app.web.admin_knowledge_lifecycle_service import (
    AdminKnowledgeLifecycleError,
    AdminKnowledgeLifecycleService,
)
from app.web.admin_knowledge_question_service import (
    AdminKnowledgeAnswerView,
    AdminKnowledgeQuestionError,
    AdminKnowledgeQuestionService,
)
from app.web.admin_knowledge_service import AdminKnowledgeService
from app.web.admin_knowledge_upload_service import (
    AdminKnowledgeUploadError,
    AdminKnowledgeUploadService,
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


def get_admin_knowledge_service(
    db_path: Path = Depends(get_db_path),
) -> AdminKnowledgeService:
    """Return the admin Knowledge Base service for the current database."""
    return AdminKnowledgeService(db_path)


def get_admin_knowledge_upload_service(
    request: Request,
    db_path: Path = Depends(get_db_path),
) -> AdminKnowledgeUploadService:
    """Return the admin Knowledge Base upload service."""
    override = getattr(request.app.state, "admin_knowledge_upload_service", None)
    if override is not None:
        return override
    return AdminKnowledgeUploadService(db_path, request.app.state.upload_dir)


def get_admin_knowledge_lifecycle_service(
    db_path: Path = Depends(get_db_path),
) -> AdminKnowledgeLifecycleService:
    """Return the admin Knowledge Base lifecycle service."""
    return AdminKnowledgeLifecycleService(db_path)


def get_admin_knowledge_question_service(
    request: Request,
    db_path: Path = Depends(get_db_path),
) -> AdminKnowledgeQuestionService:
    """Return the admin Knowledge Base question answering service."""
    override = getattr(request.app.state, "admin_knowledge_question_service", None)
    if override is not None:
        return override
    config = OpenAIConfig.from_environment()
    question_answering_service = create_knowledge_question_answering_service(config)
    return AdminKnowledgeQuestionService(
        db_path,
        question_answering_service=question_answering_service,
    )


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


def get_admin_lesson_question_preview_store(
    request: Request,
) -> AdminLessonQuestionPreviewStore:
    """Return the in-memory preview store for AI lesson question previews."""
    store = getattr(request.app.state, "admin_lesson_question_preview_store", None)
    if store is None:
        store = AdminLessonQuestionPreviewStore()
        request.app.state.admin_lesson_question_preview_store = store
    return store


def get_admin_lesson_question_preview_service(
    request: Request,
    runtime: ContentRuntime = Depends(get_content_runtime),
    preview_store: AdminLessonQuestionPreviewStore = Depends(
        get_admin_lesson_question_preview_store
    ),
) -> AdminLessonQuestionPreviewService:
    """Return the admin lesson question preview service for the current application."""
    override = getattr(
        request.app.state,
        "admin_lesson_question_preview_service",
        None,
    )
    if override is not None:
        return override
    return AdminLessonQuestionPreviewService(runtime, preview_store=preview_store)


def get_admin_lesson_question_apply_service(
    request: Request,
    runtime: ContentRuntime = Depends(get_content_runtime),
    preview_store: AdminLessonQuestionPreviewStore = Depends(
        get_admin_lesson_question_preview_store
    ),
) -> AdminLessonQuestionApplyService:
    """Return the admin lesson question apply service for the current application."""
    override = getattr(
        request.app.state,
        "admin_lesson_question_apply_service",
        None,
    )
    if override is not None:
        return override
    return AdminLessonQuestionApplyService(runtime.base_dir, runtime, preview_store)


def get_admin_lesson_practical_task_preview_store(
    request: Request,
) -> AdminLessonPracticalTaskPreviewStore:
    """Return the in-memory preview store for AI lesson practical-task previews."""
    store = getattr(
        request.app.state,
        "admin_lesson_practical_task_preview_store",
        None,
    )
    if store is None:
        store = AdminLessonPracticalTaskPreviewStore()
        request.app.state.admin_lesson_practical_task_preview_store = store
    return store


def get_admin_lesson_practical_task_preview_service(
    request: Request,
    runtime: ContentRuntime = Depends(get_content_runtime),
    preview_store: AdminLessonPracticalTaskPreviewStore = Depends(
        get_admin_lesson_practical_task_preview_store
    ),
) -> AdminLessonPracticalTaskPreviewService:
    """Return the admin lesson practical-task preview service."""
    override = getattr(
        request.app.state,
        "admin_lesson_practical_task_preview_service",
        None,
    )
    if override is not None:
        return override
    return AdminLessonPracticalTaskPreviewService(
        runtime,
        preview_store=preview_store,
    )


def get_admin_lesson_practical_task_apply_service(
    request: Request,
    runtime: ContentRuntime = Depends(get_content_runtime),
    preview_store: AdminLessonPracticalTaskPreviewStore = Depends(
        get_admin_lesson_practical_task_preview_store
    ),
) -> AdminLessonPracticalTaskApplyService:
    """Return the admin lesson practical-task apply service."""
    override = getattr(
        request.app.state,
        "admin_lesson_practical_task_apply_service",
        None,
    )
    if override is not None:
        return override
    return AdminLessonPracticalTaskApplyService(
        runtime.base_dir,
        runtime,
        preview_store,
    )


def get_admin_quiz_edit_service(
    runtime: ContentRuntime = Depends(get_content_runtime),
) -> AdminQuizEditService:
    """Return the admin quiz edit service for the current application."""
    return AdminQuizEditService(runtime.base_dir, runtime)


def get_admin_quiz_question_edit_service(
    runtime: ContentRuntime = Depends(get_content_runtime),
) -> AdminQuizQuestionEditService:
    """Return the admin quiz question edit service for the current application."""
    return AdminQuizQuestionEditService(runtime.base_dir, runtime)


def get_admin_quiz_question_create_service(
    runtime: ContentRuntime = Depends(get_content_runtime),
) -> AdminQuizQuestionCreateService:
    """Return the admin quiz question create/delete service for the current application."""
    return AdminQuizQuestionCreateService(runtime.base_dir, runtime)


def get_admin_quiz_question_reorder_service(
    runtime: ContentRuntime = Depends(get_content_runtime),
) -> AdminQuizQuestionReorderService:
    """Return the admin quiz question reorder service for the current application."""
    return AdminQuizQuestionReorderService(runtime.base_dir, runtime)


def get_admin_manual_course_create_service(
    runtime: ContentRuntime = Depends(get_content_runtime),
) -> AdminManualCourseCreateService:
    """Return the admin manual course create service for the current application."""
    return AdminManualCourseCreateService(runtime.base_dir, runtime)


def get_admin_quiz_create_service(
    runtime: ContentRuntime = Depends(get_content_runtime),
) -> AdminQuizCreateService:
    """Return the admin quiz create service for the current application."""
    return AdminQuizCreateService(runtime.base_dir, runtime)


# TODO: Replace with authenticated web user identity when auth is implemented.
_WEB_DASHBOARD_TELEGRAM_ID = 1

# TODO: Replace with authenticated tenant/company identity when auth is implemented.
_WEB_ADMIN_COMPANY_ID = "intertop"


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


def _render_admin_knowledge_page(
    request: Request,
    knowledge_service: AdminKnowledgeService,
    *,
    error_message: str = "",
) -> HTMLResponse:
    """Render the admin Knowledge Base document list."""
    documents = knowledge_service.get_documents(_WEB_ADMIN_COMPANY_ID)
    return templates.TemplateResponse(
        request,
        "admin_knowledge.html",
        {
            "active_nav": "admin",
            "documents": documents,
            "documents_count": len(documents),
            "error_message": error_message,
        },
    )


@router.get("/admin/knowledge", response_class=HTMLResponse, include_in_schema=False)
def admin_knowledge_page(
    request: Request,
    knowledge_service: AdminKnowledgeService = Depends(get_admin_knowledge_service),
) -> HTMLResponse:
    """Render the admin Knowledge Base document list."""
    return _render_admin_knowledge_page(request, knowledge_service)


@router.post(
    "/admin/knowledge/{document_id}/publish",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def admin_knowledge_publish(
    request: Request,
    document_id: str,
    knowledge_service: AdminKnowledgeService = Depends(get_admin_knowledge_service),
    lifecycle_service: AdminKnowledgeLifecycleService = Depends(
        get_admin_knowledge_lifecycle_service
    ),
) -> HTMLResponse:
    """Publish one Knowledge Base document."""
    try:
        lifecycle_service.publish(_WEB_ADMIN_COMPANY_ID, document_id)
    except AdminKnowledgeLifecycleError as exc:
        return _render_admin_knowledge_page(
            request,
            knowledge_service,
            error_message=exc.message,
        )

    return RedirectResponse(url="/admin/knowledge", status_code=303)


@router.post(
    "/admin/knowledge/{document_id}/archive",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def admin_knowledge_archive(
    request: Request,
    document_id: str,
    knowledge_service: AdminKnowledgeService = Depends(get_admin_knowledge_service),
    lifecycle_service: AdminKnowledgeLifecycleService = Depends(
        get_admin_knowledge_lifecycle_service
    ),
) -> HTMLResponse:
    """Archive one Knowledge Base document."""
    try:
        lifecycle_service.archive(_WEB_ADMIN_COMPANY_ID, document_id)
    except AdminKnowledgeLifecycleError as exc:
        return _render_admin_knowledge_page(
            request,
            knowledge_service,
            error_message=exc.message,
        )

    return RedirectResponse(url="/admin/knowledge", status_code=303)


def _render_admin_knowledge_ask_page(
    request: Request,
    *,
    question: str = "",
    language: str = "ru",
    error_message: str = "",
    answer_view: Optional[AdminKnowledgeAnswerView] = None,
) -> HTMLResponse:
    """Render the Knowledge Base grounded question form and optional answer."""
    return templates.TemplateResponse(
        request,
        "admin_knowledge_ask.html",
        {
            "active_nav": "admin",
            "question": question,
            "language": language,
            "error_message": error_message,
            "answer_view": answer_view,
        },
    )


@router.get(
    "/admin/knowledge/ask",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def admin_knowledge_ask_page(request: Request) -> HTMLResponse:
    """Render the Knowledge Base grounded question form."""
    return _render_admin_knowledge_ask_page(request)


@router.post(
    "/admin/knowledge/ask",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def admin_knowledge_ask_submit(
    request: Request,
    question_service: AdminKnowledgeQuestionService = Depends(
        get_admin_knowledge_question_service
    ),
) -> HTMLResponse:
    """Answer one grounded Knowledge Base question for the admin UI."""
    form = await request.form()
    question = str(form.get("question") or "")
    language = str(form.get("language") or "ru").strip()

    try:
        answer_view = question_service.answer_question(
            _WEB_ADMIN_COMPANY_ID,
            question,
            language=language,
        )
    except AdminKnowledgeQuestionError as exc:
        return _render_admin_knowledge_ask_page(
            request,
            question=question,
            language=language,
            error_message=exc.message,
        )

    return _render_admin_knowledge_ask_page(
        request,
        question=question,
        language=language,
        answer_view=answer_view,
    )


def _render_admin_knowledge_upload_page(
    request: Request,
    *,
    error_message: str = "",
    title: str = "",
    source_language: str = "auto",
) -> HTMLResponse:
    """Render the Knowledge Base document upload form."""
    return templates.TemplateResponse(
        request,
        "admin_knowledge_upload.html",
        {
            "active_nav": "admin",
            "error_message": error_message,
            "title": title,
            "source_language": source_language,
        },
    )


@router.get(
    "/admin/knowledge/upload",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def admin_knowledge_upload_page(request: Request) -> HTMLResponse:
    """Render the Knowledge Base document upload form."""
    return _render_admin_knowledge_upload_page(request)


@router.post(
    "/admin/knowledge/upload",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def admin_knowledge_upload_submit(
    request: Request,
    upload_service: AdminKnowledgeUploadService = Depends(
        get_admin_knowledge_upload_service
    ),
) -> HTMLResponse:
    """Validate and import one uploaded Knowledge Base document."""
    form = await request.form()
    title = str(form.get("title") or "").strip()
    source_language = str(form.get("source_language") or "auto").strip()
    upload_file = form.get("source_file")

    filename = getattr(upload_file, "filename", None)
    if upload_file is None or not filename:
        return _render_admin_knowledge_upload_page(
            request,
            error_message="Файл не выбран. Загрузите документ.",
            title=title,
            source_language=source_language,
        )

    content = await upload_file.read()
    try:
        upload_service.import_upload(
            company_id=_WEB_ADMIN_COMPANY_ID,
            filename=filename,
            content=content,
            title=title or None,
            source_language=source_language,
        )
    except AdminKnowledgeUploadError as exc:
        return _render_admin_knowledge_upload_page(
            request,
            error_message=exc.message,
            title=title,
            source_language=source_language,
        )

    return RedirectResponse(url="/admin/knowledge", status_code=303)


@router.get(
    "/admin/knowledge/{document_id}",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def admin_knowledge_document_page(
    request: Request,
    document_id: str,
    knowledge_service: AdminKnowledgeService = Depends(get_admin_knowledge_service),
    chunk: Optional[int] = None,
) -> HTMLResponse:
    """Render one tenant-scoped Knowledge Base document."""
    detail = knowledge_service.get_document_detail(
        _WEB_ADMIN_COMPANY_ID,
        document_id,
        focus_chunk_index=chunk,
    )
    if detail is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Документ не найден",
                "message": "Запрошенный документ базы знаний не найден.",
            },
            status_code=404,
        )

    return templates.TemplateResponse(
        request,
        "admin_knowledge_document.html",
        {
            "active_nav": "admin",
            "detail": detail,
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
def admin_course_create_mode_page(request: Request) -> HTMLResponse:
    """Render the course creation mode selection page."""
    return templates.TemplateResponse(
        request,
        "admin_course_create_mode.html",
        {
            "active_nav": "admin",
        },
    )


@router.get(
    "/admin/courses/new/ai",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def admin_course_create_page(
    request: Request,
    admin_service: AdminService = Depends(get_admin_service),
) -> HTMLResponse:
    """Render the AI course creation wizard form."""
    return _render_admin_course_create_page(request, admin_service)


@router.post(
    "/admin/courses/new/ai",
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
    "/admin/courses/new",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def admin_course_create_submit_legacy(
    request: Request,
    admin_service: AdminService = Depends(get_admin_service),
    upload_service: AdminUploadService = Depends(get_upload_service),
) -> HTMLResponse:
    """Legacy alias for the AI course creation upload endpoint."""
    return await admin_course_create_submit(request, admin_service, upload_service)


def _render_admin_manual_course_create_page(
    request: Request,
    create_service: AdminManualCourseCreateService,
    *,
    error_message: str = "",
    form_title: str = "",
    form_description: str = "",
    form_language: str = "ru",
) -> HTMLResponse:
    """Render the manual course creation form."""
    create_view = create_service.get_create_view()
    return templates.TemplateResponse(
        request,
        "admin_course_create_manual.html",
        {
            "active_nav": "admin",
            "create_view": create_view,
            "error_message": error_message,
            "form_title": form_title,
            "form_description": form_description,
            "form_language": form_language,
        },
    )


@router.get(
    "/admin/courses/new/manual",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def admin_manual_course_create_page(
    request: Request,
    create_service: AdminManualCourseCreateService = Depends(
        get_admin_manual_course_create_service
    ),
) -> HTMLResponse:
    """Render the manual course creation form."""
    return _render_admin_manual_course_create_page(request, create_service)


@router.post(
    "/admin/courses/new/manual",
    include_in_schema=False,
)
async def admin_manual_course_create_submit(
    request: Request,
    create_service: AdminManualCourseCreateService = Depends(
        get_admin_manual_course_create_service
    ),
):
    """Create an empty course manually and redirect to admin detail."""
    form = await request.form()
    title = str(form.get("title") or "")
    description = str(form.get("description") or "")
    language = str(form.get("language") or "ru")

    try:
        result = create_service.create_course(
            AdminManualCourseCreateRequest(
                title=title,
                description=description,
                language=language,
            )
        )
    except AdminManualCourseCreateError as exc:
        return _render_admin_manual_course_create_page(
            request,
            create_service,
            error_message=exc.message,
            form_title=title.strip(),
            form_description=description,
            form_language=language.strip() or "ru",
        )

    return RedirectResponse(
        url=result.detail_url,
        status_code=303,
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


@router.post(
    "/admin/courses/new/loading",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def admin_course_generation_loading(
    request: Request,
    admin_service: AdminService = Depends(get_admin_service),
    upload_service: AdminUploadService = Depends(get_upload_service),
) -> HTMLResponse:
    """Show the AI generation loading screen before starting course generation."""
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
        loading_view = build_generation_loading_view(
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
        "admin_course_generation_loading.html",
        {
            "active_nav": "admin",
            "loading": loading_view,
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


def _get_preview_course_or_not_found(
    request: Request,
    slug: str,
    content_runtime: ContentRuntime,
):
    """Return a course for preview or a 404 response."""
    course = content_runtime.get_course(slug)
    if course is None:
        return None, templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Курс не найден",
                "message": "Запрошенный курс недоступен или не существует.",
            },
            status_code=404,
        )
    return course, None


@router.get(
    "/admin/courses/{slug}/preview",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def admin_course_preview_page(
    slug: str,
    request: Request,
    content_runtime: ContentRuntime = Depends(get_content_runtime),
) -> HTMLResponse:
    """Render a course as employees will see it without saving progress."""
    course, not_found = _get_preview_course_or_not_found(request, slug, content_runtime)
    if not_found is not None:
        return not_found

    course_detail = course_mapper.to_detail(course)
    preview = PreviewContext.for_course(slug)
    progress = build_preview_progress_view(
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
            "preview": preview,
            "active_nav": "admin",
        },
    )


@router.get(
    "/admin/courses/{slug}/preview/lessons/{lesson_id}",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def admin_lesson_preview_page(
    slug: str,
    lesson_id: str,
    request: Request,
    content_runtime: ContentRuntime = Depends(get_content_runtime),
) -> HTMLResponse:
    """Render one lesson in admin preview mode without recording progress."""
    course, not_found = _get_preview_course_or_not_found(request, slug, content_runtime)
    if not_found is not None:
        return not_found

    preview = PreviewContext.for_course(slug)
    for lesson in course.lessons:
        if lesson.path.name == lesson_id:
            lesson_detail = course_mapper.to_lesson_detail(course, lesson)
            return templates.TemplateResponse(
                request,
                "lesson_detail.html",
                {
                    "course": course_mapper.to_detail(course),
                    "lesson": lesson_detail,
                    "preview": preview,
                    "course_has_quiz": course.quiz is not None,
                    "active_nav": "admin",
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
    "/admin/courses/{slug}/preview/quiz",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def admin_quiz_preview_page(
    slug: str,
    request: Request,
    content_runtime: ContentRuntime = Depends(get_content_runtime),
) -> HTMLResponse:
    """Render the course quiz in admin preview mode."""
    course, not_found = _get_preview_course_or_not_found(request, slug, content_runtime)
    if not_found is not None:
        return not_found

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

    preview = PreviewContext.for_course(slug)
    quiz = build_quiz_page_view(course.quiz)
    return templates.TemplateResponse(
        request,
        "quiz.html",
        {
            "course": course_mapper.to_detail(course),
            "quiz": quiz,
            "preview": preview,
            "active_nav": "admin",
        },
    )


@router.post(
    "/admin/courses/{slug}/preview/quiz",
    response_class=HTMLResponse,
    include_in_schema=False,
)
async def admin_quiz_preview_submit_page(
    slug: str,
    request: Request,
    content_runtime: ContentRuntime = Depends(get_content_runtime),
) -> HTMLResponse:
    """Score a preview quiz submission without persisting attempts."""
    course, not_found = _get_preview_course_or_not_found(request, slug, content_runtime)
    if not_found is not None:
        return not_found

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
    preview = PreviewContext.for_course(slug)

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
            "preview": preview,
            "active_nav": "admin",
        },
    )


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


def _render_admin_lesson_generate_questions_not_found(
    request: Request,
    *,
    resource: str,
) -> HTMLResponse:
    if resource == "course":
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Курс не найден",
                "message": "Запрошенный курс недоступен или не существует.",
            },
            status_code=404,
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


def _render_admin_lesson_generate_questions_page(
    request: Request,
    preview_view,
    *,
    error_message: str = "",
) -> HTMLResponse:
    """Render the admin lesson AI question preview page."""
    return templates.TemplateResponse(
        request,
        "admin_lesson_generate_questions.html",
        {
            "active_nav": "admin",
            "preview": preview_view,
            "error_message": error_message,
        },
    )


@router.get(
    "/admin/courses/{slug}/lessons/{lesson_id}/generate-questions",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def admin_lesson_generate_questions_page(
    slug: str,
    lesson_id: str,
    request: Request,
    preview_service: AdminLessonQuestionPreviewService = Depends(
        get_admin_lesson_question_preview_service
    ),
) -> HTMLResponse:
    """Render the AI question preview page for one lesson."""
    preview_view = preview_service.get_preview_page(slug, lesson_id)
    if preview_view is None:
        not_found = preview_service.get_not_found_reason(slug, lesson_id)
        return _render_admin_lesson_generate_questions_not_found(
            request,
            resource=not_found or "lesson",
        )

    return _render_admin_lesson_generate_questions_page(request, preview_view)


@router.post(
    "/admin/courses/{slug}/lessons/{lesson_id}/generate-questions",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def admin_lesson_generate_questions_submit(
    slug: str,
    lesson_id: str,
    request: Request,
    preview_service: AdminLessonQuestionPreviewService = Depends(
        get_admin_lesson_question_preview_service
    ),
) -> HTMLResponse:
    """Generate AI quiz questions for preview without persisting changes."""
    preview_page = preview_service.get_preview_page(slug, lesson_id)
    if preview_page is None:
        not_found = preview_service.get_not_found_reason(slug, lesson_id)
        return _render_admin_lesson_generate_questions_not_found(
            request,
            resource=not_found or "lesson",
        )

    try:
        preview_view = preview_service.generate_preview(slug, lesson_id)
    except AdminLessonQuestionPreviewError as exc:
        return _render_admin_lesson_generate_questions_page(
            request,
            preview_page,
            error_message=exc.message,
        )

    return _render_admin_lesson_generate_questions_page(request, preview_view)


@router.post(
    "/admin/courses/{slug}/lessons/{lesson_id}/generate-questions/apply",
    include_in_schema=False,
)
async def admin_lesson_generate_questions_apply(
    slug: str,
    lesson_id: str,
    request: Request,
    preview_service: AdminLessonQuestionPreviewService = Depends(
        get_admin_lesson_question_preview_service
    ),
    apply_service: AdminLessonQuestionApplyService = Depends(
        get_admin_lesson_question_apply_service
    ),
    preview_store: AdminLessonQuestionPreviewStore = Depends(
        get_admin_lesson_question_preview_store
    ),
):
    """Append selected AI preview questions to the course quiz."""
    form = await request.form()
    preview_id = str(form.get("preview_id") or "")
    edited_questions: tuple[AdminLessonQuestionEditInput, ...] = ()
    selected_indexes: tuple[int, ...] = ()
    ownership_verified = False

    try:
        try:
            record = preview_store.get(preview_id)
        except AdminLessonQuestionPreviewStoreError as exc:
            raise AdminLessonQuestionApplyError(exc.message) from exc
        if record is None:
            raise AdminLessonQuestionApplyError(
                "Предпросмотр вопросов недоступен. Сгенерируйте вопросы снова."
            )
        if record.slug != slug or record.lesson_id != lesson_id:
            raise AdminLessonQuestionApplyError(
                "Предпросмотр вопросов недоступен. Сгенерируйте вопросы снова."
            )

        ownership_verified = True
        edited_questions = parse_question_edits_from_form(form, record)
        selected_indexes = parse_selected_question_indexes(
            form.getlist("selected_questions")
        )
        result = apply_service.apply_selected_questions(
            AdminLessonQuestionApplyRequest(
                slug=slug,
                lesson_id=lesson_id,
                preview_id=preview_id,
                selected_indexes=selected_indexes,
                edited_questions=edited_questions,
            )
        )
    except AdminLessonQuestionApplyError as exc:
        if ownership_verified:
            preview_view = preview_service.get_generated_preview_page(
                slug,
                lesson_id,
                preview_id,
            )
            if preview_view is not None:
                if edited_questions:
                    preview_view = preview_service.with_edited_values(
                        preview_view,
                        edited_questions=edited_questions,
                        selected_indexes=selected_indexes,
                    )
                return _render_admin_lesson_generate_questions_page(
                    request,
                    preview_view,
                    error_message=exc.message,
                )

        preview_page = preview_service.get_preview_page(slug, lesson_id)
        if preview_page is None:
            not_found = preview_service.get_not_found_reason(slug, lesson_id)
            return _render_admin_lesson_generate_questions_not_found(
                request,
                resource=not_found or "lesson",
            )
        return _render_admin_lesson_generate_questions_page(
            request,
            preview_page,
            error_message=exc.message,
        )

    return RedirectResponse(
        url=f"/admin/courses/{result.slug}/quiz/edit",
        status_code=303,
    )


def _render_admin_lesson_generate_practical_task_not_found(
    request: Request,
    *,
    resource: str,
) -> HTMLResponse:
    if resource == "course":
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Курс не найден",
                "message": "Запрошенный курс недоступен или не существует.",
            },
            status_code=404,
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


def _render_admin_lesson_generate_practical_task_page(
    request: Request,
    preview_view,
    *,
    error_message: str = "",
) -> HTMLResponse:
    """Render the admin lesson AI practical-task preview page."""
    return templates.TemplateResponse(
        request,
        "admin_lesson_generate_practical_task.html",
        {
            "active_nav": "admin",
            "preview": preview_view,
            "error_message": error_message,
        },
    )


@router.get(
    "/admin/courses/{slug}/lessons/{lesson_id}/generate-practical-task",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def admin_lesson_generate_practical_task_page(
    slug: str,
    lesson_id: str,
    request: Request,
    preview_service: AdminLessonPracticalTaskPreviewService = Depends(
        get_admin_lesson_practical_task_preview_service
    ),
) -> HTMLResponse:
    """Render the AI practical-task preview page for one lesson."""
    preview_view = preview_service.get_preview_page(slug, lesson_id)
    if preview_view is None:
        not_found = preview_service.get_not_found_reason(slug, lesson_id)
        return _render_admin_lesson_generate_practical_task_not_found(
            request,
            resource=not_found or "lesson",
        )

    return _render_admin_lesson_generate_practical_task_page(request, preview_view)


@router.post(
    "/admin/courses/{slug}/lessons/{lesson_id}/generate-practical-task",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def admin_lesson_generate_practical_task_submit(
    slug: str,
    lesson_id: str,
    request: Request,
    preview_service: AdminLessonPracticalTaskPreviewService = Depends(
        get_admin_lesson_practical_task_preview_service
    ),
) -> HTMLResponse:
    """Generate an AI practical task for preview without persisting changes."""
    preview_page = preview_service.get_preview_page(slug, lesson_id)
    if preview_page is None:
        not_found = preview_service.get_not_found_reason(slug, lesson_id)
        return _render_admin_lesson_generate_practical_task_not_found(
            request,
            resource=not_found or "lesson",
        )

    try:
        preview_view = preview_service.generate_preview(slug, lesson_id)
    except AdminLessonPracticalTaskPreviewError as exc:
        return _render_admin_lesson_generate_practical_task_page(
            request,
            preview_page,
            error_message=exc.message,
        )

    return _render_admin_lesson_generate_practical_task_page(request, preview_view)


@router.post(
    "/admin/courses/{slug}/lessons/{lesson_id}/generate-practical-task/apply",
    include_in_schema=False,
)
async def admin_lesson_generate_practical_task_apply(
    slug: str,
    lesson_id: str,
    request: Request,
    preview_service: AdminLessonPracticalTaskPreviewService = Depends(
        get_admin_lesson_practical_task_preview_service
    ),
    apply_service: AdminLessonPracticalTaskApplyService = Depends(
        get_admin_lesson_practical_task_apply_service
    ),
):
    """Apply an AI preview practical task to the lesson."""
    form = await request.form()
    preview_id = str(form.get("preview_id") or "")
    title = str(form.get("title") or "")
    description = str(form.get("description") or "")
    expected_result = str(form.get("expected_result") or "")
    estimated_minutes = str(form.get("estimated_minutes") or "")

    try:
        result = apply_service.apply_preview(
            AdminLessonPracticalTaskApplyRequest(
                slug=slug,
                lesson_id=lesson_id,
                preview_id=preview_id,
                title=title,
                description=description,
                expected_result=expected_result,
                estimated_minutes=estimated_minutes,
            )
        )
    except AdminLessonPracticalTaskApplyError as exc:
        preview_view = preview_service.get_generated_preview_page(
            slug,
            lesson_id,
            preview_id,
        )
        if preview_view is None:
            preview_view = preview_service.get_generated_preview_page_by_id(
                preview_id
            )
        if preview_view is None:
            preview_page = preview_service.get_preview_page(slug, lesson_id)
            if preview_page is None:
                not_found = preview_service.get_not_found_reason(slug, lesson_id)
                return _render_admin_lesson_generate_practical_task_not_found(
                    request,
                    resource=not_found or "lesson",
                )
            return _render_admin_lesson_generate_practical_task_page(
                request,
                preview_page,
                error_message=exc.message,
            )
        preview_view = preview_service.with_edited_values(
            preview_view,
            title=title,
            description=description,
            expected_result=expected_result,
            estimated_minutes=estimated_minutes,
        )
        return _render_admin_lesson_generate_practical_task_page(
            request,
            preview_view,
            error_message=exc.message,
        )

    return RedirectResponse(
        url=f"/admin/courses/{result.slug}/lessons/{result.lesson_id}/edit",
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


@router.post(
    "/admin/courses/{slug}/quiz/create",
    include_in_schema=False,
)
def admin_quiz_create_submit(
    slug: str,
    request: Request,
    admin_service: AdminService = Depends(get_admin_service),
    quiz_create_service: AdminQuizCreateService = Depends(get_admin_quiz_create_service),
):
    """Create an empty final quiz for one course and redirect to quiz edit."""
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
        result = quiz_create_service.create_quiz(slug)
    except AdminQuizCreateError as exc:
        return _render_admin_course_detail_page(
            request,
            detail,
            error_message=exc.message,
        )

    return RedirectResponse(url=result.edit_url, status_code=303)


def _render_admin_quiz_edit_page(
    request: Request,
    edit_view,
    *,
    error_message: str = "",
    form_title: Optional[str] = None,
    form_passing_score: Optional[str] = None,
    form_randomize_questions: Optional[bool] = None,
    form_randomize_options: Optional[bool] = None,
) -> HTMLResponse:
    """Render the admin quiz settings edit form."""
    return templates.TemplateResponse(
        request,
        "admin_quiz_edit.html",
        {
            "active_nav": "admin",
            "edit": edit_view,
            "error_message": error_message,
            "form_title": edit_view.title if form_title is None else form_title,
            "form_passing_score": (
                str(edit_view.passing_score)
                if form_passing_score is None
                else form_passing_score
            ),
            "form_randomize_questions": (
                edit_view.randomize_questions
                if form_randomize_questions is None
                else form_randomize_questions
            ),
            "form_randomize_options": (
                edit_view.randomize_options
                if form_randomize_options is None
                else form_randomize_options
            ),
        },
    )


@router.get(
    "/admin/courses/{slug}/quiz/edit",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def admin_quiz_edit_page(
    slug: str,
    request: Request,
    runtime: ContentRuntime = Depends(get_content_runtime),
    edit_service: AdminQuizEditService = Depends(get_admin_quiz_edit_service),
) -> HTMLResponse:
    """Render the quiz settings edit form for one published course."""
    if runtime.get_course(slug) is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Курс не найден",
                "message": "Запрошенный курс недоступен или не существует.",
            },
            status_code=404,
        )

    edit_view = edit_service.get_edit_view(slug)
    if edit_view is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Тест не найден",
                "message": "Для этого курса итоговый тест не создан.",
            },
            status_code=404,
        )

    return _render_admin_quiz_edit_page(request, edit_view)


@router.post(
    "/admin/courses/{slug}/quiz/edit",
    include_in_schema=False,
)
async def admin_quiz_edit_submit(
    slug: str,
    request: Request,
    runtime: ContentRuntime = Depends(get_content_runtime),
    edit_service: AdminQuizEditService = Depends(get_admin_quiz_edit_service),
):
    """Validate and persist updated quiz settings, then redirect to course detail."""
    if runtime.get_course(slug) is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Курс не найден",
                "message": "Запрошенный курс недоступен или не существует.",
            },
            status_code=404,
        )

    edit_view = edit_service.get_edit_view(slug)
    if edit_view is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Тест не найден",
                "message": "Для этого курса итоговый тест не создан.",
            },
            status_code=404,
        )

    form = await request.form()
    title = str(form.get("title") or "")
    passing_score = str(form.get("passing_score") or "")
    randomize_questions = form.get("randomize_questions") == "1"
    randomize_options = form.get("randomize_options") == "1"

    try:
        result = edit_service.update_quiz(
            AdminQuizEditRequest(
                slug=slug,
                title=title,
                passing_score=passing_score,
                randomize_questions=randomize_questions,
                randomize_options=randomize_options,
            )
        )
    except AdminQuizEditError as exc:
        return _render_admin_quiz_edit_page(
            request,
            edit_view,
            error_message=exc.message,
            form_title=title,
            form_passing_score=passing_score,
            form_randomize_questions=randomize_questions,
            form_randomize_options=randomize_options,
        )

    return RedirectResponse(
        url=f"/admin/courses/{result.slug}",
        status_code=303,
    )


def _render_admin_quiz_question_edit_page(
    request: Request,
    edit_view,
    *,
    error_message: str = "",
    form_text: Optional[str] = None,
    form_option_texts: Optional[list[str]] = None,
    form_correct_option_id: Optional[str] = None,
    form_explanation: Optional[str] = None,
    form_lesson: Optional[str] = None,
    form_difficulty: Optional[str] = None,
    form_tags: Optional[str] = None,
) -> HTMLResponse:
    """Render the admin quiz question edit form."""
    default_option_texts = [option.text for option in edit_view.options]
    option_texts = (
        default_option_texts
        if form_option_texts is None
        else form_option_texts
    )
    default_correct = next(
        (option.id for option in edit_view.options if option.is_correct),
        edit_view.options[0].id if edit_view.options else "",
    )
    return templates.TemplateResponse(
        request,
        "admin_quiz_question_edit.html",
        {
            "active_nav": "admin",
            "edit": edit_view,
            "error_message": error_message,
            "form_text": edit_view.text if form_text is None else form_text,
            "form_option_texts": option_texts,
            "form_correct_option_id": (
                default_correct
                if form_correct_option_id is None
                else form_correct_option_id
            ),
            "form_explanation": (
                edit_view.explanation if form_explanation is None else form_explanation
            ),
            "form_lesson": edit_view.lesson if form_lesson is None else form_lesson,
            "form_difficulty": (
                str(edit_view.difficulty)
                if form_difficulty is None
                else form_difficulty
            ),
            "form_tags": edit_view.tags_text if form_tags is None else form_tags,
        },
    )


@router.get(
    "/admin/courses/{slug}/quiz/questions/{question_id}/edit",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def admin_quiz_question_edit_page(
    slug: str,
    question_id: str,
    request: Request,
    runtime: ContentRuntime = Depends(get_content_runtime),
    edit_service: AdminQuizQuestionEditService = Depends(
        get_admin_quiz_question_edit_service
    ),
) -> HTMLResponse:
    """Render the quiz question edit form for one published course."""
    course = runtime.get_course(slug)
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
                "title": "Тест не найден",
                "message": "Для этого курса итоговый тест не создан.",
            },
            status_code=404,
        )

    edit_view = edit_service.get_edit_view(slug, question_id)
    if edit_view is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Вопрос не найден",
                "message": "Запрошенный вопрос недоступен или не существует.",
            },
            status_code=404,
        )

    return _render_admin_quiz_question_edit_page(request, edit_view)


@router.post(
    "/admin/courses/{slug}/quiz/questions/{question_id}/edit",
    include_in_schema=False,
)
async def admin_quiz_question_edit_submit(
    slug: str,
    question_id: str,
    request: Request,
    runtime: ContentRuntime = Depends(get_content_runtime),
    edit_service: AdminQuizQuestionEditService = Depends(
        get_admin_quiz_question_edit_service
    ),
):
    """Validate and persist updated quiz question content, then redirect to quiz edit."""
    course = runtime.get_course(slug)
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

    edit_view = edit_service.get_edit_view(slug, question_id)

    form = await request.form()
    text = str(form.get("text") or "")
    explanation = str(form.get("explanation") or "")
    lesson = str(form.get("lesson") or "")
    difficulty = str(form.get("difficulty") or "")
    tags_raw = str(form.get("tags") or "")
    correct_option_id = str(form.get("correct_option_id") or "")
    if edit_view is not None:
        option_count = len(edit_view.options)
    else:
        option_count = 0
        while f"option_text_{option_count}" in form:
            option_count += 1
    option_texts = [
        str(form.get(f"option_text_{index}") or "")
        for index in range(option_count)
    ]

    try:
        result = edit_service.update_question(
            AdminQuizQuestionEditRequest(
                slug=slug,
                question_id=question_id,
                text=text,
                option_texts=tuple(option_texts),
                correct_option_id=correct_option_id,
                explanation=explanation,
                lesson=lesson,
                difficulty=difficulty,
                tags=parse_question_tags(tags_raw),
            )
        )
    except AdminQuizQuestionEditError as exc:
        if edit_view is None:
            return templates.TemplateResponse(
                request,
                "not_found.html",
                {
                    "title": "Ошибка редактирования",
                    "message": exc.message,
                },
                status_code=200,
            )
        return _render_admin_quiz_question_edit_page(
            request,
            edit_view,
            error_message=exc.message,
            form_text=text,
            form_option_texts=option_texts,
            form_correct_option_id=correct_option_id,
            form_explanation=explanation,
            form_lesson=lesson,
            form_difficulty=difficulty,
            form_tags=tags_raw,
        )

    return RedirectResponse(
        url=f"/admin/courses/{result.slug}/quiz/edit",
        status_code=303,
    )


def _render_admin_quiz_question_create_page(
    request: Request,
    create_view,
    *,
    error_message: str = "",
    form_text: str = "",
    form_option_texts: Optional[list[str]] = None,
    form_correct_option_index: Optional[int] = None,
    form_explanation: str = "",
    form_lesson: str = "",
    form_difficulty: str = "0",
    form_tags: str = "",
) -> HTMLResponse:
    """Render the admin quiz question create form."""
    default_option_texts = ["", "", "", ""]
    option_texts = (
        default_option_texts
        if form_option_texts is None
        else form_option_texts
    )
    return templates.TemplateResponse(
        request,
        "admin_quiz_question_create.html",
        {
            "active_nav": "admin",
            "create": create_view,
            "error_message": error_message,
            "form_text": form_text,
            "form_option_texts": option_texts,
            "form_correct_option_index": (
                0 if form_correct_option_index is None else form_correct_option_index
            ),
            "form_explanation": form_explanation,
            "form_lesson": form_lesson,
            "form_difficulty": form_difficulty,
            "form_tags": form_tags,
        },
    )


@router.get(
    "/admin/courses/{slug}/quiz/questions/new",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def admin_quiz_question_create_page(
    slug: str,
    request: Request,
    runtime: ContentRuntime = Depends(get_content_runtime),
    create_service: AdminQuizQuestionCreateService = Depends(
        get_admin_quiz_question_create_service
    ),
) -> HTMLResponse:
    """Render the quiz question create form for one published course."""
    course = runtime.get_course(slug)
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

    create_view = create_service.get_create_view(slug)
    if create_view is None:
        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Тест не найден",
                "message": "Для этого курса итоговый тест не создан.",
            },
            status_code=404,
        )

    return _render_admin_quiz_question_create_page(request, create_view)


@router.post(
    "/admin/courses/{slug}/quiz/questions/new",
    include_in_schema=False,
)
async def admin_quiz_question_create_submit(
    slug: str,
    request: Request,
    runtime: ContentRuntime = Depends(get_content_runtime),
    create_service: AdminQuizQuestionCreateService = Depends(
        get_admin_quiz_question_create_service
    ),
):
    """Validate and persist a new quiz question, then redirect to quiz edit."""
    form = await request.form()
    text = str(form.get("text") or "")
    explanation = str(form.get("explanation") or "")
    lesson = str(form.get("lesson") or "")
    difficulty = str(form.get("difficulty") or "")
    tags_raw = str(form.get("tags") or "")
    correct_option_index = str(form.get("correct_option_index") or "")
    option_texts = [
        str(form.get(f"option_text_{index}") or "")
        for index in range(4)
    ]

    try:
        parsed_index = int(correct_option_index) if correct_option_index else 0
    except ValueError:
        parsed_index = -1

    try:
        result = create_service.create_question(
            AdminQuizQuestionCreateRequest(
                slug=slug,
                text=text,
                option_texts=tuple(option_texts),
                correct_option_index=correct_option_index,
                explanation=explanation,
                lesson=lesson,
                difficulty=difficulty,
                tags=parse_question_tags(tags_raw),
            )
        )
    except AdminQuizQuestionCreateError as exc:
        create_view = create_service.get_create_view_for_errors(slug)
        if create_view is None:
            return templates.TemplateResponse(
                request,
                "not_found.html",
                {
                    "title": "Курс не найден",
                    "message": "Запрошенный курс недоступен или не существует.",
                },
                status_code=404,
            )
        return _render_admin_quiz_question_create_page(
            request,
            create_view,
            error_message=exc.message,
            form_text=text,
            form_option_texts=option_texts,
            form_correct_option_index=parsed_index if parsed_index >= 0 else None,
            form_explanation=explanation,
            form_lesson=lesson,
            form_difficulty=difficulty or "0",
            form_tags=tags_raw,
        )

    return RedirectResponse(
        url=f"/admin/courses/{result.slug}/quiz/edit",
        status_code=303,
    )


@router.post(
    "/admin/courses/{slug}/quiz/questions/{question_id}/delete",
    include_in_schema=False,
)
async def admin_quiz_question_delete_submit(
    slug: str,
    question_id: str,
    request: Request,
    runtime: ContentRuntime = Depends(get_content_runtime),
    edit_service: AdminQuizEditService = Depends(get_admin_quiz_edit_service),
    create_service: AdminQuizQuestionCreateService = Depends(
        get_admin_quiz_question_create_service
    ),
):
    """Delete one quiz question and redirect to quiz edit."""
    edit_view = edit_service.get_edit_view(slug)

    try:
        result = create_service.delete_question(
            AdminQuizQuestionDeleteRequest(slug=slug, question_id=question_id)
        )
    except AdminQuizQuestionCreateError as exc:
        if edit_view is None:
            course = runtime.get_course(slug)
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
            return templates.TemplateResponse(
                request,
                "not_found.html",
                {
                    "title": "Тест не найден",
                    "message": "Для этого курса итоговый тест не создан.",
                },
                status_code=404,
            )
        return _render_admin_quiz_edit_page(
            request,
            edit_view,
            error_message=exc.message,
        )

    return RedirectResponse(
        url=f"/admin/courses/{result.slug}/quiz/edit",
        status_code=303,
    )


def _handle_admin_quiz_question_reorder(
    slug: str,
    question_id: str,
    request: Request,
    runtime: ContentRuntime,
    edit_service: AdminQuizEditService,
    reorder_service: AdminQuizQuestionReorderService,
    *,
    direction: str,
) -> Union[RedirectResponse, HTMLResponse]:
    """Shared handler for quiz question move-up/move-down POST requests."""
    edit_view = edit_service.get_edit_view(slug)

    reorder_request = AdminQuizQuestionReorderRequest(
        slug=slug,
        question_id=question_id,
    )
    try:
        if direction == "up":
            result = reorder_service.move_up(reorder_request)
        else:
            result = reorder_service.move_down(reorder_request)
    except AdminQuizQuestionReorderError as exc:
        if edit_view is not None:
            return _render_admin_quiz_edit_page(
                request,
                edit_view,
                error_message=exc.message,
            )

        course = runtime.get_course(slug)
        if course is None or exc.message in {
            "Курс не найден.",
            "Некорректный идентификатор курса.",
        }:
            return templates.TemplateResponse(
                request,
                "not_found.html",
                {
                    "title": "Курс не найден",
                    "message": "Запрошенный курс недоступен или не существует.",
                },
                status_code=404,
            )

        if exc.message == "Тест не найден.":
            return templates.TemplateResponse(
                request,
                "not_found.html",
                {
                    "title": "Тест не найден",
                    "message": "Для этого курса итоговый тест не создан.",
                },
                status_code=404,
            )

        return templates.TemplateResponse(
            request,
            "not_found.html",
            {
                "title": "Ошибка",
                "message": exc.message,
            },
            status_code=200,
        )

    return RedirectResponse(
        url=f"/admin/courses/{result.slug}/quiz/edit",
        status_code=303,
    )


@router.post(
    "/admin/courses/{slug}/quiz/questions/{question_id}/move-up",
    include_in_schema=False,
)
async def admin_quiz_question_move_up(
    slug: str,
    question_id: str,
    request: Request,
    runtime: ContentRuntime = Depends(get_content_runtime),
    edit_service: AdminQuizEditService = Depends(get_admin_quiz_edit_service),
    reorder_service: AdminQuizQuestionReorderService = Depends(
        get_admin_quiz_question_reorder_service
    ),
):
    """Move one quiz question up in the questions list."""
    return _handle_admin_quiz_question_reorder(
        slug,
        question_id,
        request,
        runtime,
        edit_service,
        reorder_service,
        direction="up",
    )


@router.post(
    "/admin/courses/{slug}/quiz/questions/{question_id}/move-down",
    include_in_schema=False,
)
async def admin_quiz_question_move_down(
    slug: str,
    question_id: str,
    request: Request,
    runtime: ContentRuntime = Depends(get_content_runtime),
    edit_service: AdminQuizEditService = Depends(get_admin_quiz_edit_service),
    reorder_service: AdminQuizQuestionReorderService = Depends(
        get_admin_quiz_question_reorder_service
    ),
):
    """Move one quiz question down in the questions list."""
    return _handle_admin_quiz_question_reorder(
        slug,
        question_id,
        request,
        runtime,
        edit_service,
        reorder_service,
        direction="down",
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
