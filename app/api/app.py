"""FastAPI application factory for the Intertop Training Web Platform."""

from __future__ import annotations

from fastapi import FastAPI

from app.api.router import router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(title="Intertop Training API")
    application.include_router(router)
    return application


app = create_app()
