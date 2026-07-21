from pathlib import Path

from app.repositories.course_repository import CourseRepository
from app.services.scanner import scan_courses


def sync_courses(
    base_dir: Path,
    db_path: Path,
) -> None:
    course_repository = CourseRepository()
    courses = scan_courses(base_dir)

    for sort_order, course in enumerate(courses):
        course_repository.save(
            db_path=db_path,
            slug=course.slug,
            title=course.title,
            cover_path=course.cover_path,
            sort_order=sort_order,
        )