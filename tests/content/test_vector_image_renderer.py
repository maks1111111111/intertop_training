"""Tests for optional, isolated legacy-vector rendering primitives."""

from __future__ import annotations

import io
import unittest
from pathlib import Path
import subprocess

from PIL import Image

from app.content.vector_image_renderer import (
    LibreOfficeVectorImageRenderer,
    VectorImageRenderError,
    _sandbox_profile,
    detect_legacy_vector_format,
)


class VectorImageRendererTests(unittest.TestCase):
    @staticmethod
    def _png_bytes() -> bytes:
        output = io.BytesIO()
        Image.new("RGB", (100, 100), (1, 2, 3)).save(output, format="PNG")
        return output.getvalue()

    def test_detects_controlled_wmf_and_emf_signatures(self) -> None:
        self.assertEqual(
            detect_legacy_vector_format(b"\xd7\xcd\xc6\x9a" + b"wmf"), "wmf"
        )
        emf = b"\x01\x00\x00\x00" + b"\x00" * 36 + b" EMF" + b"payload"
        self.assertEqual(detect_legacy_vector_format(emf), "emf")
        self.assertIsNone(detect_legacy_vector_format(b"not a vector"))
        self.assertIsNone(detect_legacy_vector_format(b"\xd7\xcd"))

    def test_missing_renderer_fails_closed(self) -> None:
        renderer = LibreOfficeVectorImageRenderer(
            soffice_path=Path("/not-a-real/soffice"),
            sandbox_executable=Path("/not-a-real/sandbox-exec"),
        )

        with self.assertRaisesRegex(VectorImageRenderError, "renderer_unavailable") as caught:
            renderer.render_png(b"\xd7\xcd\xc6\x9a" + b"wmf", source_format="wmf")

        self.assertEqual(caught.exception.code, "renderer_unavailable")

    def test_missing_isolation_fails_closed_before_invoking_renderer(self) -> None:
        renderer = LibreOfficeVectorImageRenderer(
            soffice_path=Path("/bin/sh"),
            sandbox_executable=Path("/not-a-real/sandbox-exec"),
        )

        with self.assertRaisesRegex(
            VectorImageRenderError, "renderer_isolation_unavailable"
        ) as caught:
            renderer.render_png(b"\xd7\xcd\xc6\x9a" + b"wmf", source_format="wmf")

        self.assertEqual(caught.exception.code, "renderer_isolation_unavailable")

    def test_public_error_does_not_include_source_payload(self) -> None:
        renderer = LibreOfficeVectorImageRenderer(
            soffice_path=Path("/not-a-real/secret-source.wmf"),
            sandbox_executable=Path("/not-a-real/sandbox-exec"),
        )
        payload = b"\xd7\xcd\xc6\x9a" + b"customer-private-content"

        with self.assertRaises(VectorImageRenderError) as caught:
            renderer.render_png(payload, source_format="wmf")

        self.assertNotIn("customer-private-content", str(caught.exception))
        self.assertNotIn("secret-source.wmf", str(caught.exception))

    def test_sandbox_initialization_failure_is_not_reported_as_vector_failure(self) -> None:
        def unavailable_sandbox(argv, **kwargs):
            return subprocess.CompletedProcess(argv, 71)

        renderer = LibreOfficeVectorImageRenderer(
            soffice_path=Path("/bin/sh"),
            sandbox_executable=Path("/usr/bin/sandbox-exec"),
            runner=unavailable_sandbox,
        )

        with self.assertRaisesRegex(
            VectorImageRenderError, "renderer_isolation_unavailable"
        ) as caught:
            renderer.render_png(b"\xd7\xcd\xc6\x9a" + b"wmf", source_format="wmf")

        self.assertEqual(caught.exception.code, "renderer_isolation_unavailable")

    def test_renderer_uses_argv_shell_false_and_restrictive_profile(self) -> None:
        captured = {}

        def fake_runner(argv, **kwargs):
            captured["argv"] = argv
            captured["kwargs"] = kwargs
            output_directory = Path(argv[argv.index("--outdir") + 1])
            (output_directory / "input.png").write_bytes(self._png_bytes())
            return subprocess.CompletedProcess(argv, 0)

        renderer = LibreOfficeVectorImageRenderer(
            soffice_path=Path("/bin/sh"),
            sandbox_executable=Path("/usr/bin/sandbox-exec"),
            runner=fake_runner,
        )

        rendered = renderer.render_png(b"\xd7\xcd\xc6\x9a" + b"wmf", source_format="wmf")

        self.assertTrue(rendered.startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertIsInstance(captured["argv"], list)
        self.assertFalse(captured["kwargs"]["shell"])
        profile = captured["argv"][captured["argv"].index("-p") + 1]
        self.assertIn("(deny network*)", profile)
        self.assertNotIn("(allow file-read*)\n", profile)

    def test_sandbox_profile_does_not_grant_all_filesystem_reads(self) -> None:
        profile = _sandbox_profile(Path("/private/tmp/example"), runtime_root=Path("/opt/runtime"))

        self.assertNotIn("(allow file-read*)\n", profile)
        self.assertIn('(subpath "/opt/runtime")', profile)
        self.assertIn('(subpath "/private/tmp/example")', profile)


if __name__ == "__main__":
    unittest.main()
