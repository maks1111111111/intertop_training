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


def _has_unique_index(
    connection: sqlite3.Connection,
    table_name: str,
    expected_columns: tuple[str, ...],
) -> bool:
    """Return whether a table has a unique index with these exact columns."""
    for index in connection.execute(f"PRAGMA index_list({table_name})"):
        if not bool(index["unique"]):
            continue
        index_name = str(index["name"]).replace("'", "''")
        columns = tuple(
            str(column["name"])
            for column in connection.execute(
                f"PRAGMA index_info('{index_name}')"
            )
        )
        if columns == expected_columns:
            return True
    return False


def _rebuild_users_with_optional_telegram_id(
    connection: sqlite3.Connection,
    columns: Dict[str, sqlite3.Row],
) -> None:
    """Rebuild legacy users while preserving canonical ids and foreign keys."""
    foreign_keys_enabled = bool(
        connection.execute("PRAGMA foreign_keys").fetchone()[0]
    )
    legacy_alter_table_enabled = bool(
        connection.execute("PRAGMA legacy_alter_table").fetchone()[0]
    )
    if connection.in_transaction:
        raise RuntimeError("users migration requires no active transaction")

    if foreign_keys_enabled:
        connection.execute("PRAGMA foreign_keys = OFF")
    if not legacy_alter_table_enabled:
        # ``create_tables`` may have already installed tenant triggers on
        # tables which are still legacy-shaped.  Newer SQLite validates every
        # trigger while renaming ``users_new`` and rejects those unrelated,
        # temporarily invalid triggers.  Their SQL does not refer to users,
        # so retain the pre-3.25 rename behaviour for this one internal swap.
        connection.execute("PRAGMA legacy_alter_table = ON")

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
        if not legacy_alter_table_enabled:
            connection.execute("PRAGMA legacy_alter_table = OFF")
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


def migrate_enrollments_due_at(connection: sqlite3.Connection) -> None:
    """Add optional due date for explicit course assignments."""
    columns = _get_table_columns(connection, "enrollments")

    if "due_at" not in columns:
        connection.execute(
            """
            ALTER TABLE enrollments
            ADD COLUMN due_at TEXT
            """
        )


def migrate_enrollments_development_context(
    connection: sqlite3.Connection,
) -> None:
    """Add optional development-zone context for explicit course assignments."""
    columns = _get_table_columns(connection, "enrollments")

    if "development_source" not in columns:
        connection.execute(
            """
            ALTER TABLE enrollments
            ADD COLUMN development_source TEXT
            """
        )

    if "development_reason" not in columns:
        connection.execute(
            """
            ALTER TABLE enrollments
            ADD COLUMN development_reason TEXT
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


def migrate_platform_admins_table(connection: sqlite3.Connection) -> None:
    """Add global platform administration records to existing databases.

    Platform privileges intentionally live outside ``company_memberships`` so
    that they cannot be inherited from a tenant role or tenant session.
    """
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS platform_admins (
            user_id INTEGER PRIMARY KEY,
            is_owner INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,
            CHECK (is_owner IN (0, 1)),
            CHECK (is_active IN (0, 1))
        );

        CREATE UNIQUE INDEX IF NOT EXISTS idx_platform_admins_single_active_owner
            ON platform_admins(is_owner)
            WHERE is_owner = 1 AND is_active = 1;

        CREATE TABLE IF NOT EXISTS platform_audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor_user_id INTEGER,
            action TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK (length(trim(action)) > 0),
            CHECK (length(trim(target_type)) > 0),
            CHECK (length(trim(target_id)) > 0)
        );

        CREATE INDEX IF NOT EXISTS idx_platform_audit_events_created_at
            ON platform_audit_events(created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_platform_audit_events_target
            ON platform_audit_events(target_type, target_id);

        CREATE TRIGGER IF NOT EXISTS prevent_platform_audit_event_update
        BEFORE UPDATE ON platform_audit_events
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'platform audit events are immutable');
        END;

        CREATE TRIGGER IF NOT EXISTS prevent_platform_audit_event_delete
        BEFORE DELETE ON platform_audit_events
        FOR EACH ROW
        BEGIN
            SELECT RAISE(ABORT, 'platform audit events are immutable');
        END;
        """
    )


