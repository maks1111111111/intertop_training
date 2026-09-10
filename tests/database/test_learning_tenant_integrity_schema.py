"""Database constraints that preserve learning-data tenant ownership."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.database.db import get_connection, initialize_database


class LearningTenantIntegritySchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self._tmpdir.name) / "training.db"
        initialize_database(self.db_path)

        with get_connection(self.db_path) as connection:
            connection.executemany(
                "INSERT INTO companies (id, name) VALUES (?, ?)",
                (("company-a", "Company A"), ("company-b", "Company B")),
            )
            self.user_id = int(
                connection.execute(
                    "INSERT INTO users (username) VALUES ('learner')"
                ).lastrowid
            )
            self.course_a_id = int(
                connection.execute(
                    """
                    INSERT INTO courses (company_id, slug, title)
                    VALUES ('company-a', 'course-a', 'Course A')
                    """
                ).lastrowid
            )
            self.course_b_id = int(
                connection.execute(
                    """
                    INSERT INTO courses (company_id, slug, title)
                    VALUES ('company-b', 'course-b', 'Course B')
                    """
                ).lastrowid
            )
            self.lesson_a_id = int(
                connection.execute(
                    "INSERT INTO lessons (course_id, title) VALUES (?, 'Lesson A')",
                    (self.course_a_id,),
                ).lastrowid
            )
            self.lesson_b_id = int(
                connection.execute(
                    "INSERT INTO lessons (course_id, title) VALUES (?, 'Lesson B')",
                    (self.course_b_id,),
                ).lastrowid
            )

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_enrollment_must_belong_to_its_company_course(self) -> None:
        with get_connection(self.db_path) as connection:
            with self.assertRaisesRegex(
                sqlite3.IntegrityError,
                "enrollment course belongs to another company",
            ):
                connection.execute(
                    """
                    INSERT INTO enrollments (company_id, user_id, course_id)
                    VALUES ('company-a', ?, ?)
                    """,
                    (self.user_id, self.course_b_id),
                )

            enrollment_id = int(
                connection.execute(
                    """
                    INSERT INTO enrollments (company_id, user_id, course_id)
                    VALUES ('company-a', ?, ?)
                    """,
                    (self.user_id, self.course_a_id),
                ).lastrowid
            )

            with self.assertRaisesRegex(
                sqlite3.IntegrityError,
                "enrollment course belongs to another company",
            ):
                connection.execute(
                    "UPDATE enrollments SET company_id = 'company-b' WHERE id = ?",
                    (enrollment_id,),
                )

    def test_lesson_progress_must_belong_to_its_company_course(self) -> None:
        with get_connection(self.db_path) as connection:
            with self.assertRaisesRegex(
                sqlite3.IntegrityError,
                "lesson belongs to another company",
            ):
                connection.execute(
                    """
                    INSERT INTO lesson_progress (company_id, user_id, lesson_id)
                    VALUES ('company-a', ?, ?)
                    """,
                    (self.user_id, self.lesson_b_id),
                )

            progress_id = int(
                connection.execute(
                    """
                    INSERT INTO lesson_progress (company_id, user_id, lesson_id)
                    VALUES ('company-a', ?, ?)
                    """,
                    (self.user_id, self.lesson_a_id),
                ).lastrowid
            )

            with self.assertRaisesRegex(
                sqlite3.IntegrityError,
                "lesson belongs to another company",
            ):
                connection.execute(
                    "UPDATE lesson_progress SET company_id = 'company-b' WHERE id = ?",
                    (progress_id,),
                )


if __name__ == "__main__":
    unittest.main()
