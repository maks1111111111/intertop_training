"""Read-only course endpoints backed by ContentRuntime."""

from __future__ import annotations

from typing import Optional, Union

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.dto.course import CourseDetailDTO, CourseListDTO, LessonDetailDTO
from app.api.mappers import course_mapper
from app.content.runtime import ContentRuntime
from app.services.tenant_content_runtime_registry import (
    TenantContentRuntimeRegistry,
)
from app.web.router import get_current_web_identity
from app.web.web_identity_service import WebIdentity

router = APIRouter(tags=["courses"])


def get_content_runtime(request: Request) -> ContentRuntime:
    """Return the ContentRuntime instance attached to the application."""
    return request.app.state.content_runtime


def require_api_identity(
    identity: Optional[WebIdentity] = Depends(get_current_web_identity),
) -> WebIdentity:
    """Require the signed session identity for tenant-scoped API reads."""
    if identity is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return identity


def get_tenant_content_runtime(
    request: Request,
    identity: WebIdentity = Depends(require_api_identity),
) -> ContentRuntime:
    """Return only the course runtime owned by the signed session tenant."""
    registry: TenantContentRuntimeRegistry = request.app.state.tenant_content_runtimes
    legacy_runtime = request.app.state.content_runtime
    # Embedded and test applications may explicitly replace the legacy
    # runtime. Production configures it as the registry's legacy runtime.
    if legacy_runtime is not registry.legacy_runtime:
        return legacy_runtime
    return registry.get_runtime(identity.company_id)


@router.get("/courses", response_model=CourseListDTO)
def list_courses(
    content_runtime: ContentRuntime = Depends(get_tenant_content_runtime),
) -> CourseListDTO:
    """Return all published courses available in the runtime cache."""
    return course_mapper.to_summary_list(content_runtime.get_courses())


@router.get(
    "/courses/{slug}",
    response_model=CourseDetailDTO,
    responses={
        404: {
            "description": "Course not found.",
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": "course_not_found",
                            "message": "Course not found.",
                        }
                    }
                }
            },
        }
    },
)
def get_course(
    slug: str,
    content_runtime: ContentRuntime = Depends(get_tenant_content_runtime),
) -> Union[CourseDetailDTO, JSONResponse]:
    """Return one published course by slug."""
    course = content_runtime.get_course(slug)
    if course is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "course_not_found",
                    "message": "Course not found.",
                }
            },
        )
    return course_mapper.to_detail(course)


@router.get(
    "/courses/{slug}/lessons/{lesson_id}",
    response_model=LessonDetailDTO,
    responses={
        404: {
            "description": "Course or lesson not found.",
            "content": {
                "application/json": {
                    "examples": {
                        "course_not_found": {
                            "value": {
                                "error": {
                                    "code": "course_not_found",
                                    "message": "Course not found.",
                                }
                            }
                        },
                        "lesson_not_found": {
                            "value": {
                                "error": {
                                    "code": "lesson_not_found",
                                    "message": "Lesson not found.",
                                }
                            }
                        },
                    }
                }
            },
        }
    },
)
def get_lesson(
    slug: str,
    lesson_id: str,
    content_runtime: ContentRuntime = Depends(get_tenant_content_runtime),
) -> Union[LessonDetailDTO, JSONResponse]:
    """Return one published lesson by course slug and lesson directory name."""
    course = content_runtime.get_course(slug)
    if course is None:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": "course_not_found",
                    "message": "Course not found.",
                }
            },
        )

    for lesson in course.lessons:
        if lesson.path.name == lesson_id:
            return course_mapper.to_lesson_detail(course, lesson)

    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "code": "lesson_not_found",
                "message": "Lesson not found.",
            }
        },
    )
