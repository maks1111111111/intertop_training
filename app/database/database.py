"""Инициализация SQLite-базы данных проекта."""

import sqlite3
from pathlib import Path

# Имя каталога и файла базы относительно корня проекта.
DATA_DIR_NAME = "data"
DB_FILE_NAME = "training.db"


def _get_data_dir(base_dir: Path) -> Path:
    """Возвращает путь к каталогу data/."""
    return base_dir / DATA_DIR_NAME


def _get_db_path(base_dir: Path) -> Path:
    """Возвращает путь к файлу SQLite-базы."""
    return _get_data_dir(base_dir) / DB_FILE_NAME


def _ensure_data_dir(base_dir: Path) -> None:
    """Создаёт каталог data/, если он ещё не существует."""
    _get_data_dir(base_dir).mkdir(parents=True, exist_ok=True)


def init_db(base_dir: Path) -> None:
    """
    Подготавливает SQLite-базу при старте приложения.

    - создаёт каталог data/, если его нет;
    - создаёт файл data/training.db при первом подключении;
    - создаёт таблицу users, если она ещё не существует.
    """
    _ensure_data_dir(base_dir)
    db_path = _get_db_path(base_dir)

    # connect() автоматически создаёт файл базы, если он отсутствует.
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()
