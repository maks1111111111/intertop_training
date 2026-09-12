"""Read-only preflight audit for the platform-administration contour."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from app.database.db import get_connection


_REQUIRED_TABLES = (
    "platform_admins",
    "platform_audit_events",
    "platform_support_accesses",
    "company_usage_limits",
)
_REQUIRED_TRIGGERS = (
    "prevent_platform_audit_event_update",
    "prevent_platform_audit_event_delete",
    "prevent_course_company_reassignment",
    "enforce_company_member_limit_insert",
    "enforce_company_member_limit_update",
    "enforce_company_course_limit_insert",
    "enforce_company_course_limit_update",
)


@dataclass(frozen=True)
class PlatformAuditFinding:
    """One non-sensitive platform operation issue needing review."""

    code: str
    detail: str


@dataclass(frozen=True)
class PlatformAuditReport:
    """Read-only result for one platform preflight."""

    findings: tuple[PlatformAuditFinding, ...]

    @property
    def is_clean(self) -> bool:
        return not self.findings


def audit_platform_data(db_path: Path) -> PlatformAuditReport:
    """Check platform controls and configured quota consistency without writes."""
    with get_connection(db_path) as connection:
        findings = [
            *_find_sqlite_integrity_issues(connection),
            *_find_missing_schema_controls(connection),
            *_find_usable_owner_issues(connection),
            *_find_usage_limit_violations(connection),
        ]
    return PlatformAuditReport(findings=tuple(findings))


def _find_sqlite_integrity_issues(
    connection: sqlite3.Connection,
) -> list[PlatformAuditFinding]:
    findings: list[PlatformAuditFinding] = []
    integrity_rows = connection.execute("PRAGMA integrity_check").fetchall()
    if any(str(row[0]) != "ok" for row in integrity_rows):
        findings.append(
            PlatformAuditFinding(
                code="sqlite_integrity_check_failed",
                detail="PRAGMA integrity_check did not return ok",
            )
        )

    for row in connection.execute("PRAGMA foreign_key_check").fetchall():
        findings.append(
            PlatformAuditFinding(
                code="foreign_key_violation",
                detail=f"table={row[0]} rowid={row[1]} parent={row[2]}",
            )
        )
    return findings


def _find_missing_schema_controls(
    connection: sqlite3.Connection,
) -> list[PlatformAuditFinding]:
    objects = {
        (str(row["type"]), str(row["name"]))
        for row in connection.execute(
            "SELECT type, name FROM sqlite_master WHERE type IN ('table', 'trigger')"
        ).fetchall()
    }
    findings = [
        PlatformAuditFinding(
            code="missing_platform_table",
            detail=f"required table is absent: {name}",
        )
        for name in _REQUIRED_TABLES
        if ("table", name) not in objects
    ]
    findings.extend(
        PlatformAuditFinding(
            code="missing_platform_trigger",
            detail=f"required trigger is absent: {name}",
        )
        for name in _REQUIRED_TRIGGERS
        if ("trigger", name) not in objects
    )
    return findings


def _find_usable_owner_issues(
    connection: sqlite3.Connection,
) -> list[PlatformAuditFinding]:
    if not _table_exists(connection, "platform_admins"):
        return []

    row = connection.execute(
        """
        SELECT COUNT(*)
        FROM platform_admins
        JOIN users ON users.id = platform_admins.user_id
        WHERE platform_admins.is_owner = 1
          AND platform_admins.is_active = 1
          AND users.is_active = 1
        """
    ).fetchone()
    assert row is not None
    owner_count = int(row[0])
    if owner_count == 1:
        return []
    return [
        PlatformAuditFinding(
            code="invalid_usable_owner_count",
            detail=f"expected exactly one active platform owner, found {owner_count}",
        )
    ]


def _find_usage_limit_violations(
    connection: sqlite3.Connection,
) -> list[PlatformAuditFinding]:
    required = ("company_usage_limits", "company_memberships", "courses")
    if not all(_table_exists(connection, name) for name in required):
        return []

    rows = connection.execute(
        """
        SELECT
            limits.company_id,
            limits.max_active_members,
            limits.max_courses,
            (SELECT COUNT(*) FROM company_memberships
             WHERE company_id = limits.company_id AND is_active = 1) AS active_members,
            (SELECT COUNT(*) FROM courses
             WHERE company_id = limits.company_id) AS courses
        FROM company_usage_limits AS limits
        ORDER BY limits.company_id ASC
        """
    ).fetchall()
    findings: list[PlatformAuditFinding] = []
    for row in rows:
        company_id = str(row["company_id"])
        if (
            row["max_active_members"] is not None
            and int(row["active_members"]) > int(row["max_active_members"])
        ):
            findings.append(
                PlatformAuditFinding(
                    code="active_member_limit_exceeded",
                    detail=(
                        f"company_id={company_id} active_members={row['active_members']} "
                        f"max_active_members={row['max_active_members']}"
                    ),
                )
            )
        if row["max_courses"] is not None and int(row["courses"]) > int(
            row["max_courses"]
        ):
            findings.append(
                PlatformAuditFinding(
                    code="course_limit_exceeded",
                    detail=(
                        f"company_id={company_id} courses={row['courses']} "
                        f"max_courses={row['max_courses']}"
                    ),
                )
            )
    return findings


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        is not None
    )


def format_report(report: PlatformAuditReport) -> str:
    """Render a deterministic, non-sensitive operator report."""
    lines = ["PLATFORM_AUDIT", f"findings={len(report.findings)}"]
    if report.is_clean:
        lines.append("status=clean")
        return "\n".join(lines)

    lines.append("status=review_required")
    lines.extend(
        f"- code={finding.code} detail={finding.detail}"
        for finding in report.findings
    )
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only audit of platform administration controls.",
    )
    parser.add_argument("--db", required=True, help="Path to the SQLite database.")
    return parser


def run(argv: Optional[list[str]] = None) -> int:
    """Run the audit CLI; return 1 when operator review is required."""
    args = _build_parser().parse_args(argv)
    db_path = Path(args.db)
    if not db_path.is_file():
        print("Error: database file does not exist.", file=sys.stderr)
        return 2

    try:
        report = audit_platform_data(db_path)
    except sqlite3.Error as error:
        print(f"Error: cannot audit database: {error}", file=sys.stderr)
        return 2

    print(format_report(report))
    return 0 if report.is_clean else 1


def main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point."""
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