def migrate_platform_support_accesses_table(
    connection: sqlite3.Connection,
) -> None:
    """Add time-bound company support grants for global administrators."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS platform_support_accesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operator_user_id INTEGER NOT NULL,
            company_id TEXT NOT NULL,
            reason TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            revoked_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (operator_user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,
            FOREIGN KEY (company_id)
                REFERENCES companies(id)
                ON DELETE CASCADE,
            CHECK (length(trim(reason)) > 0)
        );

        CREATE INDEX IF NOT EXISTS idx_platform_support_accesses_operator
            ON platform_support_accesses(operator_user_id, expires_at);

        CREATE INDEX IF NOT EXISTS idx_platform_support_accesses_company
            ON platform_support_accesses(company_id, expires_at);
        """
    )


def migrate_company_usage_limits_table(connection: sqlite3.Connection) -> None:
    """Add enforced company member and course limits to existing databases."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS company_usage_limits (
            company_id TEXT PRIMARY KEY,
            max_active_members INTEGER,
            max_courses INTEGER,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
            CHECK (max_active_members IS NULL OR max_active_members > 0),
            CHECK (max_courses IS NULL OR max_courses > 0)
        );
        CREATE TRIGGER IF NOT EXISTS enforce_company_member_limit_insert
        BEFORE INSERT ON company_memberships
        FOR EACH ROW WHEN NEW.is_active = 1 AND EXISTS (
            SELECT 1 FROM company_usage_limits
            WHERE company_id = NEW.company_id
              AND max_active_members IS NOT NULL
              AND (SELECT COUNT(*) FROM company_memberships
                   WHERE company_id = NEW.company_id AND is_active = 1) >= max_active_members
        )
        BEGIN SELECT RAISE(ABORT, 'company active member limit reached'); END;

        CREATE TRIGGER IF NOT EXISTS enforce_company_member_limit_update
        BEFORE UPDATE OF company_id, is_active ON company_memberships
        FOR EACH ROW
        WHEN NEW.is_active = 1
         AND (OLD.is_active != 1 OR OLD.company_id != NEW.company_id)
         AND EXISTS (
            SELECT 1 FROM company_usage_limits
            WHERE company_id = NEW.company_id
              AND max_active_members IS NOT NULL
              AND (SELECT COUNT(*) FROM company_memberships
                   WHERE company_id = NEW.company_id
                     AND is_active = 1
                     AND id != OLD.id) >= max_active_members
        )
        BEGIN SELECT RAISE(ABORT, 'company active member limit reached'); END;

        CREATE TRIGGER IF NOT EXISTS enforce_company_course_limit_insert
        BEFORE INSERT ON courses
        FOR EACH ROW WHEN EXISTS (
            SELECT 1 FROM company_usage_limits
            WHERE company_id = NEW.company_id
              AND max_courses IS NOT NULL
              AND (SELECT COUNT(*) FROM courses WHERE company_id = NEW.company_id) >= max_courses
        )
        BEGIN SELECT RAISE(ABORT, 'company course limit reached'); END;

        CREATE TRIGGER IF NOT EXISTS enforce_company_course_limit_update
        BEFORE UPDATE OF company_id ON courses
        FOR EACH ROW
        WHEN NEW.company_id != OLD.company_id
         AND EXISTS (
            SELECT 1 FROM company_usage_limits
            WHERE company_id = NEW.company_id
              AND max_courses IS NOT NULL
              AND (SELECT COUNT(*) FROM courses
                   WHERE company_id = NEW.company_id
                     AND id != OLD.id) >= max_courses
        )
        BEGIN SELECT RAISE(ABORT, 'company course limit reached'); END;
        """
    )
