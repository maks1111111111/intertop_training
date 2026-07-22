from pathlib import Path

from app.repositories.course_repository import CourseRepository
from app.repositories.lesson_repository import LessonRepository
from app.services.scanner import scan_courses


def sync_courses(
    base_dir: Path,
    db_path: Path,
) -> None:
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