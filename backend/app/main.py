"""FastAPI application factory and operational behavior."""

import json
import logging
import re
import secrets
from collections.abc import (
    AsyncGenerator,
    AsyncIterator,
    Awaitable,
    Callable,
    Generator,
    Mapping,
)
from contextlib import asynccontextmanager, contextmanager
from time import perf_counter
from typing import Protocol, cast
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response
from starlette.types import Lifespan
from supabase import AsyncClientOptions, acreate_client

from app.api.auth import AuthorizationDenied
from app.api.auth import AdminUnauthorized
from app.admin.diagnostics import DiagnosticHub, diagnostic_context, emit_diagnostic
from app.admin.ingestion import (
    SourceIngestor,
    SourceInvalid,
    SourceRemoteFailure,
    SourceTooLarge,
)
from app.admin.routes import AdminRowNotFound
from app.admin.routes import router as admin_router
from app.admin.supabase_repository import SupabaseAdminRepository
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
        source_http: httpx.AsyncClient | None = None
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
            source_http = httpx.AsyncClient()
            repository = SupabaseAssessmentRepository(supabase)
            admin_repository = SupabaseAdminRepository(supabase)
            engine = HttpxKstEngine(r_http)
            app.state.repository = repository
            app.state.admin_repository = admin_repository
            app.state.kst_engine = engine
            app.state.source_ingestor = SourceIngestor(source_http, settings)
            app.state.diagnostic_hub = DiagnosticHub(
                max_events=settings.admin_diagnostic_max_events,
                ttl_seconds=settings.admin_diagnostic_ttl_seconds,
                secrets=(
                    settings.supabase_service_key.get_secret_value(),
                    (
                        ""
                        if settings.admin_access_key is None
                        else settings.admin_access_key.get_secret_value()
                    ),
                ),
            )
            app.state.assessment_service = AssessmentService(
                repository,
                engine,
                max_graph_nodes=settings.max_graph_nodes,
            )
            yield
        finally:
            if r_http is not None:
                await r_http.aclose()
            if source_http is not None:
                await source_http.aclose()
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
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=resolved_settings.allowed_hosts,
    )
    app.state.settings = resolved_settings
    app.include_router(health_router)
    app.include_router(or_router)
    app.include_router(player_router)
    app.include_router(admin_router)
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
            AdminUnauthorized,
            401,
            "admin_unauthorized",
            "Valid admin credentials are required.",
        ),
        (AdminRowNotFound, 404, "admin_not_found", "Admin row was not found."),
        (SourceTooLarge, 413, "source_too_large", "Source exceeds configured limits."),
        (SourceInvalid, 422, "invalid_source", "Source content is invalid."),
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
    app.add_exception_handler(SourceRemoteFailure, _remote_source_failure)


async def _remote_source_failure(request: Request, error: Exception) -> Response:
    source_error = error
    if not isinstance(source_error, SourceRemoteFailure):
        return _error_response(
            502, "source_fetch_failed", "Source could not be fetched."
        )
    status_code = 504 if source_error.timed_out else 502
    request.state.outcome_code = (
        "source_fetch_timeout" if source_error.timed_out else "source_fetch_failed"
    )
    return _error_response(
        status_code,
        request.state.outcome_code,
        (
            "Source request timed out."
            if source_error.timed_out
            else "Source could not be fetched."
        ),
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
    experiment_id = _authenticated_experiment(request)
    match = _TEST_ID_PATH.search(request.url.path)
    test_id = None if match is None else match.group("test_id")
    status_code = 500
    request.state.outcome_code = "internal_error"
    hub = getattr(request.app.state, "diagnostic_hub", None)
    context = (
        diagnostic_context(
            hub,
            experiment_id,
            request_id=request_id,
            test_id=test_id,
        )
        if experiment_id is not None and isinstance(hub, DiagnosticHub)
        else _empty_context()
    )
    with context:
        if experiment_id is not None:
            emit_diagnostic(
                source="client",
                level="info",
                event_type="request",
                payload={
                    "method": request.method,
                    "path": request.url.path,
                    "body": await _json_request_body(request),
                },
            )
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
        response_body: object = None
        if experiment_id is not None:
            response_body = await _json_response_body(response)
            if isinstance(response_body, Mapping):
                response_mapping = cast(Mapping[object, object], response_body)
                body_test_id = response_mapping.get("test_id")
                if isinstance(body_test_id, str):
                    test_id = body_test_id
            emit_diagnostic(
                source="client",
                level="info" if status_code < 400 else "warning",
                event_type="response",
                request_id=request_id,
                test_id=test_id,
                payload={
                    "status": status_code,
                    "request_id": request_id,
                    "body": cast(object, response_body),
                },
            )
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
    if test_id is not None:
        event["test_id"] = test_id
    logger.info(json.dumps(event, separators=(",", ":"), sort_keys=True))
    completion_context = (
        diagnostic_context(
            hub,
            experiment_id,
            request_id=request_id,
            test_id=test_id,
        )
        if experiment_id is not None and isinstance(hub, DiagnosticHub)
        else _empty_context()
    )
    with completion_context:
        emit_diagnostic(
            source="fastapi",
            level="info" if status_code < 400 else "warning",
            event_type="request_completed",
            request_id=request_id,
            test_id=test_id,
            payload=event,
        )
    return response


@contextmanager
def _empty_context() -> Generator[None]:
    yield


def _authenticated_experiment(request: Request) -> str | None:
    if request.url.path.startswith("/api/v1/admin/experiments/"):
        return None
    if not (
        request.url.path == "/api/v1/tests"
        or request.url.path.startswith("/api/v1/player/tests/")
    ):
        return None
    experiment_id = request.headers.get("X-Experiment-ID")
    authorization = request.headers.get("Authorization", "")
    settings = request.app.state.settings
    if (
        not isinstance(settings, Settings)
        or settings.admin_access_key is None
        or experiment_id is None
        or not authorization.startswith("Bearer ")
    ):
        return None
    expected = settings.admin_access_key.get_secret_value()
    supplied = authorization.removeprefix("Bearer ")
    if not secrets.compare_digest(supplied.encode("utf-8"), expected.encode("utf-8")):
        return None
    try:
        return str(UUID(experiment_id))
    except ValueError:
        return None


async def _json_request_body(request: Request) -> object:
    body = await request.body()
    if not body:
        return None
    try:
        return cast(object, json.loads(body))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"unparsed_bytes": len(body)}


async def _json_response_body(response: Response) -> object:
    content_type = response.headers.get("content-type", "")
    if "application/json" not in content_type:
        return None
    body = getattr(response, "body", None)
    if not isinstance(body, bytes):
        streaming = cast(_StreamingBodyResponse, response)
        iterator = getattr(streaming, "body_iterator", None)
        if iterator is None:
            return None
        chunks: list[bytes] = []
        async for chunk in iterator:
            chunks.append(chunk.encode("utf-8") if isinstance(chunk, str) else chunk)
        body = b"".join(chunks)
        streaming.body_iterator = _replay_body(body)
    try:
        return cast(object, json.loads(body))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"unparsed_bytes": len(body)}


async def _replay_body(body: bytes) -> AsyncIterator[bytes]:
    yield body


class _StreamingBodyResponse(Protocol):
    body_iterator: AsyncIterator[bytes | str]


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
