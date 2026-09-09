"""Structured logging and request-context behavior."""

import json
import logging

import pytest

from app.logging_config import (
    StructuredJsonFormatter,
    build_logging_config,
    safe_exception_location,
)
from app.observability import reset_request_id, set_request_id


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


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING", "ERROR"])
def test_logging_config_accepts_supported_levels(level: str) -> None:
    assert build_logging_config(level)["loggers"]
