"""Provision new password-authenticated users inside one active company."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.database.db import get_connection
from app.web.password_hashing_service import PasswordHashingService


_ROLES = frozenset({"student", "manager", "admin"})
_MINIMUM_PASSWORD_LENGTH = 12


@dataclass(frozen=True)
class ProvisionedCompanyUser:
    user_id: int
    company_id: str
    email: str
    role: str


class CompanyUserProvisioningError(ValueError):
    """Raised when a tenant user cannot be provisioned safely."""


class CompanyUserProvisioningService:
    """Create a new canonical user, credential and tenant membership atomically."""

    def provision(
        self,
        db_path: Path,
        *,
        company_id: str,
        first_name: str,
        last_name: str,
        email: str,
        password: str,
        role: str,
    ) -> ProvisionedCompanyUser:
        normalized_company_id = _required(company_id, "company_id")
        normalized_first_name = _required(first_name, "first_name")
        normalized_last_name = last_name.strip()
        normalized_email = _required(email, "email").lower()
        normalized_role = _required(role, "role").lower()
        if normalized_role not in _ROLES:
            raise CompanyUserProvisioningError("Недопустимая роль пользователя.")
        if len(password) < _MINIMUM_PASSWORD_LENGTH:
            raise CompanyUserProvisioningError(
                "Пароль должен содержать не менее 12 символов."
            )
        password_hash = PasswordHashingService().hash_password(password)

        try:
            with get_connection(db_path) as connection:
                company = connection.execute(
                    "SELECT id FROM companies WHERE id = ? AND is_active = 1",
                    (normalized_company_id,),
                ).fetchone()
                if company is None:
                    raise CompanyUserProvisioningError("Компания недоступна.")
                user_id = int(
                    connection.execute(
                        """
                        INSERT INTO users (username, first_name, last_name)
                        VALUES (?, ?, ?)
                        """,
                        (normalized_email, normalized_first_name, normalized_last_name or None),
                    ).lastrowid
                )
                connection.execute(
                    """
                    INSERT INTO user_password_credentials (user_id, email, password_hash)
                    VALUES (?, ?, ?)
                    """,
                    (user_id, normalized_email, password_hash),
                )
                connection.execute(
                    """
                    INSERT INTO company_memberships (company_id, user_id, role)
                    VALUES (?, ?, ?)
                    """,
                    (normalized_company_id, user_id, normalized_role),
                )
        except sqlite3.IntegrityError as error:
            raise CompanyUserProvisioningError(
                "Пользователь с таким email уже существует."
            ) from error

        return ProvisionedCompanyUser(
            user_id=user_id,
            company_id=normalized_company_id,
            email=normalized_email,
            role=normalized_role,
        )


def _required(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise CompanyUserProvisioningError(f"{field_name} must be a string")
    normalized = value.strip()
    if not normalized:
        raise CompanyUserProvisioningError("Заполните обязательные поля пользователя.")
    return normalized
