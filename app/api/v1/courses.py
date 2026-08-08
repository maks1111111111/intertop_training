"""Read-only course endpoints backed by ContentRuntime."""

from __future__ import annotations

from typing import Union

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from app.api.dto.course import CourseDetailDTO, CourseListDTO, LessonDetailDTO
from app.api.mappers import course_mapper
from app.content.runtime import ContentRuntime

router = APIRouter(tags=["courses"])


def get_content_runtime(request: Request) -> ContentRuntime:
    """Return the ContentRuntime instance attached to the application."""
    return request.app.state.content_runtime


@router.get("/courses", response_model=CourseListDTO)
def list_courses(
    content_runtime: ContentRuntime = Depends(get_content_runtime),
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
    content_runtime: ContentRuntime = Depends(get_content_runtime),
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
    content_runtime: ContentRuntime = Depends(get_content_runtime),
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
            return course_mapper.to_lesson_detail(lesson)

    return JSONResponse(
        status_code=404,
        content={
            "error": {
                "code": "lesson_not_found",
                "message": "Lesson not found.",
            }
        },
    )
