import sqlite3
from typing import Dict


def _get_table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> Dict[str, sqlite3.Row]:
    rows = connection.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return {row["name"]: row for row in rows}


def _rebuild_users_with_optional_telegram_id(
    connection: sqlite3.Connection,
    columns: Dict[str, sqlite3.Row],
) -> None:
    """Rebuild legacy users while preserving canonical ids and foreign keys."""
    foreign_keys_enabled = bool(
        connection.execute("PRAGMA foreign_keys").fetchone()[0]
    )
    if connection.in_transaction:
        raise RuntimeError("users migration requires no active transaction")

    if foreign_keys_enabled:
        connection.execute("PRAGMA foreign_keys = OFF")

    def source(
        column_name: str,
        fallback_sql: str,
        *,
        coalesce: bool = False,
    ) -> str:
        if column_name not in columns:
            return fallback_sql
        if coalesce:
            return f"COALESCE({column_name}, {fallback_sql})"
        return column_name

    try:
        connection.execute("BEGIN")
        connection.execute(
            """
            CREATE TABLE users_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                role TEXT NOT NULL DEFAULT 'student',
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            f"""
            INSERT INTO users_new (
                id,
                telegram_id,
                username,
                first_name,
                last_name,
                role,
                is_active,
                created_at,
                updated_at
            )
            SELECT
                id,
                telegram_id,
                {source("username", "NULL")},
                {source("first_name", "NULL")},
                {source("last_name", "NULL")},
                {source("role", "'student'", coalesce=True)},
                {source("is_active", "1", coalesce=True)},
                {source("created_at", "CURRENT_TIMESTAMP", coalesce=True)},
                {source("updated_at", "CURRENT_TIMESTAMP", coalesce=True)}
            FROM users
            """
        )
        connection.execute("DROP TABLE users")
        connection.execute("ALTER TABLE users_new RENAME TO users")
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_users_telegram_id
            ON users(telegram_id)
            """
        )

        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(
                "users migration produced foreign key violations"
            )

        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        if foreign_keys_enabled:
            connection.execute("PRAGMA foreign_keys = ON")


def migrate_users_table(connection: sqlite3.Connection) -> None:
    """Make users channel-agnostic while preserving legacy Telegram users."""
    columns = _get_table_columns(connection, "users")
    telegram_id_column = columns.get("telegram_id")

    if telegram_id_column is not None and bool(telegram_id_column["notnull"]):
        _rebuild_users_with_optional_telegram_id(connection, columns)
        return

    if "role" not in columns:
        connection.execute(
            """
            ALTER TABLE users
            ADD COLUMN role TEXT NOT NULL DEFAULT 'student'
            """
        )

    if "is_active" not in columns:
        connection.execute(
            """
            ALTER TABLE users
            ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1
            """
        )

    if "updated_at" not in columns:
        connection.execute(
            """
            ALTER TABLE users
            ADD COLUMN updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            """
        )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_users_telegram_id
        ON users(telegram_id)
        """
    )


def migrate_enrollments_assignment_author(
    connection: sqlite3.Connection,
) -> None:
    """Track the canonical user who explicitly assigned a course."""
    columns = _get_table_columns(connection, "enrollments")

    if "assigned_by_user_id" not in columns:
        connection.execute(
            """
            ALTER TABLE enrollments
            ADD COLUMN assigned_by_user_id INTEGER
                REFERENCES users(id)
                ON DELETE SET NULL
            """
        )

    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_enrollments_assigned_by_user_id
        ON enrollments(assigned_by_user_id)
        """
    )