def migrate_learning_progress_tenant_scope(
    connection: sqlite3.Connection,
) -> None:
    """Scope legacy learning records to Intertop and add tenant indexes.

    Enrollments and lesson progress must be rebuilt because their legacy
    uniqueness constraints did not include a company.  Other attempt tables
    can safely receive a non-null legacy tenant column in place.
    """
    enrollment_columns = _get_table_columns(connection, "enrollments")
    progress_columns = _get_table_columns(connection, "lesson_progress")

    if "company_id" not in enrollment_columns or "company_id" not in progress_columns:
        # A populated legacy installation needs an owning tenant before its
        # globally-addressed learning records are rebuilt. New installations
        # create their first company explicitly during onboarding instead.
        legacy_users = connection.execute(
            "SELECT 1 FROM users LIMIT 1"
        ).fetchone()
        if legacy_users is not None:
            connection.execute(
                """INSERT INTO companies (id, name) VALUES ('intertop', 'Intertop')
                   ON CONFLICT(id) DO NOTHING"""
            )
        foreign_keys_enabled = bool(
            connection.execute("PRAGMA foreign_keys").fetchone()[0]
        )
        # Earlier additive migrations may have created the legacy tenant in
        # this connection.  Publish that prerequisite before the SQLite table
        # rebuild, which must toggle foreign-key enforcement outside a txn.
        if connection.in_transaction:
            connection.commit()
        if foreign_keys_enabled:
            connection.execute("PRAGMA foreign_keys = OFF")
        try:
            connection.execute("BEGIN")
            if "company_id" not in enrollment_columns:
                connection.executescript(
                    """
                    CREATE TABLE enrollments_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        company_id TEXT NOT NULL DEFAULT 'intertop',
                        user_id INTEGER NOT NULL,
                        course_id INTEGER NOT NULL,
                        status TEXT NOT NULL DEFAULT 'assigned',
                        progress_percent INTEGER NOT NULL DEFAULT 0,
                        assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        assigned_by_user_id INTEGER,
                        due_at TEXT,
                        development_source TEXT,
                        development_reason TEXT,
                        started_at TEXT,
                        completed_at TEXT,
                        UNIQUE(company_id, user_id, course_id),
                        FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                        FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
                        FOREIGN KEY (assigned_by_user_id) REFERENCES users(id) ON DELETE SET NULL
                    );
                    """
                )
                connection.execute(
                    """
                    INSERT INTO enrollments_new (
                        id, company_id, user_id, course_id, status,
                        progress_percent, assigned_at, assigned_by_user_id,
                        due_at, development_source, development_reason,
                        started_at, completed_at
                    )
                    SELECT id, 'intertop', user_id, course_id, status,
                           progress_percent, assigned_at, assigned_by_user_id,
                           due_at, development_source, development_reason,
                           started_at, completed_at
                    FROM enrollments
                    """
                )
                connection.execute("DROP TABLE enrollments")
                connection.execute("ALTER TABLE enrollments_new RENAME TO enrollments")

            if "company_id" not in progress_columns:
                connection.executescript(
                    """
                    CREATE TABLE lesson_progress_new (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        company_id TEXT NOT NULL DEFAULT 'intertop',
                        user_id INTEGER NOT NULL,
                        lesson_id INTEGER NOT NULL,
                        status TEXT NOT NULL DEFAULT 'not_started',
                        started_at TEXT,
                        completed_at TEXT,
                        UNIQUE(company_id, user_id, lesson_id),
                        FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
                        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                        FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE CASCADE
                    );
                    """
                )
                connection.execute(
                    """
                    INSERT INTO lesson_progress_new (
                        id, company_id, user_id, lesson_id, status,
                        started_at, completed_at
                    )
                    SELECT id, 'intertop', user_id, lesson_id, status,
                           started_at, completed_at
                    FROM lesson_progress
                    """
                )
                connection.execute("DROP TABLE lesson_progress")
                connection.execute("ALTER TABLE lesson_progress_new RENAME TO lesson_progress")

            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            if foreign_keys_enabled:
                connection.execute("PRAGMA foreign_keys = ON")

    for table_name in (
        "quiz_attempts",
        "practical_task_attempts",
        "web_lesson_progress",
    ):
        if "company_id" not in _get_table_columns(connection, table_name):
            connection.execute(
                f"ALTER TABLE {table_name} ADD COLUMN company_id TEXT NOT NULL DEFAULT 'intertop'"
            )

    migrate_web_lesson_progress_tenant_scope(connection)

    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_enrollments_company_user
            ON enrollments(company_id, user_id);
        CREATE INDEX IF NOT EXISTS idx_lesson_progress_company_user
            ON lesson_progress(company_id, user_id);
        CREATE INDEX IF NOT EXISTS idx_quiz_attempts_company_user_course
            ON quiz_attempts(company_id, user_id, course_slug);
        CREATE INDEX IF NOT EXISTS idx_practical_task_attempts_company_user
            ON practical_task_attempts(company_id, user_id);
        CREATE INDEX IF NOT EXISTS idx_web_lesson_progress_company_user_course
            ON web_lesson_progress(company_id, user_id, course_slug);
        """
    )


def migrate_web_lesson_progress_tenant_scope(
    connection: sqlite3.Connection,
) -> None:
    """Include the company in the legacy Web progress uniqueness boundary."""
    if "company_id" not in _get_table_columns(
        connection,
        "web_lesson_progress",
    ):
        connection.execute(
            "ALTER TABLE web_lesson_progress "
            "ADD COLUMN company_id TEXT NOT NULL DEFAULT 'intertop'"
        )

    expected_columns = (
        "company_id",
        "user_id",
        "course_slug",
        "lesson_id",
    )
    if _has_unique_index(
        connection,
        "web_lesson_progress",
        expected_columns,
    ):
        return

    connection.executescript(
        """
        CREATE TABLE web_lesson_progress_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL DEFAULT 'intertop',
            user_id TEXT NOT NULL,
            course_slug TEXT NOT NULL,
            lesson_id TEXT NOT NULL,
            completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(company_id, user_id, course_slug, lesson_id)
        );

        INSERT INTO web_lesson_progress_new (
            id,
            company_id,
            user_id,
            course_slug,
            lesson_id,
            completed_at
        )
        SELECT
            id,
            company_id,
            user_id,
            course_slug,
            lesson_id,
            completed_at
        FROM web_lesson_progress;

        DROP TABLE web_lesson_progress;
        ALTER TABLE web_lesson_progress_new RENAME TO web_lesson_progress;
        """
    )


def migrate_courses_tenant_scope(connection: sqlite3.Connection) -> None:
    """Give legacy courses an explicit owner without changing their ids."""
    columns = _get_table_columns(connection, "courses")
    if "company_id" in columns:
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_courses_company_id ON courses(company_id)"
        )
        return

    if connection.execute("SELECT 1 FROM courses LIMIT 1").fetchone() is not None:
        connection.execute(
            """INSERT INTO companies (id, name) VALUES ('intertop', 'Intertop')
               ON CONFLICT(id) DO NOTHING"""
        )
    foreign_keys_enabled = bool(
        connection.execute("PRAGMA foreign_keys").fetchone()[0]
    )
    if connection.in_transaction:
        connection.commit()
    if foreign_keys_enabled:
        connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.execute("BEGIN")
        connection.executescript(
            """
            CREATE TABLE courses_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id TEXT NOT NULL DEFAULT 'intertop',
                slug TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                cover_path TEXT,
                sort_order INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(company_id, slug)
            );
            """
        )
        def source(column_name: str, fallback_sql: str) -> str:
            return column_name if column_name in columns else fallback_sql

        connection.execute(
            f"""
            INSERT INTO courses_new (
                id, company_id, slug, title, description, cover_path,
                sort_order, status, created_at, updated_at
            )
            SELECT id, 'intertop', slug, title,
                   {source('description', "''")}, {source('cover_path', 'NULL')},
                   {source('sort_order', '0')}, {source('status', "'draft'")},
                   {source('created_at', 'CURRENT_TIMESTAMP')},
                   {source('updated_at', 'CURRENT_TIMESTAMP')}
            FROM courses
            """
        )
        connection.execute("DROP TABLE courses")
        connection.execute("ALTER TABLE courses_new RENAME TO courses")
        connection.execute(
            "CREATE INDEX idx_courses_company_id ON courses(company_id)"
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        if foreign_keys_enabled:
            connection.execute("PRAGMA foreign_keys = ON")


def migrate_learning_tenant_integrity(connection: sqlite3.Connection) -> None:
    """Enforce that learning records belong to the owning course tenant."""
    connection.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS prevent_course_company_reassignment
        BEFORE UPDATE OF company_id ON courses
        FOR EACH ROW WHEN NEW.company_id != OLD.company_id
        BEGIN
            SELECT RAISE(ABORT, 'course company ownership is immutable');
        END;

        CREATE TRIGGER IF NOT EXISTS enforce_enrollment_course_company_insert
        BEFORE INSERT ON enrollments
        FOR EACH ROW
        WHEN NOT EXISTS (
            SELECT 1
            FROM courses
            WHERE courses.id = NEW.course_id
              AND courses.company_id = NEW.company_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'enrollment course belongs to another company');
        END;

        CREATE TRIGGER IF NOT EXISTS enforce_enrollment_course_company_update
        BEFORE UPDATE OF company_id, course_id ON enrollments
        FOR EACH ROW
        WHEN NOT EXISTS (
            SELECT 1
            FROM courses
            WHERE courses.id = NEW.course_id
              AND courses.company_id = NEW.company_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'enrollment course belongs to another company');
        END;

        CREATE TRIGGER IF NOT EXISTS enforce_lesson_progress_course_company_insert
        BEFORE INSERT ON lesson_progress
        FOR EACH ROW
        WHEN NOT EXISTS (
            SELECT 1
            FROM lessons
            JOIN courses ON courses.id = lessons.course_id
            WHERE lessons.id = NEW.lesson_id
              AND courses.company_id = NEW.company_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'lesson belongs to another company');
        END;

        CREATE TRIGGER IF NOT EXISTS enforce_lesson_progress_course_company_update
        BEFORE UPDATE OF company_id, lesson_id ON lesson_progress
        FOR EACH ROW
        WHEN NOT EXISTS (
            SELECT 1
            FROM lessons
            JOIN courses ON courses.id = lessons.course_id
            WHERE lessons.id = NEW.lesson_id
              AND courses.company_id = NEW.company_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'lesson belongs to another company');
        END;

        CREATE TRIGGER IF NOT EXISTS enforce_quiz_attempt_course_company_insert
        BEFORE INSERT ON quiz_attempts
        FOR EACH ROW
        WHEN NEW.company_id != 'intertop'
         AND NOT EXISTS (
            SELECT 1
            FROM courses
            WHERE courses.company_id = NEW.company_id
              AND courses.slug = NEW.course_slug
        )
        BEGIN
            SELECT RAISE(ABORT, 'quiz course belongs to another company');
        END;

        CREATE TRIGGER IF NOT EXISTS enforce_quiz_attempt_course_company_update
        BEFORE UPDATE OF company_id, course_slug ON quiz_attempts
        FOR EACH ROW
        WHEN NEW.company_id != 'intertop'
         AND NOT EXISTS (
            SELECT 1
            FROM courses
            WHERE courses.company_id = NEW.company_id
              AND courses.slug = NEW.course_slug
        )
        BEGIN
            SELECT RAISE(ABORT, 'quiz course belongs to another company');
        END;

        CREATE TRIGGER IF NOT EXISTS enforce_practical_attempt_course_company_insert
        BEFORE INSERT ON practical_task_attempts
        FOR EACH ROW
        WHEN NEW.company_id != 'intertop'
         AND NOT EXISTS (
            SELECT 1
            FROM courses
            WHERE courses.company_id = NEW.company_id
              AND courses.slug = NEW.course_slug
        )
        BEGIN
            SELECT RAISE(ABORT, 'practical-task course belongs to another company');
        END;

        CREATE TRIGGER IF NOT EXISTS enforce_practical_attempt_course_company_update
        BEFORE UPDATE OF company_id, course_slug ON practical_task_attempts
        FOR EACH ROW
        WHEN NEW.company_id != 'intertop'
         AND NOT EXISTS (
            SELECT 1
            FROM courses
            WHERE courses.company_id = NEW.company_id
              AND courses.slug = NEW.course_slug
        )
        BEGIN
            SELECT RAISE(ABORT, 'practical-task course belongs to another company');
        END;
        """
    )


