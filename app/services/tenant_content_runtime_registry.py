"""Tenant-separated content runtimes for the Web application."""

from __future__ import annotations

from pathlib import Path

from app.content.runtime import ContentRuntime

LEGACY_COMPANY_ID = "intertop"


class TenantContentRuntimeRegistry:
    """Return one cached filesystem runtime per verified tenant id.

    The original Intertop content remains at the configured root for a safe
    zero-copy migration. Every subsequently provisioned company is confined
    to a direct child directory named after its company id.
    """

    def __init__(self, courses_root: Path) -> None:
        self._courses_root = courses_root.resolve()
        self._legacy_runtime = ContentRuntime(self._courses_root)
        self._runtimes: dict[str, ContentRuntime] = {}

    def get_runtime(self, company_id: str) -> ContentRuntime:
        normalized_company_id = _validate_company_id(company_id)
        if normalized_company_id == LEGACY_COMPANY_ID:
            return self._legacy_runtime

        runtime = self._runtimes.get(normalized_company_id)
        if runtime is None:
            tenant_dir = self._tenant_dir(normalized_company_id)
            runtime = ContentRuntime(tenant_dir)
            self._runtimes[normalized_company_id] = runtime
        return runtime

    @property
    def legacy_runtime(self) -> ContentRuntime:
        """The compatibility runtime that serves the Intertop tenant."""
        return self._legacy_runtime

    def _tenant_dir(self, company_id: str) -> Path:
        tenant_dir = (self._courses_root / company_id).resolve()
        if tenant_dir.parent != self._courses_root:
            raise ValueError("company_id must be a single safe path component")
        return tenant_dir


def _validate_company_id(company_id: str) -> str:
    if not isinstance(company_id, str):
        raise ValueError("company_id must be a string")
    normalized = company_id.strip()
    if not normalized:
        raise ValueError("company_id must not be empty")
    if normalized in {".", ".."} or "/" in normalized or "\\" in normalized:
        raise ValueError("company_id must be a single safe path component")
    return normalized
