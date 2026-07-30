"""Bounded process-local diagnostics for authenticated experiments."""

import asyncio
from collections import deque
from collections.abc import AsyncGenerator, Generator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from time import monotonic
from typing import TypeAlias, cast

JsonValue: TypeAlias = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)

_SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "password",
    "secret",
    "token",
    "access_key",
    "admin_access_key",
    "apikey",
    "api_key",
    "supabase_service_key",
}


@dataclass(frozen=True, slots=True)
class DiagnosticEvent:
    sequence: int
    timestamp: str
    source: str
    level: str
    type: str
    request_id: str | None
    test_id: str | None
    payload: JsonValue

    def as_dict(self) -> dict[str, JsonValue]:
        return {
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "source": self.source,
            "level": self.level,
            "type": self.type,
            "request_id": self.request_id,
            "test_id": self.test_id,
            "payload": self.payload,
        }


@dataclass(frozen=True, slots=True)
class DiagnosticSnapshot:
    """Stable, non-persistent view of one experiment's retained events."""

    events: tuple[DiagnosticEvent, ...]
    truncated: bool
    maximum_events: int


@dataclass(slots=True)
class _Experiment:
    events: deque[DiagnosticEvent]
    subscribers: set[asyncio.Queue[DiagnosticEvent]]
    next_sequence: int
    last_activity: float


class DiagnosticHub:
    """A per-process ring buffer with replay and subscriber cleanup."""

    def __init__(
        self,
        *,
        max_events: int = 500,
        ttl_seconds: int = 3600,
        secrets: tuple[str, ...] = (),
    ) -> None:
        self.max_events = max_events
        self.ttl_seconds = ttl_seconds
        self._secrets = tuple(value for value in secrets if value)
        self._experiments: dict[str, _Experiment] = {}

    def emit(
        self,
        experiment_id: str,
        *,
        source: str,
        level: str,
        event_type: str,
        request_id: str | None,
        test_id: str | None,
        payload: object,
    ) -> DiagnosticEvent:
        now = monotonic()
        self.expire(now=now)
        experiment = self._experiments.get(experiment_id)
        if experiment is None:
            experiment = _Experiment(
                events=deque(maxlen=self.max_events),
                subscribers=set(),
                next_sequence=1,
                last_activity=now,
            )
            self._experiments[experiment_id] = experiment
        event = DiagnosticEvent(
            sequence=experiment.next_sequence,
            timestamp=datetime.now(UTC).isoformat(),
            source=source,
            level=level,
            type=event_type,
            request_id=request_id,
            test_id=test_id,
            payload=self._redact(payload),
        )
        experiment.next_sequence += 1
        experiment.last_activity = now
        experiment.events.append(event)
        for queue in tuple(experiment.subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                experiment.subscribers.discard(queue)
        return event

    async def stream(
        self, experiment_id: str, *, after_sequence: int = 0
    ) -> AsyncGenerator[str]:
        self.expire()
        experiment = self._experiments.get(experiment_id)
        if experiment is None:
            experiment = _Experiment(
                events=deque(maxlen=self.max_events),
                subscribers=set(),
                next_sequence=1,
                last_activity=monotonic(),
            )
            self._experiments[experiment_id] = experiment
        queue: asyncio.Queue[DiagnosticEvent] = asyncio.Queue(maxsize=self.max_events)
        experiment.subscribers.add(queue)
        experiment.last_activity = monotonic()
        try:
            for event in tuple(experiment.events):
                if event.sequence > after_sequence:
                    yield self._serialize(event)
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except TimeoutError:
                    experiment.last_activity = monotonic()
                    yield ": keep-alive\n\n"
                    continue
                experiment.last_activity = monotonic()
                yield self._serialize(event)
        finally:
            experiment.subscribers.discard(queue)

    def expire(self, *, now: float | None = None) -> None:
        current = monotonic() if now is None else now
        expired = [
            identifier
            for identifier, experiment in self._experiments.items()
            if not experiment.subscribers
            and current - experiment.last_activity >= self.ttl_seconds
        ]
        for identifier in expired:
            del self._experiments[identifier]

    def subscriber_count(self, experiment_id: str) -> int:
        experiment = self._experiments.get(experiment_id)
        return 0 if experiment is None else len(experiment.subscribers)

    def events_after(
        self, experiment_id: str, *, after_sequence: int = 0
    ) -> tuple[DiagnosticEvent, ...]:
        """Return a stable replay snapshot for tests and non-streaming callers."""

        self.expire()
        experiment = self._experiments.get(experiment_id)
        if experiment is None:
            return ()
        experiment.last_activity = monotonic()
        return tuple(
            event for event in experiment.events if event.sequence > after_sequence
        )

    def snapshot(self, experiment_id: str) -> DiagnosticSnapshot | None:
        """Return one stable ring-buffer snapshot without creating an experiment."""

        self.expire()
        experiment = self._experiments.get(experiment_id)
        if experiment is None:
            return None
        experiment.last_activity = monotonic()
        events = tuple(experiment.events)
        return DiagnosticSnapshot(
            events=events,
            truncated=bool(events and events[0].sequence > 1),
            maximum_events=self.max_events,
        )

    @staticmethod
    def _serialize(event: DiagnosticEvent) -> str:
        data = json.dumps(event.as_dict(), ensure_ascii=False, separators=(",", ":"))
        return f"id: {event.sequence}\nevent: diagnostic\ndata: {data}\n\n"

    def _redact(self, value: object, *, key: str | None = None) -> JsonValue:
        if key is not None and key.casefold() in _SENSITIVE_KEYS:
            return "[REDACTED]"
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            result = value
            for secret in self._secrets:
                result = result.replace(secret, "[REDACTED]")
            return result
        if isinstance(value, Mapping):
            mapping = cast(Mapping[object, object], value)
            return {
                str(child_key): self._redact(child_value, key=str(child_key))
                for child_key, child_value in mapping.items()
            }
        if isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            sequence = cast(Sequence[object], value)
            return [self._redact(child) for child in sequence]
        return str(value)


@dataclass(frozen=True, slots=True)
class DiagnosticContext:
    hub: DiagnosticHub
    experiment_id: str
    request_id: str | None
    test_id: str | None


_context: ContextVar[DiagnosticContext | None] = ContextVar(
    "admin_diagnostic_context", default=None
)


@contextmanager
def diagnostic_context(
    hub: DiagnosticHub,
    experiment_id: str,
    *,
    request_id: str | None = None,
    test_id: str | None = None,
) -> Generator[None]:
    token = _context.set(
        DiagnosticContext(
            hub=hub,
            experiment_id=experiment_id,
            request_id=request_id,
            test_id=test_id,
        )
    )
    try:
        yield
    finally:
        _context.reset(token)


def emit_diagnostic(
    *,
    source: str,
    level: str,
    event_type: str,
    payload: object,
    request_id: str | None = None,
    test_id: str | None = None,
) -> DiagnosticEvent | None:
    context = _context.get()
    if context is None:
        return None
    return context.hub.emit(
        context.experiment_id,
        source=source,
        level=level,
        event_type=event_type,
        request_id=request_id or context.request_id,
        test_id=test_id or context.test_id,
        payload=payload,
    )