def migrate_knowledge_tenant_integrity(connection: sqlite3.Connection) -> None:
    """Enforce that Knowledge Base chunks belong to their tenant document."""
    connection.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS enforce_knowledge_chunk_document_company_insert
        BEFORE INSERT ON knowledge_document_chunks
        FOR EACH ROW
        WHEN NOT EXISTS (
            SELECT 1
            FROM knowledge_documents
            WHERE knowledge_documents.company_id = NEW.company_id
              AND knowledge_documents.document_id = NEW.document_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'knowledge chunk document belongs to another company');
        END;

        CREATE TRIGGER IF NOT EXISTS enforce_knowledge_chunk_document_company_update
        BEFORE UPDATE OF company_id, document_id ON knowledge_document_chunks
        FOR EACH ROW
        WHEN NOT EXISTS (
            SELECT 1
            FROM knowledge_documents
            WHERE knowledge_documents.company_id = NEW.company_id
              AND knowledge_documents.document_id = NEW.document_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'knowledge chunk document belongs to another company');
        END;

        CREATE TRIGGER IF NOT EXISTS prevent_knowledge_document_identity_update_with_chunks
        BEFORE UPDATE OF company_id, document_id ON knowledge_documents
        FOR EACH ROW
        WHEN EXISTS (
            SELECT 1
            FROM knowledge_document_chunks
            WHERE knowledge_document_chunks.company_id = OLD.company_id
              AND knowledge_document_chunks.document_id = OLD.document_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'knowledge document has chunks');
        END;

        CREATE TRIGGER IF NOT EXISTS prevent_knowledge_document_delete_with_chunks
        BEFORE DELETE ON knowledge_documents
        FOR EACH ROW
        WHEN EXISTS (
            SELECT 1
            FROM knowledge_document_chunks
            WHERE knowledge_document_chunks.company_id = OLD.company_id
              AND knowledge_document_chunks.document_id = OLD.document_id
        )
        BEGIN
            SELECT RAISE(ABORT, 'knowledge document has chunks');
        END;
        """
    )


def run_migrations(connection: sqlite3.Connection) -> None:
    migrate_users_table(connection)
    migrate_enrollments_assignment_author(connection)
    migrate_enrollments_due_at(connection)
    migrate_enrollments_development_context(connection)
    migrate_lessons_table(connection)
    migrate_quiz_answers_unique_question(connection)
    migrate_knowledge_documents_table(connection)
    migrate_knowledge_document_chunks_table(connection)
    migrate_user_password_credentials_table(connection)
    migrate_companies_table(connection)
    migrate_platform_admins_table(connection)
    migrate_platform_support_accesses_table(connection)
    migrate_courses_tenant_scope(connection)
    # Course-table migration can rebuild ``courses`` and therefore drops
    # triggers attached to its legacy table. Install usage-limit triggers only
    # after that migration so old installations receive the same enforcement.
    migrate_company_usage_limits_table(connection)
    migrate_learning_progress_tenant_scope(connection)
    migrate_learning_tenant_integrity(connection)
    migrate_knowledge_tenant_integrity(connection)
