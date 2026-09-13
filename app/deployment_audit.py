"""Read-only preflight for a configured remote Intertop deployment."""

from __future__ import annotations

import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

from app.database.platform_audit import audit_platform_data
from app.database.tenant_audit import audit_tenant_data
from app.deployment_config import DeploymentConfig
from app.env import load_project_env
from app.runtime_paths_config import RuntimePathsConfig
from app.web_server import WebServerConfig


@dataclass(frozen=True)
class DeploymentAuditFinding:
    """One non-sensitive configuration or data issue requiring review."""

    code: str
    detail: str


@dataclass(frozen=True)
class DeploymentAuditReport:
    """Combined, non-mutating result for a configured deployment."""

    environment: str
    findings: tuple[DeploymentAuditFinding, ...]

    @property
    def is_clean(self) -> bool:
        return not self.findings


def audit_deployment(
    deployment_config: DeploymentConfig,
    runtime_paths: RuntimePathsConfig,
    web_server_config: WebServerConfig,
) -> DeploymentAuditReport:
    """Check remote configuration, persistent paths and existing SQLite data."""
    findings: list[DeploymentAuditFinding] = []
    if deployment_config.environment == "development":
        findings.append(
            DeploymentAuditFinding(
                code="remote_environment_required",
                detail="set INTERTOP_ENV to staging or production before deployment",
            )
        )

    _validate_runtime_paths(deployment_config, runtime_paths, findings)
    _validate_web_server(web_server_config, findings)

    if runtime_paths.db_path.is_file():
        _append_database_findings(runtime_paths.db_path, findings)
    else:
        findings.append(
            DeploymentAuditFinding(
                code="database_file_missing",
                detail=f"database file does not exist: {runtime_paths.db_path}",
            )
        )

    return DeploymentAuditReport(
        environment=deployment_config.environment,
        findings=tuple(findings),
    )


def format_report(report: DeploymentAuditReport) -> str:
    """Render a deterministic operator-facing deployment report."""
    lines = [
        "DEPLOYMENT_AUDIT",
        f"environment={report.environment}",
        f"findings={len(report.findings)}",
    ]
    if report.is_clean:
        lines.append("status=clean")
        return "\n".join(lines)

    lines.append("status=review_required")
    lines.extend(
        f"- code={finding.code} detail={finding.detail}"
        for finding in report.findings
    )
    return "\n".join(lines)


def run() -> int:
    """Run the configured preflight and return 1 when review is required."""
    load_project_env()
    try:
        deployment_config = DeploymentConfig.from_environment()
        runtime_paths = RuntimePathsConfig.from_environment()
        deployment_config.validate_runtime_paths(runtime_paths)
        web_server_config = WebServerConfig.from_environment()
    except RuntimeError as error:
        print(f"Error: invalid deployment configuration: {error}", file=sys.stderr)
        return 2

    report = audit_deployment(
        deployment_config,
        runtime_paths,
        web_server_config,
    )
    print(format_report(report))
    return 0 if report.is_clean else 1


def _validate_runtime_paths(
    deployment_config: DeploymentConfig,
    runtime_paths: RuntimePathsConfig,
    findings: list[DeploymentAuditFinding],
) -> None:
    try:
        deployment_config.validate_runtime_paths(runtime_paths)
    except RuntimeError as error:
        findings.append(
            DeploymentAuditFinding(
                code="runtime_path_inside_checkout",
                detail=str(error),
            )
        )

    for variable_name, directory in (
        ("INTERTOP_DB_PATH", runtime_paths.db_path.parent),
        ("INTERTOP_COURSES_DIR", runtime_paths.courses_dir),
        ("INTERTOP_UPLOAD_DIR", runtime_paths.upload_dir),
    ):
        if not directory.is_dir():
            findings.append(
                DeploymentAuditFinding(
                    code="runtime_directory_missing",
                    detail=f"{variable_name} parent is missing: {directory}",
                )
            )


def _validate_web_server(
    web_server_config: WebServerConfig,
    findings: list[DeploymentAuditFinding],
) -> None:
    if web_server_config.host not in {"127.0.0.1", "::1", "localhost"}:
        findings.append(
            DeploymentAuditFinding(
                code="web_listener_not_loopback",
                detail=(
                    "INTERTOP_WEB_HOST must be a loopback address when using "
                    "the bundled one-VPS Nginx deployment"
                ),
            )
        )


def _append_database_findings(
    db_path: Path,
    findings: list[DeploymentAuditFinding],
) -> None:
    try:
        tenant_report = audit_tenant_data(db_path)
        platform_report = audit_platform_data(db_path)
    except sqlite3.Error as error:
        findings.append(
            DeploymentAuditFinding(
                code="database_audit_failed",
                detail=str(error),
            )
        )
        return

    findings.extend(
        DeploymentAuditFinding(
            code=f"tenant.{finding.code}",
            detail=(
                f"table={finding.table_name} id={finding.record_id} "
                f"company_id={finding.company_id} detail={finding.detail}"
            ),
        )
        for finding in tenant_report.findings
    )
    findings.extend(
        DeploymentAuditFinding(
            code=f"platform.{finding.code}",
            detail=finding.detail,
        )
        for finding in platform_report.findings
    )


if __name__ == "__main__":
    raise SystemExit(run())
