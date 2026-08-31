import sqlite3


def create_tables(connection: sqlite3.Connection) -> None:
    """Создаёт все таблицы и индексы приложения."""

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE,
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
            assigned_by_user_id INTEGER,
            due_at TEXT,
            started_at TEXT,
            completed_at TEXT,
            UNIQUE(user_id, course_id),
            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,
            FOREIGN KEY (course_id)
                REFERENCES courses(id)
                ON DELETE CASCADE,
            FOREIGN KEY (assigned_by_user_id)
                REFERENCES users(id)
                ON DELETE SET NULL
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

        CREATE TABLE IF NOT EXISTS practical_task_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            course_slug TEXT NOT NULL,
            lesson_slug TEXT NOT NULL,
            task_title TEXT NOT NULL,
            task_description TEXT NOT NULL,
            expected_result TEXT NOT NULL,
            learner_answer TEXT NOT NULL,
            score INTEGER,
            max_score INTEGER,
            passed INTEGER,
            feedback_summary TEXT,
            feedback_strengths_json TEXT,
            feedback_improvements_json TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TEXT,
            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,
            CHECK (status IN ('pending', 'reviewed', 'failed')),
            CHECK (passed IS NULL OR passed IN (0, 1)),
            CHECK (score IS NULL OR score >= 0),
            CHECK (max_score IS NULL OR max_score >= 0)
        );

        CREATE INDEX IF NOT EXISTS idx_practical_task_attempts_user_id
            ON practical_task_attempts(user_id);

        CREATE INDEX IF NOT EXISTS idx_practical_task_attempts_course_lesson
            ON practical_task_attempts(course_slug, lesson_slug);

        CREATE INDEX IF NOT EXISTS idx_practical_task_attempts_status
            ON practical_task_attempts(status);

        CREATE TABLE IF NOT EXISTS web_lesson_progress (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            course_slug TEXT NOT NULL,
            lesson_id TEXT NOT NULL,
            completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, course_slug, lesson_id)
        );

        CREATE INDEX IF NOT EXISTS idx_web_lesson_progress_user_course
            ON web_lesson_progress(user_id, course_slug);

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
