"""Shared tenant fixtures for tests that persist learning attempts."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from app.database.db import get_connection


def seed_company_courses(
    db_path: Path,
    course_slugs: Iterable[str],
    *,
    company_id: str = "intertop",
) -> None:
    """Create the owning company and catalog courses required by DB guards."""
    normalized_slugs = tuple(dict.fromkeys(course_slugs))
    with get_connection(db_path) as connection:
        connection.execute(
            """
            INSERT INTO companies (id, name)
            VALUES (?, ?)
            ON CONFLICT(id) DO NOTHING
            """,
            (company_id, "Test Company"),
        )
        connection.executemany(
            """
            INSERT INTO courses (company_id, slug, title, status)
            VALUES (?, ?, ?, 'published')
            ON CONFLICT(company_id, slug) DO NOTHING
            """,
            (
                (company_id, slug, f"Test course: {slug}")
                for slug in normalized_slugs
            ),
        )
