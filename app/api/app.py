"""FastAPI application factory for the Intertop Training Web Platform."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.router import router
from app.content.runtime import ContentRuntime
from app.database.db import initialize_database
from app.env import load_project_env
from app.runtime_paths_config import RuntimePathsConfig
from app.services.course_sync import sync_courses
from app.web.csrf import SameOriginCSRFMiddleware
from app.web.router import router as web_router


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    load_project_env()
    runtime_paths = RuntimePathsConfig.from_environment()
    application = FastAPI(title="Intertop Training API")
    application.add_middleware(SameOriginCSRFMiddleware)
    db_path = runtime_paths.db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    initialize_database(db_path)
    courses_dir = runtime_paths.courses_dir
    sync_courses(
        base_dir=courses_dir,
        db_path=db_path,
    )
    application.state.db_path = db_path
    application.state.content_runtime = ContentRuntime(courses_dir)
    application.state.upload_dir = runtime_paths.upload_dir
    application.state.runtime_paths = runtime_paths
    application.include_router(router)
    application.include_router(web_router)
    static_dir = Path(__file__).resolve().parents[1] / "web" / "static"
    application.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    return application


app = create_app()
