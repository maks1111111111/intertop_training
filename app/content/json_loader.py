"""Safe JSON loading helpers for content validators.

This module provides a single entry point for reading JSON files while
collecting structured errors into a :class:`ValidationReport`. It does not
validate JSON semantics or integrate with the runtime scanner.
"""

import json
from pathlib import Path
from typing import Any, Optional

from app.content.models import ValidationReport


def load_json_file(
    path: Path,
    report: ValidationReport,
    *,
    missing_code: Optional[str] = None,
    missing_message: Optional[str] = None,
    location: Optional[str] = None,
) -> Optional[Any]:
    """Load a JSON file and record validation errors in ``report``.

    The function never raises expected I/O or JSON syntax errors. Callers
    receive parsed JSON on success, or ``None`` when the file is missing,
    unreadable, or syntactically invalid.

    Args:
        path: Path to the JSON file to read.
        report: Validation report that receives any discovered errors.
        missing_code: When provided, a missing or non-file ``path`` adds an
            ``ERROR`` with this code to ``report``. When omitted, a missing
            file returns ``None`` silently.
        missing_message: Custom message for the missing-file error. Defaults
            to a message that includes the file name.
        location: Optional logical location inside structured content, for
            example ``"questions[3]"``.

    Returns:
        Parsed JSON value on success, or ``None`` when loading fails.
    """
    if not path.is_file():
        if missing_code is not None:
            message = missing_message
            if message is None:
                message = f"Required JSON file is missing: {path.name}"
            report.add_error(
                code=missing_code,
                message=message,
                path=path,
                location=location,
            )
        return None

    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        report.add_error(
            code="json_file_unreadable",
            message=(
                f"Cannot read JSON file {path.name}: {exc.strerror or exc}"
            ),
            path=path,
            location=location,
        )
        return None

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        report.add_error(
            code="invalid_json",
            message=(
                f"Invalid JSON in {path.name}: "
                f"line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ),
            path=path,
            location=location,
        )
        return None
