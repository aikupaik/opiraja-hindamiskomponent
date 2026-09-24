"""Structured logging and request-context behavior."""

import asyncio
import json
import logging

import httpx
import pytest
from postgrest import APIError, APIResponse

from app.admin.diagnostics import DiagnosticHub, diagnostic_context
from app.logging_config import (
    ProductionSanitizer,
    StructuredJsonFormatter,
    build_logging_config,
    safe_exception_chain,
    safe_exception_location,
    truncate_utf8,
)
from app.logging_config import configure_production_sanitizer
from app.observability import (
    collect_dependency_metrics,
    reset_request_id,
    set_request_id,
)
from app.supabase_observability import execute_supabase


class _SuccessfulQuery:
    async def execute(self) -> APIResponse:
        return APIResponse(data=[{"id": 1}])


class _FailedQuery:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def execute(self) -> APIResponse:
        raise self._error


def test_formatter_emits_one_line_json_with_context_and_fields() -> None:
    formatter = StructuredJsonFormatter(service="api")
    record = logging.LogRecord(
        name="app.requests",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request_completed",
        args=(),
        exc_info=None,
    )
    record.method = "GET"
    record.path = "/api/v1/tests/example"
    record.status = 200
    token = set_request_id("request.safe-123")
    try:
        output = formatter.format(record)
    finally:
        reset_request_id(token)

    assert "\n" not in output
    event = json.loads(output)
    assert event == {
        "timestamp": event["timestamp"],
        "schema_version": 1,
        "level": "INFO",
        "service": "api",
        "event": "request_completed",
        "request_id": "request.safe-123",
        "method": "GET",
        "path": "/api/v1/tests/example",
        "status": 200,
    }


def test_logging_config_keeps_access_logging_disabled() -> None:
    config = build_logging_config("INFO")
    loggers = config["loggers"]
    assert isinstance(loggers, dict)
    assert loggers["app"]["level"] == "INFO"
    assert loggers["uvicorn.access"]["handlers"] == []


def test_exception_location_does_not_include_exception_text() -> None:
    secret = "must-not-appear"
    try:
        raise RuntimeError(secret)
    except RuntimeError as error:
        location = safe_exception_location(error)

    assert location is not None
    assert "test_exception_location_does_not_include_exception_text" in location
    assert secret not in location


def test_sanitizer_redacts_nested_secrets_tokens_and_limits_utf8() -> None:
    secret = "configured-service-secret"
    jwt = "abcdefghij.abcdefghij.abcdefghij"
    sanitizer = ProductionSanitizer((secret,))

    value = sanitizer.sanitize(
        {
            "Authorization": "Bearer exposed",
            "nested": [
                f"prefix {secret}",
                f"https://example.test/path?access_token=exposed&next=1 {jwt}",
                "õ" * 20,
            ],
        },
        max_string_bytes=24,
    )

    serialized = json.dumps(value, ensure_ascii=False)
    assert "exposed" not in serialized
    assert secret not in serialized
    assert jwt not in serialized
    assert "[REDACTED]" in serialized
    assert truncate_utf8("õ" * 20, 24).endswith("[TRUNCATED]")


def test_exception_chain_contains_types_and_locations_but_no_messages() -> None:
    try:
        try:
            raise ValueError("database-row-secret")
        except ValueError as cause:
            raise RuntimeError("wrapper-secret") from cause
    except RuntimeError as error:
        chain = safe_exception_chain(error)

    assert [
        item["error_type"] for item in chain if isinstance(item, dict)
    ] == ["RuntimeError", "ValueError"]
    serialized = json.dumps(chain)
    assert "wrapper-secret" not in serialized
    assert "database-row-secret" not in serialized


def test_supabase_execution_emits_production_events_and_exact_metrics(
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_production_sanitizer(("database-secret",))
    caplog.set_level(logging.INFO, logger="app.supabase")
    token = set_request_id("request.database-123")
    hub = DiagnosticHub()

    async def scenario() -> None:
        with diagnostic_context(hub, "experiment-1"):
            with collect_dependency_metrics() as metrics:
                response = await execute_supabase(
                    _SuccessfulQuery(), operation="example.select"
                )
                assert response.data == [{"id": 1}]
        assert metrics.supabase_execute_count == 1
        assert metrics.supabase_seconds >= 0

    try:
        asyncio.run(scenario())
    finally:
        reset_request_id(token)

    record = next(
        item
        for item in caplog.records
        if item.name == "app.supabase" and item.getMessage() == "supabase_operation"
    )
    event = record.__dict__
    assert event["operation"] == "example.select"
    assert event["outcome"] == "success"
    assert event["count"] == 1
    assert event["request_id"] == "request.database-123"
    diagnostic = hub.events_after("experiment-1")
    assert len(diagnostic) == 1
    assert diagnostic[0].type == "supabase_operation"
    assert diagnostic[0].payload == {
        "event": "supabase_operation",
        "operation": "example.select",
        "outcome": "success",
        "duration_ms": event["duration_ms"],
        "count": 1,
        "request_id": "request.database-123",
    }


def test_supabase_error_fields_are_categorized_sanitized_and_limited(
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_production_sanitizer(("database-secret",))
    caplog.set_level(logging.WARNING, logger="app.supabase")
    error = APIError(
        {
            "code": "23505",
            "message": "database-secret " + ("õ" * 3000),
            "details": "duplicate detail",
            "hint": "retry hint",
        }
    )

    with pytest.raises(APIError):
        asyncio.run(
            execute_supabase(_FailedQuery(error), operation="example.insert")
        )

    record = next(
        item
        for item in caplog.records
        if item.name == "app.supabase" and item.getMessage() == "supabase_operation"
    )
    event = record.__dict__
    error_message = event["error_message"]
    assert isinstance(error_message, str)
    assert event["outcome"] == "failed"
    assert event["error_category"] == "postgrest"
    assert event["error_code"] == "23505"
    assert "database-secret" not in error_message
    assert error_message.endswith("[TRUNCATED]")
    assert len(error_message.encode("utf-8")) <= 2048
    assert event["error_details"] == "duplicate detail"
    assert event["error_hint"] == "retry hint"


@pytest.mark.parametrize(
    ("error", "category"),
    [
        (TimeoutError("slow"), "timeout"),
        (httpx.ReadTimeout("slow"), "timeout"),
        (httpx.ConnectError("offline"), "transport"),
    ],
)
def test_supabase_transport_categories(
    error: Exception,
    category: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="app.supabase")
    with pytest.raises(type(error)):
        asyncio.run(
            execute_supabase(_FailedQuery(error), operation="example.select")
        )
    assert caplog.records[-1].__dict__["error_category"] == category


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR"])
def test_logging_config_accepts_supported_levels(level: str) -> None:
    assert build_logging_config(level)["loggers"]
