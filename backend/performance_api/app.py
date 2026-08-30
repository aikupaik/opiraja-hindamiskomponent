"""Performance-only application factory with no network dependencies."""

import os
import re
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from random import Random
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import FastAPI

from app.admin.diagnostics import DiagnosticHub
from app.config import Settings
from app.main import create_app as create_production_app
from app.services.assessment import AssessmentService
from tests.fakes.assessment_repository import InMemoryAssessmentRepository

from .engine import DeterministicKstEngine
from .evidence import EventLoopLagSampler, export_evidence
from .fixtures import build_item_bank, load_fixtures

_RUN_ID = re.compile(r"^perf-[A-Za-z0-9._-]+$")


class _UuidSequence:
    def __init__(self, run_id: str) -> None:
        self._namespace = uuid5(NAMESPACE_URL, run_id)
        self._next_value = 1

    def __call__(self) -> UUID:
        value = uuid5(self._namespace, str(self._next_value))
        self._next_value += 1
        return value


class _DeterministicRandom:
    def __init__(self, run_id: str) -> None:
        self._random = Random(run_id)

    def shuffle(self, values: list[str]) -> None:
        self._random.shuffle(values)


def create_app() -> FastAPI:
    settings = Settings.model_validate({})
    run_id = _required_run_id(os.environ.get("PERF_RUN_ID"))
    workload = os.environ.get("PERF_API_WORKLOAD", "smoke")
    shape = os.environ.get("PERF_API_SHAPE", "all")
    evidence_path = Path(
        os.environ.get("PERF_API_EVIDENCE_PATH", "/tmp/api-only-state.json")
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        fixtures = load_fixtures()
        repository = InMemoryAssessmentRepository(record_calls=False)
        await repository.seed_items(*build_item_bank(fixtures))
        engine = DeterministicKstEngine(fixtures)
        loop_lag = EventLoopLagSampler()
        app.state.repository = repository
        app.state.kst_engine = engine
        app.state.assessment_service = AssessmentService(
            repository,
            engine,
            max_graph_nodes=settings.max_graph_nodes,
            random_source=_DeterministicRandom(run_id),
            uuid_factory=_UuidSequence(run_id),
        )
        app.state.diagnostic_hub = DiagnosticHub(
            max_events=settings.admin_diagnostic_max_events,
            ttl_seconds=settings.admin_diagnostic_ttl_seconds,
            secrets=(
                settings.supabase_service_key.get_secret_value(),
                settings.or_jwt_secret.get_secret_value(),
                settings.api_jwt_secret.get_secret_value(),
            ),
        )
        loop_lag.start()
        try:
            yield
        finally:
            await loop_lag.stop()
            export_evidence(
                evidence_path,
                run_id=run_id,
                workload=workload,
                shape=shape,
                repository=repository,
                engine=engine,
                loop_lag=loop_lag,
            )

    return create_production_app(settings, lifespan=lifespan)


def _required_run_id(value: str | None) -> str:
    if value is None or _RUN_ID.fullmatch(value) is None:
        raise ValueError(
            "PERF_RUN_ID must start with 'perf-' and contain only safe characters"
        )
    return value
