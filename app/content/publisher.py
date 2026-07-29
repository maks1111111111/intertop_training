"""Safe course publication service for the Content Engine.

Publishing changes ``course.json`` only after :func:`validate_course` reports
that the course passes the release gate.
"""

import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.content.content_pack import ContentPack, build_content_pack
from app.content.contract import COURSE_JSON_FILENAME
from app.content.diff import SnapshotDiff, compare_snapshots
from app.content.history import PUBLISH_HISTORY_FILENAME, record_publication
from app.content.release_manifest import build_release_manifest
from app.content.release_manifest_io import save_release_manifest
from app.content.snapshots import SNAPSHOTS_DIR_NAME, create_snapshot
from app.content.validator import validate_course

RELEASE_MANIFEST_FILENAME = "release-manifest.json"


@dataclass(frozen=True)
class PublicationResult:
    """Result of a :func:`publish_course` operation."""

    published: bool
    gate: dict
    content_pack: Optional[ContentPack] = None


def _resolve_next_version(manifest: dict) -> Optional[int]:
    """Return the version a course should receive on publication.

    Missing ``version`` is treated as ``0`` and becomes ``1``.
    Integer values ``>= 0`` are incremented by one.
    Invalid types and negative integers return ``None``.
    """
    if "version" not in manifest:
        return 1

    version_value = manifest["version"]
    if isinstance(version_value, bool) or not isinstance(version_value, int):
        return None

    if version_value < 0:
        return None

    return version_value + 1


def _gate_blocked_for_publication(gate: dict) -> dict:
    """Return a release gate that blocks publication."""
    return {
        "allowed": False,
        "ready": False,
        "errors": max(gate["errors"], 1),
        "warnings": gate["warnings"],
    }


def _utc_timestamp() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _snapshot_dir_path(course_dir: Path, version: int) -> Path:
    """Return the snapshot directory path for a course version."""
    return course_dir / SNAPSHOTS_DIR_NAME / f"v{version:04d}"


def _previous_snapshot_path(course_dir: Path, version: int) -> Optional[Path]:
    """Return the previous snapshot directory, if one exists."""
    if version <= 1:
        return None

    previous_snapshot = _snapshot_dir_path(course_dir, version - 1)
    if previous_snapshot.is_dir():
        return previous_snapshot

    return None


def _prepare_snapshot_for_diff(snapshot: Path) -> Path:
    """Return a temporary copy of ``snapshot`` without publication service files.

    The original snapshot directory is never modified.
    """
    tmp = tempfile.mkdtemp()
    cleaned_snapshot = Path(tmp) / "snapshot"
    shutil.copytree(snapshot, cleaned_snapshot)
    for filename in (RELEASE_MANIFEST_FILENAME, PUBLISH_HISTORY_FILENAME):
        service_path = cleaned_snapshot / filename
        if service_path.is_file():
            service_path.unlink()
    return cleaned_snapshot


def _compare_with_previous_snapshot(
    previous_snapshot: Optional[Path],
    new_snapshot: Path,
) -> SnapshotDiff:
    """Compare a new snapshot with the previous one, or an empty baseline."""
    if previous_snapshot is not None:
        cleaned_previous = _prepare_snapshot_for_diff(previous_snapshot)
        cleaned_new = _prepare_snapshot_for_diff(new_snapshot)
        try:
            return compare_snapshots(cleaned_previous, cleaned_new)
        finally:
            shutil.rmtree(cleaned_previous.parent)
            shutil.rmtree(cleaned_new.parent)

    with tempfile.TemporaryDirectory() as tmp:
        empty_snapshot = Path(tmp) / "empty"
        empty_snapshot.mkdir()
        return compare_snapshots(empty_snapshot, new_snapshot)


def _complete_publication(
    course_dir: Path,
    *,
    version: int,
    gate: dict,
) -> ContentPack:
    """Create release artifacts and record publication history.

    Coordinates snapshot creation, diffing, manifest persistence, content
    pack building, and publication history without duplicating module logic.
    """
    snapshot_dir = create_snapshot(course_dir, version)
    previous_snapshot = _previous_snapshot_path(course_dir, version)
    diff = _compare_with_previous_snapshot(previous_snapshot, snapshot_dir)

    manifest = build_release_manifest(
        version=version,
        published=_utc_timestamp(),
        snapshot=snapshot_dir,
        diff=diff,
    )
    save_release_manifest(manifest, snapshot_dir / RELEASE_MANIFEST_FILENAME)
    content_pack = build_content_pack(course_dir, snapshot_dir, version)
    record_publication(course_dir, published=True, gate=gate)
    return content_pack


