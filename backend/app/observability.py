"""Request-local dependency measurements shared by integrations and middleware."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from time import perf_counter
from collections.abc import Generator


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
