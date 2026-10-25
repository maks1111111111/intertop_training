"""Optional, isolated rendering of legacy Office vector image evidence.

This module is deliberately provider-neutral.  It never modifies source
evidence and only returns an in-memory PNG suitable for later bounded visual
preparation.  The LibreOffice implementation is opt-in: callers must inject
it into :class:`VisualSourceAnalyzer` after providing both an explicit binary
and an available network-isolation executable.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Protocol


VECTOR_SOURCE_FORMATS = frozenset({"wmf", "emf"})
VECTOR_RENDERER_FAILURE_CODES = frozenset(
    {
        "renderer_unavailable",
        "renderer_timeout",
        "malformed_vector",
        "rendered_output_invalid",
        "rendered_output_too_large",
        "rendered_dimensions_exceeded",
        "renderer_isolation_unavailable",
        "vector_source_too_large",
    }
)
MAX_VECTOR_SOURCE_BYTES = 5 * 1024 * 1024
MAX_VECTOR_RENDERED_BYTES = 5 * 1024 * 1024
DEFAULT_VECTOR_RENDER_TIMEOUT_SECONDS = 10.0
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
# ``sandbox-exec`` uses BSD's EX_OSERR (71) when the host cannot apply its
# policy at process start.  Treat that differently from a renderer conversion
# error: the renderer was never safely isolated.
_SANDBOX_INITIALIZATION_FAILURE_RETURN_CODES = frozenset({71})


class VectorImageRenderError(RuntimeError):
    """Safe, typed failure from an optional vector renderer."""

    def __init__(self, code: str) -> None:
        if code not in VECTOR_RENDERER_FAILURE_CODES:
            raise ValueError("unsupported vector renderer failure code")
        self.code = code
        super().__init__(f"vector image rendering failed: {code}")


class VectorImageRenderer(Protocol):
    """Render one declared legacy vector source image to trusted PNG bytes."""

    def render_png(self, content: bytes, *, source_format: str) -> bytes:
        """Return PNG bytes or raise :class:`VectorImageRenderError`."""
        ...


class LibreOfficeVectorImageRenderer:
    """Opt-in LibreOffice renderer guarded by macOS ``sandbox-exec``.

    This renderer is intentionally not discovered automatically.  A caller
    must supply explicit executable paths, and any unavailable isolation
    mechanism fails closed instead of running LibreOffice unsandboxed.
    """

    def __init__(
        self,
        *,
        soffice_path: Path,
        sandbox_executable: Path,
        timeout_seconds: float = DEFAULT_VECTOR_RENDER_TIMEOUT_SECONDS,
        runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    ) -> None:
        if not isinstance(soffice_path, Path) or not isinstance(sandbox_executable, Path):
            raise ValueError("vector renderer paths must be Path values")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or timeout_seconds <= 0
        ):
            raise ValueError("vector renderer timeout must be positive")
        if not callable(runner):
            raise ValueError("vector renderer runner must be callable")
        self._soffice_path = soffice_path
        self._sandbox_executable = sandbox_executable
        self._timeout_seconds = float(timeout_seconds)
        self._runner = runner

    def render_png(self, content: bytes, *, source_format: str) -> bytes:
        if source_format not in VECTOR_SOURCE_FORMATS:
            raise VectorImageRenderError("malformed_vector")
        if not isinstance(content, bytes) or not content:
            raise VectorImageRenderError("malformed_vector")
        if len(content) > MAX_VECTOR_SOURCE_BYTES:
            raise VectorImageRenderError("vector_source_too_large")
        if not _is_executable_file(self._soffice_path):
            raise VectorImageRenderError("renderer_unavailable")
        if not _is_executable_file(self._sandbox_executable):
            raise VectorImageRenderError("renderer_isolation_unavailable")

        with tempfile.TemporaryDirectory(prefix="mentorconnect-vector-") as raw_directory:
            directory = Path(raw_directory)
            source_path = directory / f"input.{source_format}"
            output_directory = directory / "output"
            profile_directory = directory / "profile"
            output_directory.mkdir()
            source_path.write_bytes(content)
            argv = [
                str(self._sandbox_executable),
                "-p",
                _sandbox_profile(
                    directory,
                    runtime_root=_renderer_runtime_root(self._soffice_path),
                ),
                str(self._soffice_path),
                "--headless",
                "--nologo",
                "--nodefault",
                "--nolockcheck",
                "--nofirststartwizard",
                "--norestore",
                f"-env:UserInstallation={profile_directory.as_uri()}",
                "--convert-to",
                "png",
                "--outdir",
                str(output_directory),
                str(source_path),
            ]
            try:
                completed = self._runner(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    shell=False,
                    timeout=self._timeout_seconds,
                    env={"TMPDIR": str(directory), "PATH": os.defpath},
                )
            except subprocess.TimeoutExpired:
                raise VectorImageRenderError("renderer_timeout") from None
            except (OSError, ValueError):
                raise VectorImageRenderError("renderer_unavailable") from None
            if completed.returncode in _SANDBOX_INITIALIZATION_FAILURE_RETURN_CODES:
                raise VectorImageRenderError("renderer_isolation_unavailable")
            if completed.returncode != 0:
                raise VectorImageRenderError("malformed_vector")

            output_path = output_directory / "input.png"
            try:
                rendered = output_path.read_bytes()
            except OSError:
                raise VectorImageRenderError("rendered_output_invalid") from None

        if len(rendered) > MAX_VECTOR_RENDERED_BYTES:
            raise VectorImageRenderError("rendered_output_too_large")
        if not rendered.startswith(_PNG_SIGNATURE):
            raise VectorImageRenderError("rendered_output_invalid")
        return rendered


def detect_legacy_vector_format(content: bytes) -> str | None:
    """Identify WMF/EMF bytes without trusting source filenames or MIME data."""
    if not isinstance(content, bytes):
        return None
    # Placeable WMF key, stored little-endian as D7 CD C6 9A.
    if content.startswith(b"\xd7\xcd\xc6\x9a"):
        return "wmf"
    # EMF records start with type 1 and carry the ASCII signature at offset 40.
    if len(content) >= 44 and content[:4] == b"\x01\x00\x00\x00" and content[40:44] == b" EMF":
        return "emf"
    return None


def _is_executable_file(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _renderer_runtime_root(soffice_path: Path) -> Path:
    """Return the narrowest practical root containing an Office runtime."""
    resolved = soffice_path.resolve()
    # Bundled and app-bundle ``soffice`` launchers both keep their runtime a
    # few levels above the launcher.  This remains narrower than a user home
    # directory and is never derived from document metadata.
    parents = resolved.parents
    return parents[2] if len(parents) > 2 else resolved.parent


def _sandbox_profile(directory: Path, *, runtime_root: Path) -> str:
    """Return a minimal macOS sandbox profile for one renderer invocation."""
    read_roots = (
        directory,
        runtime_root,
        Path("/System"),
        Path("/usr/lib"),
        Path("/usr/share"),
        Path("/Library/Fonts"),
    )
    profile = [
        "(version 1)",
        "(deny default)",
        "(allow process*)",
        "(deny network*)",
    ]
    profile.extend(
        f'(allow file-read* (subpath "{_sandbox_path(root)}"))'
        for root in read_roots
    )
    profile.append(f'(allow file-write* (subpath "{_sandbox_path(directory)}"))')
    return "\n".join(profile)


def _sandbox_path(path: Path) -> str:
    """Escape a controlled local path for the sandbox profile language."""
    return str(path).replace("\\", "\\\\").replace('"', "\\\"")
