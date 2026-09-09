"""Structured production logging for the API process."""

import json
import logging
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from types import TracebackType
from typing import cast

from app.observability import current_request_id

LOG_SCHEMA_VERSION = 1
VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})
_STANDARD_RECORD_FIELDS: frozenset[str] = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class StructuredJsonFormatter(logging.Formatter):
    """Render an application or server log record as one JSON object."""

    def __init__(self, *, service: str) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "event", record.getMessage())
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "schema_version": LOG_SCHEMA_VERSION,
            "level": record.levelname,
            "service": self._service,
            "event": str(event),
        }
        request_id = getattr(record, "request_id", None) or current_request_id()
        if request_id is not None:
            payload["request_id"] = request_id
        record_values = cast(Mapping[str, object], record.__dict__)
        for key, value in record_values.items():
            if (
                key in _STANDARD_RECORD_FIELDS
                or key in payload
                or key in {"color_message", "event"}
            ):
                continue
            payload[key] = _json_value(value)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def build_logging_config(log_level: str) -> dict[str, object]:
    """Build the logging configuration consumed by Uvicorn."""

    if log_level not in VALID_LOG_LEVELS:
        raise ValueError("APP_LOG_LEVEL must be DEBUG, INFO, WARNING, or ERROR")
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "app.logging_config.StructuredJsonFormatter",
                "service": "api",
            }
        },
        "handlers": {
            "json": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "stream": "ext://sys.stdout",
            }
        },
        "loggers": {
            "app": {
                "handlers": ["json"],
                "level": log_level,
                "propagate": False,
            },
            "uvicorn": {
                "handlers": ["json"],
                "level": log_level,
                "propagate": False,
            },
            "uvicorn.error": {
                "level": log_level,
            },
            "uvicorn.access": {
                "handlers": [],
                "level": log_level,
                "propagate": False,
            },
        },
        "root": {
            "handlers": ["json"],
            "level": "WARNING",
        },
    }


def request_log_level(status_code: int) -> int:
    """Map an HTTP status to the severity used by completion events."""

    if status_code >= 500:
        return logging.ERROR
    if status_code >= 400:
        return logging.WARNING
    return logging.INFO


def safe_exception_location(error: BaseException) -> str | None:
    """Return the final traceback location without serializing error text."""

    traceback: TracebackType | None = error.__traceback__
    if traceback is None:
        return None
    while traceback.tb_next is not None:
        traceback = traceback.tb_next
    frame = traceback.tb_frame
    module = frame.f_globals.get("__name__", "unknown")
    return f"{module}:{frame.f_code.co_name}:{traceback.tb_lineno}"


def _json_value(value: object) -> object:
    if value is None or isinstance(value, bool | int | float | str):
        return value
    if isinstance(value, Mapping):
        mapping = cast(Mapping[object, object], value)
        return {str(key): _json_value(item) for key, item in mapping.items()}
    if isinstance(value, list | tuple):
        values = cast(Sequence[object], value)
        return [_json_value(item) for item in values]
    return type(value).__name__
