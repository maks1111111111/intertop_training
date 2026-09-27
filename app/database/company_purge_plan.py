"""Build a read-only, tenant-scoped plan before an offboarding data purge."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from app.database.company_offboarding import assess_company_offboarding
from app.database.db import get_connection
from app.services.tenant_content_runtime_registry import LEGACY_COMPANY_ID


class CompanyPurgePlanError(RuntimeError):
    """Raised when an eligible company's purge scope cannot be planned safely."""


@dataclass(frozen=True)
class CompanyPurgePlan:
    """Counts of data that a future explicitly confirmed purge may remove."""

    company_id: str
    record_counts: Mapping[str, int]
    course_directories: int
    upload_files: int
    upload_bytes: int


def build_company_purge_plan(
    *,
    db_path: Path,
    company_id: str,
    courses_dir: Path,
    uploads_dir: Path,
) -> CompanyPurgePlan:
    """Describe one eligible tenant's data without deleting or changing it."""
    status = assess_company_offboarding(db_path, company_id)
    if not status.is_eligible:
        raise CompanyPurgePlanError(
            "company is not eligible for a working-data purge: " + status.reason
        )

    source_db = Path(db_path).resolve()
    courses_root = Path(courses_dir).resolve()
    uploads_root = Path(uploads_dir).resolve()
    for directory in (courses_root, uploads_root):
        if not directory.is_dir():
            raise NotADirectoryError(directory)

    with get_connection(source_db) as connection:
        counts = _record_counts(connection, status.company_id)
        course_slugs = [
            str(row["slug"])
            for row in connection.execute(
                "SELECT slug FROM courses WHERE company_id = ? ORDER BY id",
                (status.company_id,),
            )
        ]

    course_directories = _count_course_directories(
        courses_root,
        status.company_id,
        course_slugs,
    )
    upload_files, upload_bytes = _count_upload_files(
        uploads_root,
        status.company_id,
    )
    return CompanyPurgePlan(
        company_id=status.company_id,
        record_counts=counts,
        course_directories=course_directories,
        upload_files=upload_files,
        upload_bytes=upload_bytes,
    )


def _record_counts(
    connection: sqlite3.Connection,
    company_id: str,
) -> dict[str, int]:
    queries = {
        "company": "SELECT COUNT(*) FROM companies WHERE id = ?",
        "departments": "SELECT COUNT(*) FROM company_departments WHERE company_id = ?",
        "memberships": "SELECT COUNT(*) FROM company_memberships WHERE company_id = ?",
        "member_organizations": "SELECT COUNT(*) FROM company_member_organizations WHERE company_id = ?",
        "usage_limits": "SELECT COUNT(*) FROM company_usage_limits WHERE company_id = ?",
        "courses": "SELECT COUNT(*) FROM courses WHERE company_id = ?",
        "lessons": """
            SELECT COUNT(*) FROM lessons
            JOIN courses ON courses.id = lessons.course_id
            WHERE courses.company_id = ?
        """,
        "enrollments": "SELECT COUNT(*) FROM enrollments WHERE company_id = ?",
        "lesson_progress": "SELECT COUNT(*) FROM lesson_progress WHERE company_id = ?",
        "quiz_attempts": "SELECT COUNT(*) FROM quiz_attempts WHERE company_id = ?",
        "quiz_answers": """
            SELECT COUNT(*) FROM quiz_answers
            JOIN quiz_attempts ON quiz_attempts.id = quiz_answers.attempt_id
            WHERE quiz_attempts.company_id = ?
        """,
        "practical_task_attempts": "SELECT COUNT(*) FROM practical_task_attempts WHERE company_id = ?",
        "web_lesson_progress": "SELECT COUNT(*) FROM web_lesson_progress WHERE company_id = ?",
        "knowledge_documents": "SELECT COUNT(*) FROM knowledge_documents WHERE company_id = ?",
        "knowledge_document_chunks": "SELECT COUNT(*) FROM knowledge_document_chunks WHERE company_id = ?",
        "support_access_records": "SELECT COUNT(*) FROM platform_support_accesses WHERE company_id = ?",
        "orphanable_user_accounts": """
            SELECT COUNT(*)
            FROM users
            JOIN company_memberships AS target
                ON target.user_id = users.id AND target.company_id = ?
            WHERE NOT EXISTS (
                SELECT 1 FROM company_memberships AS other
                WHERE other.user_id = users.id AND other.company_id != ?
            )
              AND NOT EXISTS (
                SELECT 1 FROM platform_admins
                WHERE platform_admins.user_id = users.id
            )
        """,
    }
    counts: dict[str, int] = {}
    for name, query in queries.items():
        parameters = (company_id, company_id) if name == "orphanable_user_accounts" else (company_id,)
        row = connection.execute(query, parameters).fetchone()
        assert row is not None
        counts[name] = int(row[0])
    return counts


