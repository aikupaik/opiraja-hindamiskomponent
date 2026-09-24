"""Structured production logging for the API process."""

import json
import logging
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from types import TracebackType
from typing import TypeAlias, cast

from app.observability import current_request_id

LOG_SCHEMA_VERSION = 1
TRUNCATION_MARKER = "...[TRUNCATED]"
VALID_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})
JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)
_COMPACT_JWT = re.compile(
    r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."
    r"[A-Za-z0-9_-]{10,}(?![A-Za-z0-9_-])"
)
_TOKEN_URL_VALUE = re.compile(
    r"(?i)([?&#][A-Za-z0-9_-]*(?:token|api[_-]?key)=)[^&\s\"'<>]+"
)
_SENSITIVE_KEY_PARTS = frozenset(
    {
        "authorization",
        "cookie",
        "password",
        "passwd",
        "secret",
        "token",
        "apikey",
        "credential",
    }
)
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
            "event": production_sanitizer().sanitize(str(event)),
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
            payload[key] = production_sanitizer().sanitize(value)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class ProductionSanitizer:
    """Redact secrets while preserving JSON-compatible value structure."""

    def __init__(self, secrets: Sequence[str] = ()) -> None:
        self._secrets = tuple(value for value in secrets if value)

    def sanitize(
        self,
        value: object,
        *,
        max_string_bytes: int = 32 * 1024,
        key: str | None = None,
    ) -> JsonValue:
        if key is not None and _is_sensitive_key(key):
            return "[REDACTED]"
        if value is None or isinstance(value, bool | int | float):
            return value
        if isinstance(value, str):
            redacted = value
            for secret in self._secrets:
                redacted = redacted.replace(secret, "[REDACTED]")
            redacted = _TOKEN_URL_VALUE.sub(r"\1[REDACTED]", redacted)
            redacted = _COMPACT_JWT.sub("[REDACTED]", redacted)
            return truncate_utf8(redacted, max_string_bytes)
        if isinstance(value, Mapping):
            mapping = cast(Mapping[object, object], value)
            return {
                str(child_key): self.sanitize(
                    child_value,
                    max_string_bytes=max_string_bytes,
                    key=str(child_key),
                )
                for child_key, child_value in mapping.items()
            }
        if isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            sequence = cast(Sequence[object], value)
            return [
                self.sanitize(item, max_string_bytes=max_string_bytes)
                for item in sequence
            ]
        return truncate_utf8(type(value).__name__, max_string_bytes)


_production_sanitizer = ProductionSanitizer()


def configure_production_sanitizer(secrets: Sequence[str]) -> ProductionSanitizer:
    """Replace the process sanitizer after settings have been validated."""

    global _production_sanitizer
    _production_sanitizer = ProductionSanitizer(secrets)
    return _production_sanitizer


def production_sanitizer() -> ProductionSanitizer:
    return _production_sanitizer


def truncate_utf8(value: str, maximum_bytes: int) -> str:
    """Limit text without splitting a UTF-8 code point."""

    encoded = value.encode("utf-8")
    if len(encoded) <= maximum_bytes:
        return value
    marker = TRUNCATION_MARKER.encode("utf-8")
    if maximum_bytes <= len(marker):
        return marker[:maximum_bytes].decode("utf-8", errors="ignore")
    prefix = encoded[: maximum_bytes - len(marker)].decode("utf-8", errors="ignore")
    return prefix + TRUNCATION_MARKER


def _is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
    compact = normalized.replace("_", "")
    return any(
        part in normalized.split("_") or part in compact
        for part in _SENSITIVE_KEY_PARTS
    )


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


def safe_exception_chain(
    error: BaseException, *, maximum_depth: int = 8
) -> list[JsonValue]:
    """Describe exception classes and code locations without exception text."""

    chain: list[JsonValue] = []
    current: BaseException | None = error
    seen: set[int] = set()
    while (
        current is not None
        and len(chain) < maximum_depth
        and id(current) not in seen
    ):
        seen.add(id(current))
        item: dict[str, JsonValue] = {"error_type": type(current).__name__}
        location = safe_exception_location(current)
        if location is not None:
            item["location"] = location
        chain.append(item)
        current = current.__cause__ or current.__context__
    return chain
