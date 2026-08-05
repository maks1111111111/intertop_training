"""Tests for structured practical task model (``app.content.practical_task``)."""

from __future__ import annotations

import unittest

from app.content.practical_task import PracticalTask


class PracticalTaskTests(unittest.TestCase):
    """Tests for :class:`PracticalTask`."""

    def test_create_with_all_fields(self) -> None:
        task = PracticalTask(
            title="Inspect the work area",
            description="Walk through the store and identify safety hazards.",
            expected_result="A written list of at least three hazards.",
            estimated_minutes=15,
        )

        self.assertEqual(task.title, "Inspect the work area")
        self.assertEqual(
            task.description,
            "Walk through the store and identify safety hazards.",
        )
        self.assertEqual(
            task.expected_result,
            "A written list of at least three hazards.",
        )
        self.assertEqual(task.estimated_minutes, 15)

    def test_create_without_estimated_minutes(self) -> None:
        task = PracticalTask(
            title="Role-play greeting",
            description="Practice greeting a customer at the entrance.",
            expected_result="Customer receives a friendly welcome.",
        )

        self.assertIsNone(task.estimated_minutes)

    def test_immutability(self) -> None:
        task = PracticalTask(
            title="Task",
            description="Do something.",
            expected_result="Done.",
        )

        with self.assertRaises(AttributeError):
            task.title = "Changed"  # type: ignore[misc]

    def test_equality(self) -> None:
        first = PracticalTask(
            title="Task",
            description="Description.",
            expected_result="Result.",
            estimated_minutes=10,
        )
        second = PracticalTask(
            title="Task",
            description="Description.",
            expected_result="Result.",
            estimated_minutes=10,
        )
        different = PracticalTask(
            title="Other",
            description="Description.",
            expected_result="Result.",
            estimated_minutes=10,
        )

        self.assertEqual(first, second)
        self.assertNotEqual(first, different)