def _count_course_directories(
    courses_root: Path,
    company_id: str,
    course_slugs: Sequence[str],
) -> int:
    root = courses_root if company_id == LEGACY_COMPANY_ID else courses_root / company_id
    if root.is_symlink():
        raise CompanyPurgePlanError("refusing symbolic link as company courses directory")
    resolved_root = root.resolve()
    if company_id != LEGACY_COMPANY_ID and resolved_root.parent != courses_root:
        raise CompanyPurgePlanError("company courses directory escaped courses root")

    found = 0
    for slug in course_slugs:
        _validate_component(slug, "course slug")
        candidate = resolved_root / slug
        if candidate.is_symlink():
            raise CompanyPurgePlanError("refusing symbolic link as course directory")
        if not candidate.is_dir():
            raise CompanyPurgePlanError(f"course content directory is missing: {slug}")
        if candidate.resolve().parent != resolved_root:
            raise CompanyPurgePlanError("course directory escaped company courses root")
        found += 1
    return found


def _count_upload_files(uploads_root: Path, company_id: str) -> tuple[int, int]:
    candidate = uploads_root / company_id
    if candidate.is_symlink():
        raise CompanyPurgePlanError("refusing symbolic link as company uploads directory")
    if not candidate.exists():
        return 0, 0
    root = candidate.resolve()
    if root.parent != uploads_root or not root.is_dir():
        raise CompanyPurgePlanError("company uploads directory is invalid")

    files = 0
    total_bytes = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            raise CompanyPurgePlanError("refusing symbolic link in company uploads")
        if path.is_dir():
            continue
        if not path.is_file():
            raise CompanyPurgePlanError("refusing non-regular file in company uploads")
        files += 1
        total_bytes += path.stat().st_size
    return files, total_bytes


def _validate_component(value: str, label: str) -> None:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise CompanyPurgePlanError(f"{label} is not a safe path component")


def format_company_purge_plan(plan: CompanyPurgePlan) -> str:
    """Render a deterministic plan without exposing customer content."""
    lines = ["COMPANY_PURGE_PLAN", f"company_id={plan.company_id}"]
    for name, count in plan.record_counts.items():
        lines.append(f"records_{name}={count}")
    lines.extend(
        [
            f"course_directories={plan.course_directories}",
            f"upload_files={plan.upload_files}",
            f"upload_bytes={plan.upload_bytes}",
            "status=dry_run_only",
        ]
    )
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--company-id", required=True)
    parser.add_argument("--courses-dir", required=True, type=Path)
    parser.add_argument("--uploads-dir", required=True, type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run a dry-run purge planning check."""
    args = _build_parser().parse_args(argv)
    try:
        plan = build_company_purge_plan(
            db_path=args.db,
            company_id=args.company_id,
            courses_dir=args.courses_dir,
            uploads_dir=args.uploads_dir,
        )
    except (CompanyPurgePlanError, OSError, sqlite3.Error, TypeError, ValueError) as error:
        print(f"purge plan failed: {error}", file=sys.stderr)
        return 1
    print(format_company_purge_plan(plan))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
