"""Interactively create the sole initial platform owner for a new deployment."""

from __future__ import annotations

import argparse
import getpass
import sqlite3
import sys
from pathlib import Path
from typing import Optional, Sequence

from app.database.db import get_connection, initialize_database
from app.web.password_hashing_service import PasswordHashingService


_MINIMUM_PASSWORD_LENGTH = 12


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    return parser


def _normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("email must not be empty")
    return normalized


def _validate_password(password: str, confirmation: str) -> str:
    if password != confirmation:
        raise ValueError("password confirmation does not match")
    if len(password) < _MINIMUM_PASSWORD_LENGTH:
        raise ValueError(
            f"password must contain at least {_MINIMUM_PASSWORD_LENGTH} characters"
        )
    return password


def create_initial_platform_owner(
    db_path: Path,
    *,
    email: str,
    password: str,
) -> int:
    """Atomically provision one credential-backed platform owner."""
    normalized_email = _normalize_email(email)
    password_hash = PasswordHashingService().hash_password(password)
    initialize_database(db_path)

    try:
        with get_connection(db_path) as connection:
            existing_admin = connection.execute(
                "SELECT user_id FROM platform_admins LIMIT 1"
            ).fetchone()
            if existing_admin is not None:
                raise RuntimeError("a platform administrator already exists")

            user_id = int(
                connection.execute(
                    "INSERT INTO users (username) VALUES ('platform-owner')"
                ).lastrowid
            )
            connection.execute(
                """
                INSERT INTO user_password_credentials (
                    user_id, email, password_hash
                )
                VALUES (?, ?, ?)
                """,
                (user_id, normalized_email, password_hash),
            )
            connection.execute(
                """
                INSERT INTO platform_admins (user_id, is_owner, is_active)
                VALUES (?, 1, 1)
                """,
                (user_id,),
            )
            connection.execute(
                """
                INSERT INTO platform_audit_events (
                    actor_user_id, action, target_type, target_id, reason
                )
                VALUES (?, 'platform_admin.bootstrap_owner', 'user', ?, 'setup_cli')
                """,
                (user_id, str(user_id)),
            )
    except sqlite3.IntegrityError as error:
        raise ValueError("email is already used") from error

    return user_id


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        email = input("Platform owner email: ")
        password = getpass.getpass("Platform owner password: ")
        confirmation = getpass.getpass("Confirm platform owner password: ")
        user_id = create_initial_platform_owner(
            args.db,
            email=email,
            password=_validate_password(password, confirmation),
        )
    except (EOFError, OSError, RuntimeError, ValueError) as error:
        print(f"Platform owner setup failed: {error}", file=sys.stderr)
        return 2

    print(f"Platform owner setup completed for user_id={user_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