def _ignore_publication_artifacts(course_dir_resolved: Path):
    """Return a copytree ignore callback that skips publication artifacts."""
    ignored_names = {SNAPSHOTS_DIR_NAME, PUBLISH_HISTORY_FILENAME}

    def _ignore(directory: str, names: list[str]) -> list[str]:
        if Path(directory).resolve() == course_dir_resolved:
            return [name for name in names if name in ignored_names]
        return []

    return _ignore


def _validate_published_candidate(
    course_dir: Path,
    manifest: dict,
    *,
    next_version: int,
) -> Optional[dict]:
    """Validate a temporary copy of the course with ``status`` set to ``published``.

    Returns the release gate for the candidate without modifying ``course_dir``,
    or ``None`` if the temporary copy cannot be created or written.
    """
    try:
        with tempfile.TemporaryDirectory() as tmp:
            candidate_dir = Path(tmp) / course_dir.name
            shutil.copytree(
                course_dir,
                candidate_dir,
                ignore=_ignore_publication_artifacts(course_dir.resolve()),
            )

            candidate_manifest = dict(manifest)
            candidate_manifest["status"] = "published"
            candidate_manifest["version"] = next_version
            candidate_json_path = candidate_dir / COURSE_JSON_FILENAME
            candidate_json_path.write_text(
                json.dumps(candidate_manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            candidate_report = validate_course(candidate_dir)
            return candidate_report.release_gate()
    except OSError:
        return None


def publish_course(course_dir: Path) -> PublicationResult:
    """Publish a course by setting ``status`` to ``published`` in ``course.json``.

    The course directory is validated first. Publication proceeds only when
    :meth:`~app.content.models.ValidationReport.release_gate` reports
    ``allowed`` is ``True``. Warnings do not block publication.

    If the course is already published, the operation is idempotent: other
    manifest fields are preserved and ``published`` is ``True``.

    Args:
        course_dir: Path to the course directory (for example ``courses/brands``).

    Returns:
        A :class:`PublicationResult` with publication status, release gate,
        and an optional :class:`~app.content.content_pack.ContentPack` when
        a new snapshot was created.
    """
    course_json_path = course_dir / COURSE_JSON_FILENAME

    try:
        raw_text = course_json_path.read_text(encoding="utf-8")
        manifest = json.loads(raw_text)
    except (OSError, json.JSONDecodeError):
        report = validate_course(course_dir)
        return PublicationResult(
            published=False,
            gate=report.release_gate(),
        )

    if not isinstance(manifest, dict):
        report = validate_course(course_dir)
        return PublicationResult(
            published=False,
            gate=report.release_gate(),
        )

    if manifest.get("status") == "published":
        report = validate_course(course_dir)
        gate = report.release_gate()
        if gate["allowed"]:
            return PublicationResult(published=True, gate=gate)
        return PublicationResult(published=False, gate=gate)

    next_version = _resolve_next_version(manifest)
    if next_version is None:
        report = validate_course(course_dir)
        return PublicationResult(
            published=False,
            gate=_gate_blocked_for_publication(report.release_gate()),
        )

    gate = _validate_published_candidate(
        course_dir,
        manifest,
        next_version=next_version,
    )

    if gate is None:
        report = validate_course(course_dir)
        return PublicationResult(
            published=False,
            gate=report.release_gate(),
        )

    if not gate["allowed"]:
        return PublicationResult(published=False, gate=gate)

    manifest["status"] = "published"
    manifest["version"] = next_version

    updated_text = json.dumps(manifest, ensure_ascii=False, indent=2)
    snapshot_dir = _snapshot_dir_path(course_dir, next_version)
    snapshot_existed_before = snapshot_dir.is_dir()

    try:
        original_text = course_json_path.read_text(encoding="utf-8")
    except OSError:
        return PublicationResult(published=False, gate=gate)

    try:
        course_json_path.write_text(updated_text, encoding="utf-8")
        content_pack = _complete_publication(
            course_dir,
            version=next_version,
            gate=gate,
        )
    except (OSError, ValueError, FileExistsError):
        try:
            course_json_path.write_text(original_text, encoding="utf-8")
        except OSError:
            pass

        if not snapshot_existed_before and snapshot_dir.exists():
            shutil.rmtree(snapshot_dir)

        raise

    return PublicationResult(
        published=True,
        gate=gate,
        content_pack=content_pack,
    )
