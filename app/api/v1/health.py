"""Health check endpoint for API liveness."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Liveness response for the HTTP API."""

    status: str


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Return a simple liveness indicator for the API application."""
    return HealthResponse(status="ok")
