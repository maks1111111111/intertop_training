"""Tests for AI client abstraction (``app.ai.client``)."""

from __future__ import annotations

import unittest

from app.ai.client import AIClient, DummyAIClient


class DummyAIClientTests(unittest.TestCase):
    """Tests for :class:`DummyAIClient`."""

    def setUp(self) -> None:
        self.client = DummyAIClient()

    def test_implements_ai_client_contract(self) -> None:
        client: AIClient = self.client

        self.assertTrue(callable(client.generate))

    def test_generate_raises_not_implemented_error(self) -> None:
        with self.assertRaises(NotImplementedError) as context:
            self.client.generate("Generate training lessons.")

        self.assertEqual(
            str(context.exception),
            "AI client generation is not implemented yet.",
        )
