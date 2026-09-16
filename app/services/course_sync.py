from pathlib import Path

from app.repositories.company_repository import CompanyRepository
from app.repositories.course_repository import CourseRepository
from app.repositories.lesson_repository import LessonRepository
from app.services.scanner import scan_courses


_LEGACY_COMPANY_ID = "intertop"


def sync_courses(
    base_dir: Path,
    db_path: Path,
    company_id: str = _LEGACY_COMPANY_ID,
) -> None:
    """Synchronize a course directory into the tenant-aware course catalog.

    The legacy root is also the application startup entry point.  When it is
    synchronized, include every active tenant's dedicated course directory so
    courses generated through the Web UI become available to progress,
    practical-task, and quiz persistence immediately after a restart.
    """
    course_repository = CourseRepository()
    lesson_repository = LessonRepository()

    courses = scan_courses(base_dir)

    for course_sort_order, course in enumerate(courses):
        course_id = course_repository.save(
            db_path=db_path,
            slug=course.slug,
            title=course.title,
            cover_path=course.cover_path,
            sort_order=course_sort_order,
            company_id=company_id,
        )

        for lesson_sort_order, lesson in enumerate(course.lessons):
            lesson_repository.save(
                db_path=db_path,
                course_id=course_id,
                slug=lesson.path.name,
                title=lesson.title,
                description=lesson.description,
                image_path=lesson.image_path,
                narration_path=lesson.narration_path,
                sort_order=lesson_sort_order,
            )

    if company_id != _LEGACY_COMPANY_ID:
        return

    courses_root = base_dir.resolve()
    for company in CompanyRepository().list_active(db_path):
        if company.id == _LEGACY_COMPANY_ID:
            continue
        tenant_courses_dir = (courses_root / company.id).resolve()
        if tenant_courses_dir.parent != courses_root:
            raise ValueError("Company course directory must be a direct child")
        sync_courses(
            base_dir=tenant_courses_dir,
            db_path=db_path,
            company_id=company.id,
        )
