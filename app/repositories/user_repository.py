from pathlib import Path
from typing import Optional

from app.database.db import (
    get_user_by_id,
    get_user_by_telegram_id,
    upsert_telegram_user,
)


class UserRepository:
    """Отвечает за работу с данными пользователей."""

    def get_by_id(
        self,
        db_path: Path,
        user_id: int,
    ):
        return get_user_by_id(
            db_path=db_path,
            user_id=user_id,
        )

    def get_by_telegram_id(
        self,
        db_path: Path,
        telegram_id: int,
    ):
        return get_user_by_telegram_id(
            db_path=db_path,
            telegram_id=telegram_id,
        )

    def save_telegram_user(
        self,
        db_path: Path,
        telegram_id: int,
        username: Optional[str],
        first_name: Optional[str],
        last_name: Optional[str],
    ):
        return upsert_telegram_user(
            db_path=db_path,
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
        )
