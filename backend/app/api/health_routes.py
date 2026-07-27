"""Dependency-free liveness and bounded readiness routes."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.config import Settings
from app.domain.repository import AssessmentRepository
from app.integrations.kst_engine import KstEngine

from .dependencies import get_kst_engine, get_repository, get_settings
from .dtos import (
    DependencyStatus,
    HealthResponse,
    ReadinessResponse,
)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live", response_model=HealthResponse)
async def live() -> HealthResponse:
    return HealthResponse(status="ok")


async def _bounded_ready(
    check: Callable[[], Awaitable[bool]], timeout: float
) -> bool:
    try:
        result = await asyncio.wait_for(check(), timeout=timeout)
        return result
    except Exception:
        return False


@router.get("/ready", response_model=ReadinessResponse)
async def ready(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    repository: Annotated[AssessmentRepository, Depends(get_repository)],
    engine: Annotated[KstEngine, Depends(get_kst_engine)],
) -> ReadinessResponse:
    supabase_ready, r_ready = await asyncio.gather(
        _bounded_ready(repository.is_ready, settings.readiness_timeout_seconds),
        _bounded_ready(engine.is_ready, settings.readiness_timeout_seconds),
    )
    available = supabase_ready and r_ready
    if not available:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if available else "unavailable",
        dependencies=DependencyStatus(
            supabase="ready" if supabase_ready else "unavailable",
            r="ready" if r_ready else "unavailable",
        ),
    )
