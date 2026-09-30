"""Create a scoped, portable export of one company's Mentor Connect data.

The export is intentionally operational rather than a public download feature.
It is run by a trusted platform operator during customer offboarding or a data
access request.  It never includes authentication secrets or platform-wide
security records, and it refuses to include filesystem content outside the
selected company's directories.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sqlite3
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from app.database.backup import create_database_backup
from app.database.db import get_connection
from app.services.tenant_content_runtime_registry import LEGACY_COMPANY_ID


class CompanyDataExportError(RuntimeError):
    """Raised when a complete tenant-scoped export cannot be created."""


@dataclass(frozen=True)
class CompanyDataExportResult:
    """Summary of one successfully written tenant export."""

    output_path: Path
    company_id: str
    archive_sha256: str
    record_counts: Mapping[str, int]
    course_files: int
    upload_files: int


_EXPORT_FORMAT = "mentorconnect-company-export-v1"
_CHUNK_SIZE = 1024 * 1024


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_company_data_export(
    *,
    db_path: Path,
    company_id: str,
    courses_dir: Path,
    uploads_dir: Path,
    output_path: Path,
    clock: Callable[[], datetime] = _utc_now,
) -> CompanyDataExportResult:
    """Write one complete export without reading another tenant's data.

    ``output_path`` must not exist.  The resulting gzip-compressed tar archive
    is mode ``0600`` and should be held in a mode ``0700`` operator directory
    until it is delivered through an approved encrypted channel and removed.
    """
    source_db = Path(db_path).resolve()
    courses_root = Path(courses_dir).resolve()
    uploads_root = Path(uploads_dir).resolve()
    destination = Path(output_path).resolve()
    normalized_company_id = _validate_company_id(company_id)
    created_at = _validate_clock(clock())

    if not source_db.is_file():
        raise FileNotFoundError(source_db)
    for directory in (courses_root, uploads_root):
        if not directory.is_dir():
            raise NotADirectoryError(directory)
    if destination == source_db:
        raise CompanyDataExportError("output path must not be the live database")
    if destination.exists():
        raise FileExistsError(destination)

    if not destination.parent.is_dir():
        raise NotADirectoryError(destination.parent)
    if destination.parent.stat().st_mode & 0o077:
        raise CompanyDataExportError(
            "output directory must not grant group or other access"
        )
    for source_root in (courses_root, uploads_root):
        if _is_within(destination, source_root):
            raise CompanyDataExportError(
                "output archive must not be stored inside tenant runtime data"
            )
    temporary_output = destination.with_name(f".{destination.name}.tmp")
    if temporary_output.exists():
        raise FileExistsError(temporary_output)

    destination_written = False
    try:
        with tempfile.TemporaryDirectory(
            prefix="mentorconnect-company-export-",
            dir=destination.parent,
        ) as snapshot_root:
            snapshot = create_database_backup(
                source_db,
                Path(snapshot_root),
                keep_last=1,
                clock=lambda: created_at,
            )
            payloads, company = _load_company_payloads(
                snapshot,
                normalized_company_id,
            )
            course_files = _collect_course_files(
                courses_root,
                normalized_company_id,
                payloads["courses"],
            )
            upload_files = _collect_upload_files(uploads_root, normalized_company_id)
            inventory = _build_file_inventory(course_files, upload_files)
            manifest = _build_manifest(
                company=company,
                created_at=created_at,
                payloads=payloads,
                inventory=inventory,
            )
            _write_archive(
                temporary_output,
                created_at=created_at,
                manifest=manifest,
                payloads=payloads,
                course_files=course_files,
                upload_files=upload_files,
                inventory=inventory,
            )
        os.replace(temporary_output, destination)
        destination_written = True
        destination.chmod(0o600)
    except Exception:
        temporary_output.unlink(missing_ok=True)
        if destination_written:
            destination.unlink(missing_ok=True)
        raise

    return CompanyDataExportResult(
        output_path=destination,
        company_id=normalized_company_id,
        archive_sha256=_sha256(destination),
        record_counts={name: len(rows) for name, rows in payloads.items()},
        course_files=len(course_files),
        upload_files=len(upload_files),
    )


def _validate_company_id(company_id: str) -> str:
    if not isinstance(company_id, str):
        raise TypeError("company_id must be a string")
    normalized = company_id.strip()
    if not normalized or normalized in {".", ".."}:
        raise ValueError("company_id must be a non-empty safe path component")
    if "/" in normalized or "\\" in normalized:
        raise ValueError("company_id must be a non-empty safe path component")
    return normalized


def _validate_clock(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        raise ValueError("export clock must return a timezone-aware datetime")
    return moment.astimezone(timezone.utc)


def _load_company_payloads(
    snapshot_path: Path,
    company_id: str,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    with get_connection(snapshot_path) as connection:
        company_row = connection.execute(
            """
            SELECT id, name, is_active, created_at, updated_at
            FROM companies
            WHERE id = ?
            """,
            (company_id,),
        ).fetchone()
        if company_row is None:
            raise CompanyDataExportError(f"company does not exist: {company_id}")

        payloads = {
            "company": [_row_to_dict(company_row)],
            "departments": _select_rows(
                connection,
                """
                SELECT id, company_id, name, is_active, created_at, updated_at
                FROM company_departments
                WHERE company_id = ?
                ORDER BY id
                """,
                company_id,
            ),
            "members": _select_rows(
                connection,
                """
                SELECT
                    memberships.id AS membership_id,
                    memberships.company_id,
                    memberships.role AS company_role,
                    memberships.is_active AS membership_is_active,
                    memberships.created_at AS membership_created_at,
                    memberships.updated_at AS membership_updated_at,
                    users.id AS user_id,
                    users.telegram_id,
                    users.username,
                    users.first_name,
                    users.last_name,
                    credentials.email
                FROM company_memberships AS memberships
                JOIN users ON users.id = memberships.user_id
                LEFT JOIN user_password_credentials AS credentials
                    ON credentials.user_id = users.id
                WHERE memberships.company_id = ?
                ORDER BY memberships.id
                """,
                company_id,
            ),
            "member_organizations": _select_rows(
                connection,
                """
                SELECT company_id, user_id, department_id, manager_user_id, updated_at
                FROM company_member_organizations
                WHERE company_id = ?
                ORDER BY user_id
                """,
                company_id,
            ),
            "usage_limits": _select_rows(
                connection,
                """
                SELECT company_id, max_active_members, max_courses, updated_at
                FROM company_usage_limits
                WHERE company_id = ?
                """,
                company_id,
            ),
            "courses": _select_rows(
                connection,
                """
                SELECT id, company_id, slug, title, description, cover_path,
                       sort_order, status, created_at, updated_at
                FROM courses
                WHERE company_id = ?
                ORDER BY id
                """,
                company_id,
            ),
            "lessons": _select_rows(
                connection,
                """
                SELECT lessons.id, lessons.course_id, lessons.title, lessons.description,
                       lessons.lesson_type, lessons.content, lessons.media_path,
                       lessons.sort_order, lessons.status, lessons.created_at,
                       lessons.updated_at
                FROM lessons
                JOIN courses ON courses.id = lessons.course_id
                WHERE courses.company_id = ?
                ORDER BY lessons.id
                """,
                company_id,
            ),
            "enrollments": _select_rows(
                connection,
                """
                SELECT id, company_id, user_id, course_id, status, progress_percent,
                       assigned_at, assigned_by_user_id, due_at, development_source,
                       development_reason, started_at, completed_at
                FROM enrollments
                WHERE company_id = ?
                ORDER BY id
                """,
                company_id,
            ),
            "lesson_progress": _select_rows(
                connection,
                """
                SELECT id, company_id, user_id, lesson_id, status, started_at, completed_at
                FROM lesson_progress
                WHERE company_id = ?
                ORDER BY id
                """,
                company_id,
            ),
            "quiz_attempts": _select_rows(
                connection,
                """
                SELECT id, company_id, user_id, course_slug, quiz_version, started_at,
                       finished_at, questions_count, correct_answers, score_percent, passed
                FROM quiz_attempts
                WHERE company_id = ?
                ORDER BY id
                """,
                company_id,
            ),
            "quiz_answers": _select_rows(
                connection,
                """
                SELECT answers.id, answers.attempt_id, answers.question_id,
                       answers.selected_option_id, answers.is_correct
                FROM quiz_answers AS answers
                JOIN quiz_attempts AS attempts ON attempts.id = answers.attempt_id
                WHERE attempts.company_id = ?
                ORDER BY answers.id
                """,
                company_id,
            ),
            "practical_task_attempts": _select_rows(
                connection,
                """
                SELECT id, company_id, user_id, course_slug, lesson_slug, task_title,
                       task_description, expected_result, learner_answer, score, max_score,
                       passed, feedback_summary, feedback_strengths_json,
                       feedback_improvements_json, status, started_at, reviewed_at
                FROM practical_task_attempts
                WHERE company_id = ?
                ORDER BY id
                """,
                company_id,
            ),
            "web_lesson_progress": _select_rows(
                connection,
                """
                SELECT id, company_id, user_id, course_slug, lesson_id, completed_at
                FROM web_lesson_progress
                WHERE company_id = ?
                ORDER BY id
                """,
                company_id,
            ),
            "knowledge_documents": _select_rows(
                connection,
                """
                SELECT id, company_id, document_id, title, original_filename, source_type,
                       source_language, extracted_text, status, version, created_at, updated_at
                FROM knowledge_documents
                WHERE company_id = ?
                ORDER BY id
                """,
                company_id,
            ),
            "knowledge_document_chunks": _select_rows(
                connection,
                """
                SELECT id, company_id, document_id, chunk_index, text, start_char, end_char,
                       created_at
                FROM knowledge_document_chunks
                WHERE company_id = ?
                ORDER BY id
                """,
                company_id,
            ),
        }
    return payloads, _row_to_dict(company_row)


def _select_rows(
    connection: sqlite3.Connection,
    query: str,
    company_id: str,
) -> list[dict[str, Any]]:
    return [_row_to_dict(row) for row in connection.execute(query, (company_id,))]


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _collect_course_files(
    courses_root: Path,
    company_id: str,
    courses: Iterable[Mapping[str, Any]],
) -> list[tuple[Path, str]]:
    course_records = tuple(courses)
    company_root = _company_courses_root(
        courses_root,
        company_id,
        allow_missing=not course_records,
    )
    if company_root is None:
        return []

    files: list[tuple[Path, str]] = []
    for course in course_records:
        slug = _validate_company_id(str(course["slug"]))
        candidate = company_root / slug
        if candidate.is_symlink():
            raise CompanyDataExportError(
                "refusing symbolic link as company course directory"
            )
        course_directory = candidate.resolve()
        if course_directory.parent != company_root:
            raise CompanyDataExportError("course slug escaped its tenant directory")
        if not course_directory.is_dir():
            raise CompanyDataExportError(
                f"course content directory is missing: {slug}"
            )
        files.extend(_collect_regular_files(course_directory, f"files/courses/{slug}"))
    return files


def _company_courses_root(
    courses_root: Path,
    company_id: str,
    *,
    allow_missing: bool = False,
) -> Path | None:
    if company_id == LEGACY_COMPANY_ID:
        return courses_root
    candidate = courses_root / company_id
    if candidate.is_symlink():
        raise CompanyDataExportError("refusing symbolic link as company courses directory")
    company_root = candidate.resolve()
    if company_root.parent != courses_root:
        raise CompanyDataExportError("company directory escaped courses root")
    if not company_root.exists() and allow_missing:
        return None
    if not company_root.is_dir():
        raise CompanyDataExportError("company courses directory is missing")
    return company_root


def _collect_upload_files(uploads_root: Path, company_id: str) -> list[tuple[Path, str]]:
    candidate = uploads_root / company_id
    if candidate.is_symlink():
        raise CompanyDataExportError("refusing symbolic link as company uploads directory")
    company_root = candidate.resolve()
    if company_root.parent != uploads_root:
        raise CompanyDataExportError("company directory escaped uploads root")
    if not company_root.exists():
        return []
    if not company_root.is_dir():
        raise CompanyDataExportError("company uploads path is not a directory")
    return _collect_regular_files(company_root, "files/uploads")


def _collect_regular_files(root: Path, archive_root: str) -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise CompanyDataExportError(f"refusing symbolic link in tenant data: {path}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise CompanyDataExportError(f"refusing non-regular tenant file: {path}")
        relative_path = path.relative_to(root).as_posix()
        files.append((path, f"{archive_root}/{relative_path}"))
    return files


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _build_file_inventory(
    course_files: Iterable[tuple[Path, str]],
    upload_files: Iterable[tuple[Path, str]],
) -> list[dict[str, Any]]:
    return [
        {
            "path": archive_name,
            "bytes": source.stat().st_size,
            "sha256": _sha256(source),
        }
        for source, archive_name in [*course_files, *upload_files]
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _build_manifest(
    *,
    company: Mapping[str, Any],
    created_at: datetime,
    payloads: Mapping[str, list[dict[str, Any]]],
    inventory: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "format": _EXPORT_FORMAT,
        "created_at": created_at.isoformat(),
        "company": company,
        "record_counts": {name: len(rows) for name, rows in payloads.items()},
        "course_files": sum(
            1 for entry in inventory if str(entry["path"]).startswith("files/courses/")
        ),
        "upload_files": sum(
            1 for entry in inventory if str(entry["path"]).startswith("files/uploads/")
        ),
        "excluded": [
            "password hashes",
            "MFA secrets",
            "web sessions and application secrets",
            "platform administrators and platform audit events",
            "temporary support-access records",
            "other companies' records and files",
        ],
    }


def _write_archive(
    path: Path,
    *,
    created_at: datetime,
    manifest: Mapping[str, Any],
    payloads: Mapping[str, list[dict[str, Any]]],
    course_files: Iterable[tuple[Path, str]],
    upload_files: Iterable[tuple[Path, str]],
    inventory: Sequence[Mapping[str, Any]],
) -> None:
    with path.open("xb") as output:
        os.fchmod(output.fileno(), 0o600)
        with tarfile.open(
            mode="w|gz",
            fileobj=output,
            format=tarfile.PAX_FORMAT,
        ) as archive:
            _add_json(archive, "manifest.json", manifest, created_at)
            for name, rows in payloads.items():
                _add_json(archive, f"data/{name}.json", rows, created_at)
            _add_json(archive, "file-inventory.json", list(inventory), created_at)
            for source, archive_name in [*course_files, *upload_files]:
                _add_regular_file(archive, source, archive_name, created_at)


def _add_json(
    archive: tarfile.TarFile,
    name: str,
    payload: object,
    created_at: datetime,
) -> None:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    info = tarfile.TarInfo(name)
    info.size = len(encoded)
    info.mode = 0o600
    info.mtime = int(created_at.timestamp())
    archive.addfile(info, io.BytesIO(encoded))


def _add_regular_file(
    archive: tarfile.TarFile,
    source: Path,
    archive_name: str,
    created_at: datetime,
) -> None:
    info = tarfile.TarInfo(archive_name)
    info.size = source.stat().st_size
    info.mode = 0o600
    info.mtime = int(created_at.timestamp())
    with source.open("rb") as source_file:
        archive.addfile(info, source_file)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--company-id", required=True)
    parser.add_argument("--courses-dir", required=True, type=Path)
    parser.add_argument("--uploads-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Create one operator-controlled company export."""
    args = _build_parser().parse_args(argv)
    try:
        result = create_company_data_export(
            db_path=args.db,
            company_id=args.company_id,
            courses_dir=args.courses_dir,
            uploads_dir=args.uploads_dir,
            output_path=args.output,
        )
    except (CompanyDataExportError, OSError, sqlite3.Error, TypeError, ValueError) as error:
        print(f"company export failed: {error}")
        return 1

    print(result.output_path)
    print(f"company_id={result.company_id}")
    print(f"archive_sha256={result.archive_sha256}")
    print(f"course_files={result.course_files}")
    print(f"upload_files={result.upload_files}")
    print("status=complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
