"""Aggregate routers for API version 1."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import courses, health

router = APIRouter()
router.include_router(health.router)
router.include_router(courses.router)
