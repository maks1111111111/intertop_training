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
            FOREIGN KEY (company_id)
                REFERENCES companies(id)
                ON DELETE CASCADE,
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
            company_id TEXT NOT NULL DEFAULT 'intertop',
            user_id INTEGER NOT NULL,
            lesson_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'not_started',
            started_at TEXT,
            completed_at TEXT,
            UNIQUE(company_id, user_id, lesson_id),
            FOREIGN KEY (company_id)
                REFERENCES companies(id)
                ON DELETE CASCADE,
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
            company_id TEXT NOT NULL DEFAULT 'intertop',
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
            company_id TEXT NOT NULL DEFAULT 'intertop',
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
            company_id TEXT NOT NULL DEFAULT 'intertop',
            user_id TEXT NOT NULL,
            course_slug TEXT NOT NULL,
            lesson_id TEXT NOT NULL,
            completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(company_id, user_id, course_slug, lesson_id)
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

        CREATE TABLE IF NOT EXISTS user_mfa_credentials (
            user_id INTEGER PRIMARY KEY,
            encrypted_secret TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 0,
            last_used_counter INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE,
            CHECK (length(trim(encrypted_secret)) > 0),
            CHECK (is_active IN (0, 1)),
            CHECK (last_used_counter IS NULL OR last_used_counter >= 0)
        );

        CREATE TABLE IF NOT EXISTS companies (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS company_departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_id TEXT NOT NULL,
            name TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(company_id, name),
            FOREIGN KEY (company_id)
                REFERENCES companies(id)
                ON DELETE CASCADE,
            CHECK (length(trim(name)) > 0),
            CHECK (is_active IN (0, 1))
        );

        CREATE INDEX IF NOT EXISTS idx_company_departments_company_id
            ON company_departments(company_id, is_active, name);

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

        CREATE TABLE IF NOT EXISTS company_member_organizations (
            company_id TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            department_id INTEGER,
            manager_user_id INTEGER,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (company_id, user_id),
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (department_id) REFERENCES company_departments(id) ON DELETE SET NULL,
            FOREIGN KEY (manager_user_id) REFERENCES users(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_company_member_organizations_department
            ON company_member_organizations(company_id, department_id);

        CREATE INDEX IF NOT EXISTS idx_company_member_organizations_manager
            ON company_member_organizations(company_id, manager_user_id);

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
        WHEN NOT EXISTS (
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
        WHEN NOT EXISTS (
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
        WHEN NOT EXISTS (
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
        WHEN NOT EXISTS (
            SELECT 1
            FROM courses
            WHERE courses.company_id = NEW.company_id
              AND courses.slug = NEW.course_slug
        )
        BEGIN
            SELECT RAISE(ABORT, 'practical-task course belongs to another company');
        END;

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
