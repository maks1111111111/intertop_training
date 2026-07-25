import sqlite3


def create_tables(connection: sqlite3.Connection) -> None:
    """Создаёт все таблицы и индексы приложения."""

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER NOT NULL UNIQUE,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            role TEXT NOT NULL DEFAULT 'student',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            cover_path TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            lesson_type TEXT NOT NULL DEFAULT 'content',
            content TEXT,
            media_path TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (course_id)
                REFERENCES courses(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS enrollments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            course_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'assigned',
            progress_percent INTEGER NOT NULL DEFAULT 0,
            assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at TEXT,
            completed_at TEXT,
            UNIQUE(user_id, course_id),
            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,
            FOREIGN KEY (course_id)
                REFERENCES courses(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS lesson_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            lesson_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'not_started',
            started_at TEXT,
            completed_at TEXT,
            UNIQUE(user_id, lesson_id),
            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,
            FOREIGN KEY (lesson_id)
                REFERENCES lessons(id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_users_telegram_id
            ON users(telegram_id);

        CREATE INDEX IF NOT EXISTS idx_lessons_course_id
            ON lessons(course_id);

        CREATE INDEX IF NOT EXISTS idx_enrollments_user_id
            ON enrollments(user_id);

        CREATE INDEX IF NOT EXISTS idx_lesson_progress_user_id
            ON lesson_progress(user_id);

        CREATE TABLE IF NOT EXISTS quiz_attempts (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            course_slug TEXT NOT NULL,
            quiz_version INTEGER NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            questions_count INTEGER NOT NULL,
            correct_answers INTEGER DEFAULT 0,
            score_percent REAL DEFAULT 0,
            passed INTEGER DEFAULT 0,
            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS quiz_answers (
            id INTEGER PRIMARY KEY,
            attempt_id INTEGER NOT NULL,
            question_id TEXT NOT NULL,
            selected_option_id TEXT NOT NULL,
            is_correct INTEGER NOT NULL,
            FOREIGN KEY (attempt_id)
                REFERENCES quiz_attempts(id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_quiz_attempts_user_id
            ON quiz_attempts(user_id);

        CREATE INDEX IF NOT EXISTS idx_quiz_attempts_course_slug
            ON quiz_attempts(course_slug);

        CREATE INDEX IF NOT EXISTS idx_quiz_answers_attempt_id
            ON quiz_answers(attempt_id);
        """
    )