"""Unified Content Engine contract.

This module contains the single source of truth for Content Engine constants.
All platform components must use only these constants.
"""

COURSE_JSON_FILENAME = "course.json"
LESSON_JSON_FILENAME = "lesson.json"
QUIZ_JSON_FILENAME = "quiz.json"

COURSE_COVER_STEM = "cover"
LESSON_IMAGE_STEM = "image"
LESSON_NARRATION_STEM = "narration"

_COVER_EXTENSION_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
_IMAGE_EXTENSION_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")
_NARRATION_EXTENSION_SUFFIXES = (".mp3", ".m4a", ".wav", ".ogg")

COURSE_COVER_EXTENSIONS = frozenset(_COVER_EXTENSION_SUFFIXES)
LESSON_IMAGE_EXTENSIONS = frozenset(_IMAGE_EXTENSION_SUFFIXES)
LESSON_NARRATION_EXTENSIONS = frozenset(_NARRATION_EXTENSION_SUFFIXES)

COURSE_COVER_FILENAMES = tuple(
    f"{COURSE_COVER_STEM}{suffix}" for suffix in _COVER_EXTENSION_SUFFIXES
)
LESSON_IMAGE_FILENAMES = tuple(
    f"{LESSON_IMAGE_STEM}{suffix}" for suffix in _IMAGE_EXTENSION_SUFFIXES
)
LESSON_NARRATION_FILENAMES = tuple(
    f"{LESSON_NARRATION_STEM}{suffix}" for suffix in _NARRATION_EXTENSION_SUFFIXES
)
