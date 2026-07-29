"""Data models for content validation reports.

These models describe validation findings without performing validation
itself. Validators collect :class:`ContentIssue` instances into a
:class:`ValidationReport` that callers can inspect or serialize.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class IssueSeverity(Enum):
    """Severity level assigned to a content validation issue.

    ``ERROR`` marks problems that make content unusable or unsafe to load.
    ``WARNING`` marks non-blocking issues that authors should review.
    """

    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass
class ContentIssue:
    """A single content validation finding.

    Attributes:
        severity: Whether the issue blocks publication (``ERROR``) or is
            advisory (``WARNING``).
        code: Stable machine-readable identifier, for example
            ``"missing_course_json"``.
        message: Human-readable explanation of the problem.
        path: Filesystem path related to the issue, if applicable.
        location: Logical location inside structured content, for example
            ``"questions[3].options[2]"``, when a file path alone is not
            precise enough.
    """

    severity: IssueSeverity
    code: str
    message: str
    path: Optional[Path] = None
    location: Optional[str] = None


@dataclass
class ValidationReport:
    """Aggregated result of validating course content.

    The report stores all discovered issues and exposes convenience helpers
    for filtering errors and warnings. It does not print output or perform
    I/O; callers decide how to present or persist the collected data.

    A report evaluates to ``False`` in boolean context when it contains
    at least one error, and to ``True`` when there are no errors. Warnings
    do not affect truthiness.
    """

    issues: list[ContentIssue] = field(default_factory=list)

    def add_error(
        self,
        code: str,
        message: str,
        path: Optional[Path] = None,
        location: Optional[str] = None,
    ) -> None:
        """Append an :class:`IssueSeverity.ERROR` issue to the report."""
        self.issues.append(
            ContentIssue(
                severity=IssueSeverity.ERROR,
                code=code,
                message=message,
                path=path,
                location=location,
            )
        )

    def add_warning(
        self,
        code: str,
        message: str,
        path: Optional[Path] = None,
        location: Optional[str] = None,
    ) -> None:
        """Append an :class:`IssueSeverity.WARNING` issue to the report."""
        self.issues.append(
            ContentIssue(
                severity=IssueSeverity.WARNING,
                code=code,
                message=message,
                path=path,
                location=location,
            )
        )

    @property
    def errors(self) -> list[ContentIssue]:
        """All issues with severity ``ERROR``."""
        return [
            issue
            for issue in self.issues
            if issue.severity is IssueSeverity.ERROR
        ]

    @property
    def warnings(self) -> list[ContentIssue]:
        """All issues with severity ``WARNING``."""
        return [
            issue
            for issue in self.issues
            if issue.severity is IssueSeverity.WARNING
        ]

    @property
    def has_errors(self) -> bool:
        """Return ``True`` when the report contains at least one error."""
        return any(
            issue.severity is IssueSeverity.ERROR
            for issue in self.issues
        )

    @property
    def has_warnings(self) -> bool:
        """Return ``True`` when the report contains at least one warning."""
        return any(
            issue.severity is IssueSeverity.WARNING
            for issue in self.issues
        )

    def is_release_ready(self) -> bool:
        """Return ``True`` when the content has no blocking errors.

        Warnings do not affect release readiness.
        """
        return not self.has_errors

    def summary(self) -> dict:
        """Return a structured release readiness summary.

        Returns:
            A dictionary with keys ``ready``, ``errors``, and ``warnings``.
            ``ready`` is ``True`` when there are no errors; warnings are
            counted but do not affect readiness.
        """
        return {
            "ready": self.is_release_ready(),
            "errors": len(self.errors),
            "warnings": len(self.warnings),
        }

    def __bool__(self) -> bool:
        """Return ``False`` when errors are present, otherwise ``True``."""
        return not self.has_errors
