"""Health check endpoint for API liveness."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.automation_health import automation_is_healthy
from app.database.db import get_connection

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Liveness response for the HTTP API."""

    status: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return a simple liveness indicator for the API application."""
    return HealthResponse(status="ok")


@router.get("/ready", response_model=HealthResponse)
def readiness(request: Request) -> HealthResponse:
    """Report whether the application can query its primary database."""
    try:
        db_path = request.app.state.db_path
        if not db_path.is_file():
            raise FileNotFoundError(db_path)
        with get_connection(db_path) as connection:
            connection.execute("SELECT 1 FROM users LIMIT 1").fetchone()
    except (AttributeError, OSError, sqlite3.Error) as error:
        raise HTTPException(
            status_code=503,
            detail="Service unavailable",
        ) from error

    return HealthResponse(status="ready")


@router.get("/automation-ready", response_model=HealthResponse)
def automation_readiness() -> HealthResponse:
    """Report whether critical daily automation completed recently."""
    if not automation_is_healthy():
        raise HTTPException(
            status_code=503,
            detail="Automation unavailable",
        )
    return HealthResponse(status="ready")