def migrate_lessons_table(connection: sqlite3.Connection) -> None:
    columns = _get_table_columns(connection, "lessons")

    if "slug" not in columns:
        connection.execute(
            """
            ALTER TABLE lessons
            ADD COLUMN slug TEXT
            """
        )

    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
        idx_lessons_course_id_slug
        ON lessons(course_id, slug)
        """
    )

def _repair_quiz_attempt_statistics(connection: sqlite3.Connection) -> None:
    """Recalculate stored scores from unique quiz answers for finished attempts."""
    connection.execute(
        """
        UPDATE quiz_attempts
        SET
            correct_answers = (
                SELECT CASE
                    WHEN quiz_attempts.questions_count <= 0 THEN 0
                    ELSE MIN(
                        quiz_attempts.questions_count,
                        COALESCE(SUM(quiz_answers.is_correct), 0)
                    )
                END
                FROM quiz_answers
                WHERE quiz_answers.attempt_id = quiz_attempts.id
            ),
            score_percent = (
                SELECT CASE
                    WHEN quiz_attempts.questions_count <= 0 THEN 0.0
                    ELSE MIN(
                        100.0,
                        ROUND(
                            MIN(
                                quiz_attempts.questions_count,
                                COALESCE(SUM(quiz_answers.is_correct), 0)
                            ) * 100.0 / quiz_attempts.questions_count,
                            2
                        )
                    )
                END
                FROM quiz_answers
                WHERE quiz_answers.attempt_id = quiz_attempts.id
            )
        WHERE finished_at IS NOT NULL
        """
    )


def migrate_quiz_answers_unique_question(connection: sqlite3.Connection) -> None:
    """Ensure at most one answer per question within a quiz attempt."""
    table_exists = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = 'quiz_answers'
        """
    ).fetchone()
    if table_exists is None:
        return

    index_exists = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'index'
          AND name = 'idx_quiz_answers_attempt_question'
        """
    ).fetchone()
    if index_exists is None:
        connection.execute(
            """
            DELETE FROM quiz_answers
            WHERE id NOT IN (
                SELECT MIN(id)
                FROM quiz_answers
                GROUP BY attempt_id, question_id
            )
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX idx_quiz_answers_attempt_question
            ON quiz_answers(attempt_id, question_id)
            """
        )

    _repair_quiz_attempt_statistics(connection)


def migrate_knowledge_documents_table(connection: sqlite3.Connection) -> None:
    """Ensure knowledge_documents table and indexes exist for legacy databases."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS knowledge_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            title TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_language TEXT NOT NULL DEFAULT 'auto',
            extracted_text TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (source_type IN ('pdf', 'docx', 'pptx')),
            CHECK (status IN ('draft', 'active', 'archived')),
            CHECK (version >= 1)
        );

        CREATE INDEX IF NOT EXISTS idx_knowledge_documents_company_id
            ON knowledge_documents(company_id);

        CREATE INDEX IF NOT EXISTS idx_knowledge_documents_company_status
            ON knowledge_documents(company_id, status);

        CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_documents_company_document
            ON knowledge_documents(company_id, document_id);
        """
    )



def migrate_knowledge_document_chunks_table(connection: sqlite3.Connection) -> None:
    """Ensure knowledge_document_chunks table and indexes exist for legacy databases."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS knowledge_document_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL,
            document_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            start_char INTEGER NOT NULL,
            end_char INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (chunk_index >= 0),
            CHECK (start_char >= 0),
            CHECK (end_char > start_char)
        );

        CREATE INDEX IF NOT EXISTS idx_knowledge_document_chunks_company_id
            ON knowledge_document_chunks(company_id);

        CREATE INDEX IF NOT EXISTS idx_knowledge_document_chunks_company_document
            ON knowledge_document_chunks(company_id, document_id);

        CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_document_chunks_company_document_index
            ON knowledge_document_chunks(company_id, document_id, chunk_index);
        """
    )


def migrate_user_password_credentials_table(
    connection: sqlite3.Connection,
) -> None:
    """Ensure password credentials storage exists for canonical users."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS user_password_credentials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            email TEXT NOT NULL COLLATE NOCASE UNIQUE,
            password_hash TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,
            CHECK (length(trim(email)) > 0),
            CHECK (length(trim(password_hash)) > 0),
            CHECK (is_active IN (0, 1))
        );

        CREATE INDEX IF NOT EXISTS idx_user_password_credentials_user_id
            ON user_password_credentials(user_id);

        CREATE UNIQUE INDEX IF NOT EXISTS idx_user_password_credentials_email
            ON user_password_credentials(email COLLATE NOCASE);
        """
    )


def migrate_companies_table(connection: sqlite3.Connection) -> None:
    """Ensure companies and company_memberships tables exist for legacy databases."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS companies (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS company_memberships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'student',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(company_id, user_id),
            FOREIGN KEY (company_id)
                REFERENCES companies(id)
                ON DELETE CASCADE,
            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,
            CHECK (role IN ('student', 'manager', 'admin')),
            CHECK (is_active IN (0, 1))
        );

        CREATE INDEX IF NOT EXISTS idx_company_memberships_company_id
            ON company_memberships(company_id);

        CREATE INDEX IF NOT EXISTS idx_company_memberships_user_id
            ON company_memberships(user_id);

        CREATE INDEX IF NOT EXISTS idx_company_memberships_company_role
            ON company_memberships(company_id, role);
        """
    )


def run_migrations(connection: sqlite3.Connection) -> None:
    migrate_users_table(connection)
    migrate_enrollments_assignment_author(connection)
    migrate_lessons_table(connection)
    migrate_quiz_answers_unique_question(connection)
    migrate_knowledge_documents_table(connection)
    migrate_knowledge_document_chunks_table(connection)
    migrate_user_password_credentials_table(connection)
    migrate_companies_table(connection)
