"""FastAPI application factory for the Intertop Training Web Platform."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.router import router
from app.content.runtime import ContentRuntime
from app.database.db import initialize_database
from app.web.router import router as web_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    application = FastAPI(title="Intertop Training API")
    project_root = Path(__file__).resolve().parents[2]
    db_path = project_root / "data" / "training.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    initialize_database(db_path)
    application.state.db_path = db_path
    application.state.content_runtime = ContentRuntime(project_root / "courses")
    application.state.upload_dir = project_root / "data" / "uploads"
    application.include_router(router)
    application.include_router(web_router)
    static_dir = project_root / "app" / "web" / "static"
    application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    return application


app = create_app()
