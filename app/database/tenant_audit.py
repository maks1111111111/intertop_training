"""Read-only preflight audit for multi-company learning data."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.database.db import get_connection

LEGACY_COMPANY_ID = "intertop"


@dataclass(frozen=True)
class TenantAuditFinding:
    """One persisted record that needs tenant-data review."""

    code: str
    table_name: str
    record_id: int
    company_id: str
    detail: str


@dataclass(frozen=True)
class TenantAuditReport:
    """Non-mutating tenant integrity audit output."""

    findings: tuple[TenantAuditFinding, ...]

    @property
    def is_clean(self) -> bool:
        return not self.findings


def audit_tenant_data(db_path: Path) -> TenantAuditReport:
    """Read tenant ownership and membership anomalies without changing a DB."""
    with get_connection(db_path) as connection:
        findings = [
            *_find_unknown_company_records(connection),
            *_find_cross_tenant_enrollments(connection),
            *_find_cross_tenant_lesson_progress(connection),
            *_find_cross_tenant_assessment_attempts(connection),
            *_find_cross_tenant_knowledge_chunks(connection),
            *_find_nonmember_learning_records(connection),
        ]
    return TenantAuditReport(findings=tuple(findings))


def _find_unknown_company_records(
    connection: sqlite3.Connection,
) -> list[TenantAuditFinding]:
    findings: list[TenantAuditFinding] = []
    for table_name in (
        "courses",
        "enrollments",
        "lesson_progress",
        "quiz_attempts",
        "practical_task_attempts",
        "web_lesson_progress",
        "knowledge_documents",
        "knowledge_document_chunks",
    ):
        rows = connection.execute(
            f"""
            SELECT {table_name}.id, {table_name}.company_id
            FROM {table_name}
            LEFT JOIN companies
                ON companies.id = {table_name}.company_id
            WHERE companies.id IS NULL
            ORDER BY {table_name}.id ASC
            """
        ).fetchall()
        findings.extend(
            TenantAuditFinding(
                code="unknown_company",
                table_name=table_name,
                record_id=int(row["id"]),
                company_id=str(row["company_id"]),
                detail="company_id has no matching companies record",
            )
            for row in rows
        )
    return findings


def _find_cross_tenant_enrollments(
    connection: sqlite3.Connection,
) -> list[TenantAuditFinding]:
    rows = connection.execute(
        """
        SELECT
            enrollments.id,
            enrollments.company_id,
            courses.company_id AS course_company_id
        FROM enrollments
        JOIN courses ON courses.id = enrollments.course_id
        WHERE enrollments.company_id != courses.company_id
        ORDER BY enrollments.id ASC
        """
    ).fetchall()
    return [
        TenantAuditFinding(
            code="course_company_mismatch",
            table_name="enrollments",
            record_id=int(row["id"]),
            company_id=str(row["company_id"]),
            detail=(
                "course belongs to company_id="
                f"{str(row['course_company_id'])}"
            ),
        )
        for row in rows
    ]


def _find_cross_tenant_lesson_progress(
    connection: sqlite3.Connection,
) -> list[TenantAuditFinding]:
    rows = connection.execute(
        """
        SELECT
            lesson_progress.id,
            lesson_progress.company_id,
            courses.company_id AS course_company_id
        FROM lesson_progress
        JOIN lessons ON lessons.id = lesson_progress.lesson_id
        JOIN courses ON courses.id = lessons.course_id
        WHERE lesson_progress.company_id != courses.company_id
        ORDER BY lesson_progress.id ASC
        """
    ).fetchall()
    return [
        TenantAuditFinding(
            code="lesson_company_mismatch",
            table_name="lesson_progress",
            record_id=int(row["id"]),
            company_id=str(row["company_id"]),
            detail=(
                "lesson course belongs to company_id="
                f"{str(row['course_company_id'])}"
            ),
        )
        for row in rows
    ]


def _find_cross_tenant_assessment_attempts(
    connection: sqlite3.Connection,
) -> list[TenantAuditFinding]:
    findings: list[TenantAuditFinding] = []
    for table_name in ("quiz_attempts", "practical_task_attempts"):
        rows = connection.execute(
            f"""
            SELECT {table_name}.id, {table_name}.company_id, {table_name}.course_slug
            FROM {table_name}
            LEFT JOIN courses
                ON courses.company_id = {table_name}.company_id
               AND courses.slug = {table_name}.course_slug
            WHERE {table_name}.company_id != ?
              AND courses.id IS NULL
            ORDER BY {table_name}.id ASC
            """,
            (LEGACY_COMPANY_ID,),
        ).fetchall()
        findings.extend(
            TenantAuditFinding(
                code="assessment_course_company_mismatch",
                table_name=table_name,
                record_id=int(row["id"]),
                company_id=str(row["company_id"]),
                detail=(
                    "course_slug is not owned by this company: "
                    f"{str(row['course_slug'])}"
                ),
            )
            for row in rows
        )
    return findings


def _find_cross_tenant_knowledge_chunks(
    connection: sqlite3.Connection,
) -> list[TenantAuditFinding]:
    rows = connection.execute(
        """
        SELECT
            chunks.id,
            chunks.company_id,
            chunks.document_id
        FROM knowledge_document_chunks AS chunks
        LEFT JOIN knowledge_documents AS documents
            ON documents.company_id = chunks.company_id
           AND documents.document_id = chunks.document_id
        WHERE documents.id IS NULL
        ORDER BY chunks.id ASC
        """
    ).fetchall()
    return [
        TenantAuditFinding(
            code="knowledge_document_company_mismatch",
            table_name="knowledge_document_chunks",
            record_id=int(row["id"]),
            company_id=str(row["company_id"]),
            detail=(
                "document_id is not owned by this company: "
                f"{str(row['document_id'])}"
            ),
        )
        for row in rows
    ]


def _find_nonmember_learning_records(
    connection: sqlite3.Connection,
) -> list[TenantAuditFinding]:
    findings: list[TenantAuditFinding] = []
    for table_name in (
        "enrollments",
        "lesson_progress",
        "quiz_attempts",
        "practical_task_attempts",
    ):
        rows = connection.execute(
            f"""
            SELECT
                {table_name}.id,
                {table_name}.company_id,
                company_memberships.id AS membership_id,
                company_memberships.is_active AS membership_is_active
            FROM {table_name}
            LEFT JOIN company_memberships
                ON company_memberships.company_id = {table_name}.company_id
               AND company_memberships.user_id = {table_name}.user_id
            WHERE {table_name}.company_id != ?
              AND (
                  company_memberships.id IS NULL
                  OR company_memberships.is_active = 0
              )
            ORDER BY {table_name}.id ASC
            """,
            (LEGACY_COMPANY_ID,),
        ).fetchall()
        findings.extend(
            TenantAuditFinding(
                code="inactive_or_missing_membership",
                table_name=table_name,
                record_id=int(row["id"]),
                company_id=str(row["company_id"]),
                detail=(
                    "membership is inactive"
                    if row["membership_id"] is not None
                    else "membership is missing"
                ),
            )
            for row in rows
        )
    return findings


def format_report(report: TenantAuditReport) -> str:
    """Render a deterministic human-readable audit report."""
    lines = ["TENANT_AUDIT", f"findings={len(report.findings)}"]
    if report.is_clean:
        lines.append("status=clean")
        return "\n".join(lines)

    lines.append("status=review_required")
    for finding in report.findings:
        lines.append(
            "- "
            f"code={finding.code} "
            f"table={finding.table_name} "
            f"id={finding.record_id} "
            f"company_id={finding.company_id} "
            f"detail={finding.detail}"
        )
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only audit of multi-company learning data.",
    )
    parser.add_argument("--db", required=True, help="Path to the SQLite database.")
    return parser


def run(argv: Optional[list[str]] = None) -> int:
    """Run the audit CLI; return 1 when review is required."""
    args = _build_parser().parse_args(argv)
    db_path = Path(args.db)
    if not db_path.is_file():
        print("Error: database file does not exist.", file=sys.stderr)
        return 2

    try:
        report = audit_tenant_data(db_path)
    except sqlite3.Error as exc:
        print(f"Error: cannot audit database: {exc}", file=sys.stderr)
        return 2

    print(format_report(report))
    return 0 if report.is_clean else 1


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point."""
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
