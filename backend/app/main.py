"""FastAPI application factory and operational behavior."""

import json
import logging
import re
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response
from starlette.types import Lifespan
from supabase import AsyncClientOptions, acreate_client

from app.api.auth import AuthorizationDenied
from app.api.health_routes import router as health_router
from app.api.or_routes import router as or_router
from app.api.player_routes import router as player_router
from app.config import Settings
from app.domain.graphs import GraphValidationError
from app.domain.repository import RepositoryDataError, RepositoryUnavailable
from app.integrations.kst_engine import HttpxKstEngine, RUnavailable
from app.observability import collect_dependency_metrics
from app.persistence.supabase_repository import SupabaseAssessmentRepository
from app.services.assessment import (
    AssessmentConflict,
    AssessmentNotFound,
    AssessmentService,
)
from app.services.questions import InvalidQuestion

logger = logging.getLogger("app.requests")
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_TEST_ID_PATH = re.compile(
    r"/tests/(?P<test_id>[0-9a-fA-F]{8}-[0-9a-fA-F-]{27,35})(?:/|$)"
)


def build_lifespan(settings: Settings) -> Lifespan[FastAPI]:
    """Build the production lifespan for shared dependency clients."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        supabase_http = httpx.AsyncClient(
            timeout=settings.supabase_request_timeout_seconds
        )
        r_http: httpx.AsyncClient | None = None
        try:
            supabase = await acreate_client(
                str(settings.supabase_url),
                settings.supabase_service_key.get_secret_value(),
                options=AsyncClientOptions(
                    httpx_client=supabase_http,
                    postgrest_client_timeout=settings.supabase_request_timeout_seconds,
                ),
            )
            r_http = httpx.AsyncClient(
                base_url=str(settings.r_service_url),
                timeout=httpx.Timeout(
                    connect=settings.r_connect_timeout_seconds,
                    read=settings.r_read_timeout_seconds,
                    write=settings.r_write_timeout_seconds,
                    pool=settings.r_pool_timeout_seconds,
                ),
                limits=httpx.Limits(
                    max_connections=settings.r_max_connections,
                    max_keepalive_connections=settings.r_max_connections,
                ),
            )
            repository = SupabaseAssessmentRepository(supabase)
            engine = HttpxKstEngine(r_http)
            app.state.repository = repository
            app.state.kst_engine = engine
            app.state.assessment_service = AssessmentService(
                repository,
                engine,
                max_graph_nodes=settings.max_graph_nodes,
            )
            yield
        finally:
            if r_http is not None:
                await r_http.aclose()
            await supabase_http.aclose()

    return lifespan


def create_app(
    settings: Settings | None = None,
    *,
    lifespan: Lifespan[FastAPI] | None = None,
) -> FastAPI:
    """Create an independently testable API application."""

    resolved_settings = settings or Settings.model_validate({})
    app = FastAPI(
        title="Assessment Orchestrator",
        version="1.0.0",
        lifespan=lifespan or build_lifespan(resolved_settings),
    )
    app.state.settings = resolved_settings
    app.include_router(health_router)
    app.include_router(or_router)
    app.include_router(player_router)
    _register_exception_handlers(app)
    app.middleware("http")(_request_completion_middleware)
    return app


def _register_exception_handlers(app: FastAPI) -> None:
    mappings: tuple[
        tuple[type[Exception], int, str, str],
        ...,
    ] = (
        (
            AssessmentNotFound,
            404,
            "assessment_not_found",
            "Assessment not found.",
        ),
        (AuthorizationDenied, 403, "forbidden", "Operation is not authorized."),
        (
            AssessmentConflict,
            409,
            "assessment_conflict",
            "Assessment state conflicts with this operation.",
        ),
        (GraphValidationError, 422, "invalid_graph", "Graph is invalid."),
        (
            RepositoryUnavailable,
            503,
            "supabase_unavailable",
            "Persistence service is unavailable.",
        ),
        (RUnavailable, 503, "r_unavailable", "Calculation service is unavailable."),
        (
            RepositoryDataError,
            500,
            "internal_error",
            "The request could not be completed.",
        ),
        (
            InvalidQuestion,
            500,
            "internal_error",
            "The request could not be completed.",
        ),
    )
    for exception_type, status_code, code, message in mappings:
        app.add_exception_handler(
            exception_type,
            _failure_handler(status_code, code, message),
        )


def _failure_handler(
    status_code: int, code: str, message: str
) -> Callable[[Request, Exception], Awaitable[Response]]:
    async def handler(request: Request, _error: Exception) -> Response:
        request.state.outcome_code = code
        return _error_response(status_code, code, message)

    return handler


async def _request_completion_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    started_at = perf_counter()
    supplied_request_id = request.headers.get("X-Request-ID", "")
    request_id = (
        supplied_request_id
        if _SAFE_REQUEST_ID.fullmatch(supplied_request_id)
        else str(uuid4())
    )
    status_code = 500
    request.state.outcome_code = "internal_error"
    with collect_dependency_metrics() as metrics:
        try:
            response = await call_next(request)
            status_code = response.status_code
            if not hasattr(request.state, "outcome_code") or (
                request.state.outcome_code == "internal_error" and status_code < 500
            ):
                request.state.outcome_code = _outcome_for_status(status_code)
        except Exception as error:
            logger.error(
                "unhandled_request_exception",
                extra={
                    "request_id": request_id,
                    "diagnostic": type(error).__name__,
                },
            )
            response = _error_response(
                500, "internal_error", "The request could not be completed."
            )
        response.headers["X-Request-ID"] = request_id
        status_code = response.status_code
    match = _TEST_ID_PATH.search(request.url.path)
    event: dict[str, object] = {
        "event": "request_completed",
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "status": status_code,
        "outcome": request.state.outcome_code,
        "total_ms": round((perf_counter() - started_at) * 1000, 3),
        "supabase_ms": round(metrics.supabase_seconds * 1000, 3),
        "supabase_execute_count": metrics.supabase_execute_count,
        "r_ms": round(metrics.r_seconds * 1000, 3),
        "r_request_count": metrics.r_request_count,
    }
    if match is not None:
        event["test_id"] = match.group("test_id")
    logger.info(json.dumps(event, separators=(",", ":"), sort_keys=True))
    return response


def _outcome_for_status(status_code: int) -> str:
    if status_code < 300:
        return "success"
    if status_code == 422:
        return "validation_error"
    if status_code < 500:
        return "client_error"
    return "server_error"


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )
