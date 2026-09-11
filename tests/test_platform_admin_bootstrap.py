"""Contract tests for the one-time platform-owner bootstrap command."""

from __future__ import annotations

import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from app.database.db import get_connection, initialize_database
from app.platform_admin_bootstrap import main


class PlatformAdminBootstrapCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "test.db"
        initialize_database(self.db_path)
        with get_connection(self.db_path) as connection:
            self.user_id = int(
                connection.execute(
                    "INSERT INTO users (username) VALUES ('owner')"
                ).lastrowid
            )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_bootstraps_existing_user_without_hardcoded_credentials(self) -> None:
        stdout = StringIO()
        with redirect_stdout(stdout):
            exit_code = main(["--db", str(self.db_path), "--user-id", str(self.user_id)])

        self.assertEqual(exit_code, 0)
        self.assertIn(f"user_id={self.user_id}", stdout.getvalue())

    def test_refuses_second_owner_bootstrap(self) -> None:
        second_user_id = self.user_id + 1
        with get_connection(self.db_path) as connection:
            connection.execute(
                "INSERT INTO users (id, username) VALUES (?, 'second-owner')",
                (second_user_id,),
            )
        self.assertEqual(
            main(["--db", str(self.db_path), "--user-id", str(self.user_id)]),
            0,
        )

        stderr = StringIO()
        with redirect_stderr(stderr):
            exit_code = main(["--db", str(self.db_path), "--user-id", str(second_user_id)])

        self.assertEqual(exit_code, 2)
        self.assertIn("owner already exists", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
