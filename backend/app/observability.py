"""Request-local observability context shared by integrations and middleware."""

from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from time import perf_counter


@dataclass(slots=True)
class DependencyMetrics:
    """Mutable request-local counters accumulated by dependency adapters."""

    supabase_seconds: float = 0.0
    supabase_execute_count: int = 0
    r_seconds: float = 0.0
    r_request_count: int = 0


_metrics: ContextVar[DependencyMetrics | None] = ContextVar(
    "dependency_metrics", default=None
)
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def set_request_id(request_id: str) -> Token[str | None]:
    """Bind a correlation ID to the current asynchronous context."""

    return _request_id.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    """Restore the correlation ID context that preceded ``set_request_id``."""

    _request_id.reset(token)


def current_request_id() -> str | None:
    """Return the correlation ID bound to the current asynchronous context."""

    return _request_id.get()


@contextmanager
def collect_dependency_metrics() -> Generator[DependencyMetrics]:
    """Bind a fresh metrics object for the current async context."""

    metrics = DependencyMetrics()
    token = _metrics.set(metrics)
    try:
        yield metrics
    finally:
        _metrics.reset(token)


def record_supabase_execute(started_at: float) -> None:
    """Record one completed or failed Supabase execute attempt."""

    metrics = _metrics.get()
    if metrics is not None:
        metrics.supabase_execute_count += 1
        metrics.supabase_seconds += perf_counter() - started_at


def record_r_request(started_at: float) -> None:
    """Record one completed or failed R HTTP request attempt."""

    metrics = _metrics.get()
    if metrics is not None:
        metrics.r_request_count += 1
        metrics.r_seconds += perf_counter() - started_at
