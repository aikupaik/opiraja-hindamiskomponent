"""Shared production and experiment observability for Supabase executions."""

import logging
from time import perf_counter
from typing import Protocol

import httpx
from postgrest import APIError, APIResponse

from app.admin.diagnostics import emit_diagnostic
from app.logging_config import production_sanitizer
from app.observability import current_request_id, record_supabase_execute

logger = logging.getLogger("app.supabase")
_ERROR_TEXT_BYTES = 2 * 1024


class ExecutableQuery(Protocol):
    async def execute(self) -> APIResponse: ...


async def execute_supabase(
    query: ExecutableQuery,
    *,
    operation: str,
) -> APIResponse:
    """Execute and emit exactly one correlated event for the attempt."""

    started_at = perf_counter()
    duration_seconds = 0.0
    try:
        response = await query.execute()
    except Exception as error:
        duration_seconds = round((perf_counter() - started_at) * 1000, 3) / 1000
        payload = _failure_payload(operation, duration_seconds, error)
        _emit(payload, level=logging.WARNING)
        raise
    else:
        duration_seconds = round((perf_counter() - started_at) * 1000, 3) / 1000
        payload: dict[str, object] = {
            "event": "supabase_operation",
            "operation": operation,
            "outcome": "success",
            "duration_ms": round(duration_seconds * 1000, 3),
            "count": len(response.data),
        }
        _emit(payload, level=logging.INFO)
        return response
    finally:
        record_supabase_execute(
            started_at,
            duration_seconds=duration_seconds,
        )


def _failure_payload(
    operation: str, duration_seconds: float, error: Exception
) -> dict[str, object]:
    payload: dict[str, object] = {
        "event": "supabase_operation",
        "operation": operation,
        "outcome": "failed",
        "duration_ms": round(duration_seconds * 1000, 3),
        "count": 0,
        "error_type": type(error).__name__,
        "error_category": _error_category(error),
    }
    if isinstance(error, APIError):
        fields = {
            "error_code": error.code,
            "error_message": error.message,
            "error_details": error.details,
            "error_hint": error.hint,
        }
    else:
        fields = {"error_message": str(error)}
    sanitizer = production_sanitizer()
    for key, value in fields.items():
        if value is not None and value != "":
            payload[key] = sanitizer.sanitize(
                str(value), max_string_bytes=_ERROR_TEXT_BYTES
            )
    return payload


def _error_category(error: Exception) -> str:
    if isinstance(error, APIError):
        return "postgrest"
    if isinstance(error, (TimeoutError, httpx.TimeoutException)):
        return "timeout"
    if isinstance(error, httpx.HTTPError):
        return "transport"
    return "unexpected"


def _emit(payload: dict[str, object], *, level: int) -> None:
    request_id = current_request_id()
    if request_id is not None:
        payload["request_id"] = request_id
    safe_payload = production_sanitizer().sanitize(payload)
    if not isinstance(safe_payload, dict):
        raise TypeError("sanitized Supabase event must remain an object")
    logger.log(level, "supabase_operation", extra=safe_payload)
    emit_diagnostic(
        source="supabase",
        level="info" if level == logging.INFO else "warning",
        event_type="supabase_operation",
        payload=safe_payload,
    )
