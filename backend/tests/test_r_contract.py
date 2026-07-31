"""Opt-in FastAPI readiness contract against the real R service."""

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import FastAPI

from app.config import Settings
from app.integrations.kst_engine import HttpxKstEngine
from app.main import create_app
from app.services.assessment import AssessmentService
from tests.fakes.assessment_repository import InMemoryAssessmentRepository

R_CONTRACT_BASE_URL = os.environ.get("R_CONTRACT_BASE_URL")


@pytest.mark.r_contract
@pytest.mark.asyncio
@pytest.mark.skipif(
    R_CONTRACT_BASE_URL is None,
    reason="R_CONTRACT_BASE_URL is not configured",
)
async def test_fastapi_readiness_with_real_r_service() -> None:
    if R_CONTRACT_BASE_URL is None:
        raise AssertionError("skip guard did not run")
    contract_url: str = R_CONTRACT_BASE_URL
    settings = Settings.model_validate(
        {
            "SUPABASE_URL": "https://contract.invalid",
            "SUPABASE_SERVICE_KEY": "contract-placeholder",
            "R_SERVICE_URL": contract_url,
            "ALLOWED_HOSTS": ["193.40.157.124", "127.0.0.1", "testserver"],
        }
    )
    repository = InMemoryAssessmentRepository()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        async with httpx.AsyncClient(
            base_url=contract_url,
            timeout=2,
        ) as r_http:
            engine = HttpxKstEngine(r_http)
            app.state.repository = repository
            app.state.kst_engine = engine
            app.state.assessment_service = AssessmentService(
                repository,
                engine,
                max_graph_nodes=settings.max_graph_nodes,
            )
            yield

    app = create_app(settings, lifespan=lifespan)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "dependencies": {"supabase": "ready", "r": "ready"},
    }
