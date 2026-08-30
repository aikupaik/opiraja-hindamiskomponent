"""Bounded event-loop and state-integrity evidence for a performance run."""

import asyncio
import json
import math
from collections import Counter
from pathlib import Path

from app.domain.models import PlayerState, SessionStatus
from tests.fakes.assessment_repository import InMemoryAssessmentRepository

from .engine import DeterministicKstEngine


class EventLoopLagSampler:
    def __init__(self, *, interval_seconds: float = 1.0) -> None:
        self._interval_seconds = interval_seconds
        self._samples_ms: list[float] = []
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("event-loop sampler is already running")
        self._task = asyncio.create_task(self._sample())

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def summary(self) -> dict[str, float | int | None]:
        values = sorted(self._samples_ms)
        return {
            "sample_count": len(values),
            "p95_ms": _percentile(values, 0.95),
            "p99_ms": _percentile(values, 0.99),
            "max_ms": None if not values else values[-1],
        }

    async def _sample(self) -> None:
        loop = asyncio.get_running_loop()
        expected = loop.time() + self._interval_seconds
        while True:
            await asyncio.sleep(max(0.0, expected - loop.time()))
            observed = loop.time()
            self._samples_ms.append(max(0.0, (observed - expected) * 1000))
            expected += self._interval_seconds


def export_evidence(
    path: Path,
    *,
    run_id: str,
    workload: str,
    shape: str,
    repository: InMemoryAssessmentRepository,
    engine: DeterministicKstEngine,
    loop_lag: EventLoopLagSampler,
) -> None:
    sessions = repository.session_snapshot
    answers = repository.answer_snapshot
    yg_orders = repository.yg_order_snapshot
    status_counts = Counter(session.status.value for session in sessions.values())
    integrity_errors: list[str] = []
    history_submissions: list[object] = []

    for test_id, session in sessions.items():
        state = session.player_state
        if not isinstance(state, PlayerState):
            integrity_errors.append(f"legacy player state: {test_id}")
            continue
        submissions = [entry.submission_id for entry in state.answered_items]
        history_submissions.extend(submissions)
        if len(submissions) != len(set(submissions)):
            integrity_errors.append(f"duplicate transition: {test_id}")
        stored = [answer for answer in answers.values() if answer.test_id == test_id]
        if session.status is SessionStatus.COMPLETED and len(stored) != len(submissions):
            integrity_errors.append(f"completed answer count mismatch: {test_id}")

    if len(history_submissions) != len(set(history_submissions)):
        integrity_errors.append("submission appears in more than one session")
    for submission_id, answer in answers.items():
        session = sessions.get(answer.test_id)
        if session is None:
            integrity_errors.append(f"answer has no session: {submission_id}")
            continue
        state = session.player_state
        if not isinstance(state, PlayerState) or not any(
            entry.submission_id == submission_id and entry.item_id == answer.item_id
            for entry in state.answered_items
        ):
            integrity_errors.append(f"answer/history mismatch: {submission_id}")

    payload: dict[str, object] = {
        "schema_version": 1,
        "run_id": run_id,
        "workload": workload,
        "graph_shape": shape,
        "session_count": len(sessions),
        "session_status_counts": dict(sorted(status_counts.items())),
        "answer_count": len(answers),
        "unique_submission_count": len(answers),
        "yg_order_count": sum(len(values) for values in yg_orders.values()),
        "integrity_errors": integrity_errors,
        "repository_method_counts": dict(sorted(repository.method_counts.items())),
        "engine_call_counts": dict(sorted(engine.call_counts.items())),
        "event_loop_lag": loop_lag.summary(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    index = max(0, math.ceil(len(values) * fraction) - 1)
    return values[index]

