"""Safe course publication service for the Content Engine.

Publishing changes ``course.json`` only after :func:`validate_course` reports
that the course passes the release gate.
"""

import json
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from app.content.contract import COURSE_JSON_FILENAME
from app.content.validator import validate_course


def _validate_published_candidate(course_dir: Path, manifest: dict) -> Optional[dict]:
    """Validate a temporary copy of the course with ``status`` set to ``published``.

    Returns the release gate for the candidate without modifying ``course_dir``,
    or ``None`` if the temporary copy cannot be created or written.
    """
    try:
        with tempfile.TemporaryDirectory() as tmp:
            candidate_dir = Path(tmp) / course_dir.name
            shutil.copytree(course_dir, candidate_dir)

            candidate_manifest = dict(manifest)
            candidate_manifest["status"] = "published"
            candidate_json_path = candidate_dir / COURSE_JSON_FILENAME
            candidate_json_path.write_text(
                json.dumps(candidate_manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            candidate_report = validate_course(candidate_dir)
            return candidate_report.release_gate()
    except OSError:
        return None


def publish_course(course_dir: Path) -> dict:
    """Publish a course by setting ``status`` to ``published`` in ``course.json``.

    The course directory is validated first. Publication proceeds only when
    :meth:`~app.content.models.ValidationReport.release_gate` reports
    ``allowed`` is ``True``. Warnings do not block publication.

    If the course is already published, the operation is idempotent: other
    manifest fields are preserved and ``published`` is ``True``.

    Args:
        course_dir: Path to the course directory (for example ``courses/brands``).

    Returns:
        A dictionary with keys:

        ``published``
            ``True`` when ``course.json`` was updated or already published;
            ``False`` when publication was blocked or could not be completed.
        ``gate``
            The release gate dictionary from validation
            (:meth:`~app.content.models.ValidationReport.release_gate`).
    """
    course_json_path = course_dir / COURSE_JSON_FILENAME

    try:
        raw_text = course_json_path.read_text(encoding="utf-8")
        manifest = json.loads(raw_text)
    except (OSError, json.JSONDecodeError):
        report = validate_course(course_dir)
        return {
            "published": False,
            "gate": report.release_gate(),
        }

    if not isinstance(manifest, dict):
        report = validate_course(course_dir)
        return {
            "published": False,
            "gate": report.release_gate(),
        }

    if manifest.get("status") == "published":
        report = validate_course(course_dir)
        gate = report.release_gate()
        if gate["allowed"]:
            return {
                "published": True,
                "gate": gate,
            }
        return {
            "published": False,
            "gate": gate,
        }

    gate = _validate_published_candidate(course_dir, manifest)

    if gate is None:
        report = validate_course(course_dir)
        return {
            "published": False,
            "gate": report.release_gate(),
        }

    if not gate["allowed"]:
        return {
            "published": False,
            "gate": gate,
        }

    manifest["status"] = "published"

    try:
        course_json_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        return {
            "published": False,
            "gate": gate,
        }

    return {
        "published": True,
        "gate": gate,
    }
