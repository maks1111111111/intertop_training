"""Read-only eligibility check for a company's approved offboarding window."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional, Sequence

from app.database.db import get_connection


WORKING_DATA_GRACE_DAYS = 30


class CompanyOffboardingError(RuntimeError):
    """Raised when the offboarding state cannot be safely assessed."""


@dataclass(frozen=True)
class CompanyOffboardingStatus:
    """Read-only assessment of one company's controlled deletion eligibility."""

    company_id: str
    company_name: str
    is_active: bool
    deactivated_at: Optional[datetime]
    eligible_at: Optional[datetime]
    is_eligible: bool
    reason: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def assess_company_offboarding(
    db_path: Path,
    company_id: str,
    *,
    now: Callable[[], datetime] = _utc_now,
) -> CompanyOffboardingStatus:
    """Assess the 30-day grace period without modifying any data.

    Eligibility derives only from the immutable platform audit trail. A company
    which was enabled again is never eligible, even when an older deactivation
    event is more than 30 days old.
    """
    source = Path(db_path).resolve()
    normalized_company_id = _validate_company_id(company_id)
    current_time = _validate_time(now())
    if not source.is_file():
        raise FileNotFoundError(source)

    with get_connection(source) as connection:
        company = connection.execute(
            """
            SELECT id, name, is_active
            FROM companies
            WHERE id = ?
            """,
            (normalized_company_id,),
        ).fetchone()
        if company is None:
            raise CompanyOffboardingError(
                f"company does not exist: {normalized_company_id}"
            )
        lifecycle_event = connection.execute(
            """
            SELECT action, created_at
            FROM platform_audit_events
            WHERE target_type = 'company'
              AND target_id = ?
              AND action IN ('company.activated', 'company.deactivated')
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (normalized_company_id,),
        ).fetchone()

    if bool(company["is_active"]):
        return CompanyOffboardingStatus(
            company_id=normalized_company_id,
            company_name=str(company["name"]),
            is_active=True,
            deactivated_at=None,
            eligible_at=None,
            is_eligible=False,
            reason="company is active",
        )

    if lifecycle_event is None or lifecycle_event["action"] != "company.deactivated":
        return CompanyOffboardingStatus(
            company_id=normalized_company_id,
            company_name=str(company["name"]),
            is_active=False,
            deactivated_at=None,
            eligible_at=None,
            is_eligible=False,
            reason="no current audited deactivation event",
        )

    deactivated_at = _parse_audit_time(str(lifecycle_event["created_at"]))
    eligible_at = deactivated_at + timedelta(days=WORKING_DATA_GRACE_DAYS)
    return CompanyOffboardingStatus(
        company_id=normalized_company_id,
        company_name=str(company["name"]),
        is_active=False,
        deactivated_at=deactivated_at,
        eligible_at=eligible_at,
        is_eligible=current_time >= eligible_at,
        reason=(
            "working-data deletion window has opened"
            if current_time >= eligible_at
            else "working-data grace period is still active"
        ),
    )


def format_company_offboarding_status(status: CompanyOffboardingStatus) -> str:
    """Render a stable human-readable operator report."""
    lines = [
        "COMPANY_OFFBOARDING",
        f"company_id={status.company_id}",
        f"company_name={status.company_name}",
        f"company_state={'active' if status.is_active else 'inactive'}",
        "working_data_grace_days=" + str(WORKING_DATA_GRACE_DAYS),
        "deactivated_at=" + _format_time(status.deactivated_at),
        "eligible_at=" + _format_time(status.eligible_at),
        "eligible=" + str(status.is_eligible).lower(),
        f"reason={status.reason}",
        "status=read_only",
    ]
    return "\n".join(lines)


def _validate_company_id(company_id: str) -> str:
    if not isinstance(company_id, str):
        raise TypeError("company_id must be a string")
    normalized = company_id.strip().lower()
    if not normalized or normalized in {".", ".."}:
        raise ValueError("company_id must be non-empty")
    if "/" in normalized or "\\" in normalized:
        raise ValueError("company_id must be a single path component")
    return normalized


def _validate_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("clock must return a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _parse_audit_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CompanyOffboardingError("invalid platform audit timestamp") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_time(value: Optional[datetime]) -> str:
    return value.isoformat() if value is not None else ""


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path)
    parser.add_argument("--company-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the read-only offboarding eligibility check."""
    args = _build_parser().parse_args(argv)
    try:
        status = assess_company_offboarding(args.db, args.company_id)
    except (CompanyOffboardingError, OSError, sqlite3.Error, TypeError, ValueError) as error:
        print(f"offboarding check failed: {error}", file=sys.stderr)
        return 2
    print(format_company_offboarding_status(status))
    return 0 if status.is_eligible else 1


if __name__ == "__main__":
    raise SystemExit(main())
