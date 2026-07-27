"""Unified local project check: content validation, tests, and compilation."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class _CheckStep:
    label: str
    args: Tuple[str, ...]


_CHECKS: Tuple[_CheckStep, ...] = (
    _CheckStep("Content validation", ("-m", "app.content.cli")),
    _CheckStep("Unit tests", ("-m", "unittest", "discover", "-s", "tests")),
    _CheckStep("Python compilation", ("-m", "compileall", "app")),
)


def _run_check(step: _CheckStep) -> int:
    """Run a single check and return its exit code."""
    print(f"=== {step.label} ===")
    completed = subprocess.run(
        [sys.executable, *step.args],
        check=False,
    )
    exit_code = completed.returncode
    if exit_code == 0:
        print(f"[PASS] {step.label}")
    else:
        print(f"[FAIL] {step.label} (exit code: {exit_code})")
    print()
    return exit_code


def main() -> int:
    """Run all project checks and print a summary."""
    results: List[Tuple[str, int]] = []

    for step in _CHECKS:
        exit_code = _run_check(step)
        results.append((step.label, exit_code))

    print("=== Project check summary ===")
    all_passed = True
    for label, exit_code in results:
        if exit_code == 0:
            print(f"[PASS] {label}")
        else:
            print(f"[FAIL] {label} (exit code: {exit_code})")
            all_passed = False

    print()
    if all_passed:
        print("PROJECT STATUS: PASS")
        return 0

    print("PROJECT STATUS: FAIL")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
