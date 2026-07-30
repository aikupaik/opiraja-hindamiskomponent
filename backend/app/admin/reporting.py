"""Ephemeral research and performance reports compiled from diagnostics."""

from collections import Counter, defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
from statistics import mean, median
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue as PydanticJsonValue

from .diagnostics import DiagnosticEvent, DiagnosticSnapshot, JsonValue

REPORT_SCHEMA_VERSION = "1.0"
API_SLOW_MS = 1_000.0
DEPENDENCY_SLOW_MS = 500.0
PREPARATION_SLOW_MS = 10_000.0


class ReportModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReportRelation(ReportModel):
    prerequisite: str
    dependent: str


class ReliabilityConfiguration(ReportModel):
    minimum: int | None = None
    multiplier: float | None = None
    maximum: int | None = None
    derived_floor: int | None = None


class SafetyConfiguration(ReportModel):
    minimum_above_floor: int | None = None
    node_multiplier: float | None = None
    derived_cap: int | None = None


class ResearchMetadata(ReportModel):
    nodes: tuple[str, ...]
    relations: tuple[ReportRelation, ...]
    configuration_hash: str | None
    stop_confidence: float | None
    feedback_credible_mass: float | None
    reliability_floor: ReliabilityConfiguration
    safety_cap: SafetyConfiguration
    knowledge_state_count: int
    initial_prior: tuple[float, ...]


class ProbabilityState(ReportModel):
    rank: int
    nodes: tuple[str, ...]
    probability: float


class AdaptiveStep(ReportModel):
    step: int
    timestamp: datetime
    candidate_id: str | None
    node: str | None
    beta: float | None
    eta: float | None
    response_correct: bool | None
    approximate_response_interval_ms: float | None
    system_processing_ms: float | None
    posterior_before: tuple[float, ...]
    posterior_after: tuple[float, ...]
    highest_probability_states: tuple[ProbabilityState, ...]
    maximum_state_confidence: float | None
    shannon_entropy_bits: float | None
    normalized_entropy: float | None
    total_variation_movement: float | None
    selected_next_candidate_id: str | None
    decision: str
    r_processing_ms: float | None


class NodeAccuracy(ReportModel):
    node: str
    correct: int
    responses: int
    accuracy: float


class FinalProfileReport(ReportModel):
    mastered: tuple[str, ...]
    ready_to_learn: tuple[str, ...]
    uncertain_ahead: tuple[str, ...]
    uncertain_prerequisite: tuple[str, ...]
    not_yet: tuple[str, ...]
    summary: str | None
    stop_reason: str | None
    best_state_confidence: float | None
    credible_mass: float | None
    credible_state_count: int | None
    confidence_limited: bool | None


class ResearchSummary(ReportModel):
    response_count: int
    correct_count: int
    overall_accuracy: float | None
    per_node_accuracy: tuple[NodeAccuracy, ...]
    node_path: tuple[str, ...]
    final_posterior: tuple[float, ...]
    stopping_reason: str | None
    confidence_limited: bool | None
    credible_mass: float | None
    credible_state_count: int | None
    final_profile: FinalProfileReport | None


class ExactRCall(ReportModel):
    sequence: int
    request_id: str | None
    operation: str
    started_at: datetime
    completed_at: datetime | None
    duration_ms: float | None
    outcome: str
    status: int | None
    input: PydanticJsonValue
    output: PydanticJsonValue


class ResearchReport(ReportModel):
    interpretation: str
    metadata: ResearchMetadata
    operations: tuple[ExactRCall, ...]
    adaptive_steps: tuple[AdaptiveStep, ...]
    summary: ResearchSummary


class TimelineStage(ReportModel):
    stage: str
    started_at: datetime
    ended_at: datetime | None
    duration_ms: float | None
    outcome: str


class TrafficSummary(ReportModel):
    method: str
    endpoint: str
    status: int
    outcome: str
    request_count: int
    approximate_request_bytes: int
    approximate_response_bytes: int


class LatencySummary(ReportModel):
    count: int
    total_ms: float
    mean_ms: float | None
    median_ms: float | None
    maximum_ms: float | None


class BackendBreakdown(ReportModel):
    total_api_ms: float
    r_ms: float
    supabase_ms: float
    residual_application_ms: float


class DependencySummary(ReportModel):
    operation: str
    count: int
    total_ms: float
    mean_ms: float
    maximum_ms: float


class SlowOperation(ReportModel):
    category: Literal["api", "r", "supabase"]
    operation: str
    duration_ms: float
    request_id: str | None
    sequence: int | None
    diagnostic_flag: bool


class DiagnosticThresholds(ReportModel):
    api_request_ms: float = API_SLOW_MS
    dependency_call_ms: float = DEPENDENCY_SLOW_MS
    preparation_ms: float = PREPARATION_SLOW_MS
    interpretation: str = (
        "Initial diagnostic review flags only; these thresholds are not production SLOs."
    )


class DeveloperReport(ReportModel):
    timeline: tuple[TimelineStage, ...]
    last_successful_stage: str
    last_recorded_event: str
    traffic: tuple[TrafficSummary, ...]
    api_latency: LatencySummary
    backend_time: BackendBreakdown
    r_by_operation: tuple[DependencySummary, ...]
    supabase_by_operation: tuple[DependencySummary, ...]
    slowest_api_requests: tuple[SlowOperation, ...]
    slowest_r_calls: tuple[SlowOperation, ...]
    slowest_supabase_operations: tuple[SlowOperation, ...]
    thresholds: DiagnosticThresholds


class ExperimentReport(ReportModel):
    schema_version: Literal["1.0"] = REPORT_SCHEMA_VERSION
    generated_at: datetime
    experiment_id: str
    test_id: str | None
    completion_state: Literal["completed", "partial"]
    run_status: str
    event_count: int
    buffer_truncated: bool
    data_quality_warnings: tuple[str, ...]
    research: ResearchReport
    developer: DeveloperReport
    exact_r_calls: tuple[ExactRCall, ...]


@dataclass(frozen=True, slots=True)
class _RPair:
    request: DiagnosticEvent
    response: DiagnosticEvent | None
    failure: DiagnosticEvent | None


@dataclass(frozen=True, slots=True)
class _ApiExchange:
    request_id: str
    request: DiagnosticEvent | None
    response: DiagnosticEvent | None
    completed: DiagnosticEvent | None


@dataclass(frozen=True, slots=True)
class _DependencyCall:
    operation: str
    duration_ms: float
    request_id: str | None
    sequence: int


_R_ALLOWED_KEYS = frozenset(
    {
        "nodes",
        "relations",
        "from",
        "to",
        "cached_knowledge_states",
        "model",
        "schema_version",
        "method",
        "knowledge_states",
        "matrix",
        "uniform_prior",
        "configuration",
        "configuration_hash",
        "stop_confidence",
        "feedback_credible_mass",
        "reliability_floor",
        "safety_cap",
        "minimum",
        "multiplier",
        "maximum",
        "minimum_above_floor",
        "node_multiplier",
        "posterior",
        "candidates",
        "candidate_id",
        "node",
        "beta",
        "eta",
        "administered",
        "response_correct",
        "response_count",
        "remaining_candidates",
        "status",
        "next_candidate",
        "profile",
        "mastered",
        "ready_to_learn",
        "uncertain_ahead",
        "uncertain_prerequisite",
        "not_yet",
        "summary",
        "stop_reason",
        "best_state_confidence",
        "credible_mass",
        "credible_state_count",
        "confidence_limited",
    }
)


def build_experiment_report(
    experiment_id: str,
    snapshot: DiagnosticSnapshot,
    *,
    generated_at: datetime | None = None,
) -> ExperimentReport:
    """Compile a privacy-allowlisted report from one immutable event snapshot."""

    events = tuple(sorted(snapshot.events, key=lambda event: event.sequence))
    warnings: list[str] = []
    if snapshot.truncated:
        warnings.append(
            f"Diagnostic ring buffer was truncated before sequence {events[0].sequence}."
        )

    r_pairs = _pair_r_calls(events, warnings)
    exact_r_calls = tuple(_exact_r_call(pair) for pair in r_pairs)
    api_exchanges = _pair_api_exchanges(events, warnings)
    model = _normalized_model(r_pairs)
    metadata = _research_metadata(model, r_pairs)
    steps = _adaptive_steps(r_pairs, api_exchanges, model, warnings)
    summary = _research_summary(steps, r_pairs)
    completed = summary.final_profile is not None
    run_status = _run_status(completed, api_exchanges)
    if not completed:
        warnings.append(
            "Run is incomplete; the report identifies the last observed stage and does not infer a root cause."
        )
    _diagnostic_warnings(events, warnings)

    developer = _developer_report(events, api_exchanges, exact_r_calls)
    test_id = next(
        (event.test_id for event in reversed(events) if event.test_id is not None),
        None,
    )
    unique_warnings = tuple(dict.fromkeys(warnings))
    research = ResearchReport(
        interpretation=(
            "This single-session report is descriptive evidence. Calibration, "
            "reliability, validity, fairness, and population-level psychometrics "
            "require aggregation of versioned JSON exports from multiple runs."
        ),
        metadata=metadata,
        operations=exact_r_calls,
        adaptive_steps=steps,
        summary=summary,
    )
    return ExperimentReport(
        generated_at=generated_at or datetime.now(UTC),
        experiment_id=experiment_id,
        test_id=test_id,
        completion_state="completed" if completed else "partial",
        run_status=run_status,
        event_count=len(events),
        buffer_truncated=snapshot.truncated,
        data_quality_warnings=unique_warnings,
        research=research,
        developer=developer,
        exact_r_calls=exact_r_calls,
    )


def _pair_r_calls(
    events: Sequence[DiagnosticEvent], warnings: list[str]
) -> tuple[_RPair, ...]:
    pending: dict[str, deque[DiagnosticEvent]] = defaultdict(deque)
    pairs: list[_RPair] = []
    for event in events:
        key = event.request_id or "__uncorrelated__"
        if event.type == "r_request":
            pending[key].append(event)
        elif event.type in {"r_response", "r_request_failed"}:
            if pending[key]:
                request = pending[key].popleft()
                pairs.append(
                    _RPair(
                        request=request,
                        response=event if event.type == "r_response" else None,
                        failure=(
                            event if event.type == "r_request_failed" else None
                        ),
                    )
                )
            elif (
                event.type == "r_request_failed"
                and pairs
                and pairs[-1].request.request_id == event.request_id
                and pairs[-1].response is not None
            ):
                # HTTP failures emit a timed dependency response followed by a
                # diagnostic failure marker. The response already closes the call.
                continue
            else:
                warnings.append(
                    f"Unpaired {event.type} event at sequence {event.sequence}."
                )
    for queue in pending.values():
        for request in queue:
            pairs.append(_RPair(request=request, response=None, failure=None))
            warnings.append(
                f"R request at sequence {request.sequence} has no response or failure event."
            )
    return tuple(sorted(pairs, key=lambda pair: pair.request.sequence))


def _pair_api_exchanges(
    events: Sequence[DiagnosticEvent], warnings: list[str]
) -> tuple[_ApiExchange, ...]:
    grouped: dict[str, dict[str, DiagnosticEvent]] = defaultdict(dict)
    for event in events:
        if event.request_id is None:
            continue
        if event.type in {"request", "response", "request_completed"}:
            grouped[event.request_id][event.type] = event
    exchanges: list[_ApiExchange] = []
    for request_id, values in grouped.items():
        exchange = _ApiExchange(
            request_id=request_id,
            request=values.get("request"),
            response=values.get("response"),
            completed=values.get("request_completed"),
        )
        exchanges.append(exchange)
        missing = [
            name
            for name, event in (
                ("request", exchange.request),
                ("response", exchange.response),
                ("request_completed", exchange.completed),
            )
            if event is None
        ]
        if missing:
            warnings.append(
                f"API request {request_id} is missing event pair members: {', '.join(missing)}."
            )
    return tuple(
        sorted(
            exchanges,
            key=lambda value: min(
                event.sequence
                for event in (value.request, value.response, value.completed)
                if event is not None
            ),
        )
    )


def _exact_r_call(pair: _RPair) -> ExactRCall:
    request_payload = _mapping(pair.request.payload)
    path = _string(request_payload, "path")
    operation = _operation_from_path(path)
    response_event = pair.response or pair.failure
    response_payload = (
        None if response_event is None else _mapping(response_event.payload)
    )
    duration_ms = _number(response_payload, "duration_ms")
    status_value = _integer(response_payload, "status")
    if pair.response is not None:
        outcome = "success" if status_value is None or status_value < 400 else "failed"
    elif pair.failure is not None:
        outcome = "failed"
    else:
        outcome = "missing_response"
    return ExactRCall(
        sequence=pair.request.sequence,
        request_id=pair.request.request_id,
        operation=operation,
        started_at=_timestamp(pair.request.timestamp),
        completed_at=(
            None
            if response_event is None
            else _timestamp(response_event.timestamp)
        ),
        duration_ms=duration_ms,
        outcome=outcome,
        status=status_value,
        input=_sanitize_r_value(
            None if request_payload is None else request_payload.get("body")
        ),
        output=_sanitize_r_value(
            None if response_payload is None else response_payload.get("body")
        ),
    )


def _normalized_model(r_pairs: Sequence[_RPair]) -> Mapping[str, JsonValue] | None:
    for pair in r_pairs:
        if _operation(pair.request) != "model" or pair.response is None:
            continue
        payload = _mapping(pair.response.payload)
        body = _mapping(None if payload is None else payload.get("body"))
        model = _mapping(None if body is None else body.get("model"))
        if model is not None:
            return model
    for pair in r_pairs:
        request = _mapping(pair.request.payload)
        body = _mapping(None if request is None else request.get("body"))
        model = _mapping(None if body is None else body.get("model"))
        if model is not None:
            return model
    return None


def _research_metadata(
    model: Mapping[str, JsonValue] | None, r_pairs: Sequence[_RPair]
) -> ResearchMetadata:
    model_request: Mapping[str, JsonValue] | None = None
    for pair in r_pairs:
        if _operation(pair.request) != "model":
            continue
        request_payload = _mapping(pair.request.payload)
        model_request = _mapping(
            None if request_payload is None else request_payload.get("body")
        )
        break
    nodes = _strings(
        None
        if model is None
        else model.get("nodes")
    ) or _strings(None if model_request is None else model_request.get("nodes"))
    relation_values = _sequence(
        None if model_request is None else model_request.get("relations")
    )
    relations: list[ReportRelation] = []
    for value in relation_values:
        relation = _mapping(value)
        prerequisite = _string(relation, "from")
        dependent = _string(relation, "to")
        if prerequisite is not None and dependent is not None:
            relations.append(
                ReportRelation(prerequisite=prerequisite, dependent=dependent)
            )
    configuration = _mapping(
        None if model is None else model.get("configuration")
    )
    reliability = _mapping(
        None if configuration is None else configuration.get("reliability_floor")
    )
    safety = _mapping(
        None if configuration is None else configuration.get("safety_cap")
    )
    states = _sequence(None if model is None else model.get("knowledge_states"))
    return ResearchMetadata(
        nodes=nodes,
        relations=tuple(relations),
        configuration_hash=_string(model, "configuration_hash"),
        stop_confidence=_number(configuration, "stop_confidence"),
        feedback_credible_mass=_number(configuration, "feedback_credible_mass"),
        reliability_floor=ReliabilityConfiguration(
            minimum=_integer(reliability, "minimum"),
            multiplier=_number(reliability, "multiplier"),
            maximum=_integer(reliability, "maximum"),
            derived_floor=_integer(model, "reliability_floor"),
        ),
        safety_cap=SafetyConfiguration(
            minimum_above_floor=_integer(safety, "minimum_above_floor"),
            node_multiplier=_number(safety, "node_multiplier"),
            derived_cap=_integer(model, "safety_cap"),
        ),
        knowledge_state_count=len(states),
        initial_prior=_numbers(None if model is None else model.get("uniform_prior")),
    )


def _adaptive_steps(
    r_pairs: Sequence[_RPair],
    exchanges: Sequence[_ApiExchange],
    model: Mapping[str, JsonValue] | None,
    warnings: list[str],
) -> tuple[AdaptiveStep, ...]:
    knowledge_states = tuple(
        _strings(value)
        for value in _sequence(
            None if model is None else model.get("knowledge_states")
        )
    )
    completion_by_request = {
        exchange.request_id: _number(
            _mapping(
                None
                if exchange.completed is None
                else exchange.completed.payload
            ),
            "total_ms",
        )
        for exchange in exchanges
    }
    answer_start_by_request = {
        exchange.request_id: (
            None
            if exchange.request is None
            else _timestamp(exchange.request.timestamp)
        )
        for exchange in exchanges
        if _is_answer_exchange(exchange)
    }
    selection_times: list[datetime] = []
    for pair in r_pairs:
        if _operation(pair.request) not in {"select", "advance"}:
            continue
        selected = _selected_candidate(pair)
        if selected is not None and pair.response is not None:
            selection_times.append(_timestamp(pair.response.timestamp))

    steps: list[AdaptiveStep] = []
    for pair in r_pairs:
        if _operation(pair.request) != "advance":
            continue
        request_payload = _mapping(pair.request.payload)
        request_body = _mapping(
            None if request_payload is None else request_payload.get("body")
        )
        administered = _mapping(
            None if request_body is None else request_body.get("administered")
        )
        response_payload = (
            None if pair.response is None else _mapping(pair.response.payload)
        )
        response_body = _mapping(
            None if response_payload is None else response_payload.get("body")
        )
        before = _numbers(
            None if request_body is None else request_body.get("posterior")
        )
        after = _numbers(
            None if response_body is None else response_body.get("posterior")
        )
        if not after:
            warnings.append(
                f"Adaptive step at sequence {pair.request.sequence} has no valid posterior response."
            )
        response_count = _integer(request_body, "response_count")
        step_number = response_count or len(steps) + 1
        answer_started = answer_start_by_request.get(pair.request.request_id or "")
        selected_at = (
            selection_times[step_number - 1]
            if 0 < step_number <= len(selection_times)
            else None
        )
        response_interval = (
            None
            if answer_started is None or selected_at is None
            else max(0.0, (answer_started - selected_at).total_seconds() * 1000)
        )
        selected_next = _selected_candidate(pair)
        status = _string(response_body, "status")
        decision = (
            "completed"
            if status == "completed"
            else (
                f"selected {selected_next}"
                if selected_next is not None
                else "no recorded decision"
            )
        )
        entropy = _entropy(after)
        normalized_entropy = (
            None
            if entropy is None
            else (0.0 if len(after) <= 1 else entropy / math.log2(len(after)))
        )
        steps.append(
            AdaptiveStep(
                step=step_number,
                timestamp=_timestamp(pair.request.timestamp),
                candidate_id=_string(administered, "candidate_id"),
                node=_string(administered, "node"),
                beta=_number(administered, "beta"),
                eta=_number(administered, "eta"),
                response_correct=_boolean(request_body, "response_correct"),
                approximate_response_interval_ms=_rounded(response_interval),
                system_processing_ms=_rounded(
                    completion_by_request.get(pair.request.request_id or "")
                ),
                posterior_before=before,
                posterior_after=after,
                highest_probability_states=_highest_states(
                    after, knowledge_states
                ),
                maximum_state_confidence=max(after) if after else None,
                shannon_entropy_bits=_rounded(entropy),
                normalized_entropy=_rounded(normalized_entropy),
                total_variation_movement=_rounded(
                    _total_variation(before, after)
                ),
                selected_next_candidate_id=selected_next,
                decision=decision,
                r_processing_ms=_number(response_payload, "duration_ms"),
            )
        )
    return tuple(steps)


def _research_summary(
    steps: Sequence[AdaptiveStep], r_pairs: Sequence[_RPair]
) -> ResearchSummary:
    correct = sum(step.response_correct is True for step in steps)
    counts: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for step in steps:
        if step.node is None or step.response_correct is None:
            continue
        counts[step.node][1] += 1
        counts[step.node][0] += int(step.response_correct)
    per_node = tuple(
        NodeAccuracy(
            node=node,
            correct=values[0],
            responses=values[1],
            accuracy=values[0] / values[1],
        )
        for node, values in counts.items()
    )
    profile_mapping: Mapping[str, JsonValue] | None = None
    final_posterior = steps[-1].posterior_after if steps else ()
    for pair in reversed(r_pairs):
        if _operation(pair.request) != "advance" or pair.response is None:
            continue
        response_payload = _mapping(pair.response.payload)
        body = _mapping(
            None if response_payload is None else response_payload.get("body")
        )
        profile_mapping = _mapping(None if body is None else body.get("profile"))
        if profile_mapping is not None and body is not None:
            final_posterior = _numbers(body.get("posterior"))
            break
    profile = (
        None
        if profile_mapping is None
        else FinalProfileReport(
            mastered=_strings(profile_mapping.get("mastered")),
            ready_to_learn=_strings(profile_mapping.get("ready_to_learn")),
            uncertain_ahead=_strings(profile_mapping.get("uncertain_ahead")),
            uncertain_prerequisite=_strings(
                profile_mapping.get("uncertain_prerequisite")
            ),
            not_yet=_strings(profile_mapping.get("not_yet")),
            summary=_string(profile_mapping, "summary"),
            stop_reason=_string(profile_mapping, "stop_reason"),
            best_state_confidence=_number(
                profile_mapping, "best_state_confidence"
            ),
            credible_mass=_number(profile_mapping, "credible_mass"),
            credible_state_count=_integer(
                profile_mapping, "credible_state_count"
            ),
            confidence_limited=_boolean(
                profile_mapping, "confidence_limited"
            ),
        )
    )
    return ResearchSummary(
        response_count=len(steps),
        correct_count=correct,
        overall_accuracy=None if not steps else correct / len(steps),
        per_node_accuracy=per_node,
        node_path=tuple(step.node for step in steps if step.node is not None),
        final_posterior=final_posterior,
        stopping_reason=None if profile is None else profile.stop_reason,
        confidence_limited=None if profile is None else profile.confidence_limited,
        credible_mass=None if profile is None else profile.credible_mass,
        credible_state_count=(
            None if profile is None else profile.credible_state_count
        ),
        final_profile=profile,
    )


def _developer_report(
    events: Sequence[DiagnosticEvent],
    exchanges: Sequence[_ApiExchange],
    r_calls: Sequence[ExactRCall],
) -> DeveloperReport:
    traffic_counter: Counter[tuple[str, str, int, str]] = Counter()
    traffic_bytes: dict[tuple[str, str, int, str], list[int]] = defaultdict(
        lambda: [0, 0]
    )
    api_durations: list[float] = []
    total_r = 0.0
    total_supabase = 0.0
    total_api = 0.0
    api_slow: list[SlowOperation] = []
    for exchange in exchanges:
        request_payload = _mapping(
            None if exchange.request is None else exchange.request.payload
        )
        response_payload = _mapping(
            None if exchange.response is None else exchange.response.payload
        )
        completed_payload = _mapping(
            None if exchange.completed is None else exchange.completed.payload
        )
        method = _string(completed_payload, "method") or _string(
            request_payload, "method"
        ) or "UNKNOWN"
        endpoint = _string(completed_payload, "path") or _string(
            request_payload, "path"
        ) or "unknown"
        status = _integer(completed_payload, "status") or _integer(
            response_payload, "status"
        ) or 0
        outcome = _string(completed_payload, "outcome") or "unknown"
        key = (method, endpoint, status, outcome)
        traffic_counter[key] += 1
        traffic_bytes[key][0] += _json_bytes(
            None if request_payload is None else request_payload.get("body")
        )
        traffic_bytes[key][1] += _json_bytes(
            None if response_payload is None else response_payload.get("body")
        )
        duration = _number(completed_payload, "total_ms")
        if duration is not None:
            api_durations.append(duration)
            total_api += duration
            total_r += _number(completed_payload, "r_ms") or 0.0
            total_supabase += _number(completed_payload, "supabase_ms") or 0.0
            api_slow.append(
                SlowOperation(
                    category="api",
                    operation=f"{method} {endpoint}",
                    duration_ms=duration,
                    request_id=exchange.request_id,
                    sequence=(
                        None
                        if exchange.completed is None
                        else exchange.completed.sequence
                    ),
                    diagnostic_flag=duration >= API_SLOW_MS,
                )
            )
    traffic = tuple(
        TrafficSummary(
            method=key[0],
            endpoint=key[1],
            status=key[2],
            outcome=key[3],
            request_count=count,
            approximate_request_bytes=traffic_bytes[key][0],
            approximate_response_bytes=traffic_bytes[key][1],
        )
        for key, count in sorted(traffic_counter.items())
    )
    supabase_calls = tuple(_supabase_calls(events))
    r_dependencies = tuple(
        _DependencyCall(
            operation=call.operation,
            duration_ms=call.duration_ms,
            request_id=call.request_id,
            sequence=call.sequence,
        )
        for call in r_calls
        if call.duration_ms is not None
    )
    timeline = _timeline(exchanges)
    successful_stages = [
        stage.stage for stage in timeline if stage.outcome not in {"failed", "unknown"}
    ]
    last_event = (
        "No retained event"
        if not events
        else (
            f"sequence {events[-1].sequence}: {events[-1].source}/"
            f"{events[-1].type} at {events[-1].timestamp}"
        )
    )
    return DeveloperReport(
        timeline=timeline,
        last_successful_stage=(
            successful_stages[-1] if successful_stages else "none observed"
        ),
        last_recorded_event=last_event,
        traffic=traffic,
        api_latency=_latency_summary(api_durations),
        backend_time=BackendBreakdown(
            total_api_ms=round(total_api, 3),
            r_ms=round(total_r, 3),
            supabase_ms=round(total_supabase, 3),
            residual_application_ms=round(
                max(0.0, total_api - total_r - total_supabase), 3
            ),
        ),
        r_by_operation=_dependency_summaries(r_dependencies),
        supabase_by_operation=_dependency_summaries(supabase_calls),
        slowest_api_requests=tuple(
            sorted(api_slow, key=lambda value: value.duration_ms, reverse=True)[:5]
        ),
        slowest_r_calls=_slow_dependencies("r", r_dependencies),
        slowest_supabase_operations=_slow_dependencies(
            "supabase", supabase_calls
        ),
        thresholds=DiagnosticThresholds(),
    )


def _timeline(exchanges: Sequence[_ApiExchange]) -> tuple[TimelineStage, ...]:
    observed: list[tuple[str, datetime, datetime | None, str]] = []
    for exchange in exchanges:
        request = exchange.request
        if request is None:
            continue
        payload = _mapping(request.payload)
        path = _string(payload, "path") or ""
        response_payload = _mapping(
            None if exchange.response is None else exchange.response.payload
        )
        response_body = _mapping(
            None if response_payload is None else response_payload.get("body")
        )
        status = _integer(response_payload, "status") or 0
        started = _timestamp(request.timestamp)
        ended = (
            None
            if exchange.completed is None
            else _timestamp(exchange.completed.timestamp)
        )
        if path == "/api/v1/tests":
            stage = "creation"
        elif path.endswith("/start"):
            stage = (
                "active assessment"
                if _string(response_body, "status") == "active"
                else "preparation / polling"
            )
        elif path.endswith("/answers"):
            stage = (
                "completion"
                if _string(response_body, "status") == "completed"
                else "active assessment"
            )
        else:
            continue
        observed.append(
            (
                stage,
                started,
                ended,
                "failed" if status >= 400 else "observed",
            )
        )
    stages: list[TimelineStage] = []
    for stage_name in (
        "creation",
        "preparation / polling",
        "active assessment",
        "completion",
    ):
        values = [value for value in observed if value[0] == stage_name]
        if not values:
            continue
        started = min(value[1] for value in values)
        ends = [value[2] for value in values if value[2] is not None]
        ended = max(ends) if ends else None
        stages.append(
            TimelineStage(
                stage=stage_name,
                started_at=started,
                ended_at=ended,
                duration_ms=(
                    None
                    if ended is None
                    else round((ended - started).total_seconds() * 1000, 3)
                ),
                outcome=(
                    "failed"
                    if any(value[3] == "failed" for value in values)
                    else "observed"
                ),
            )
        )
    return tuple(stages)


def _supabase_calls(events: Iterable[DiagnosticEvent]) -> Iterable[_DependencyCall]:
    for event in events:
        if event.type != "supabase_operation":
            continue
        payload = _mapping(event.payload)
        duration = _number(payload, "duration_ms")
        if duration is None:
            continue
        yield _DependencyCall(
            operation=_string(payload, "operation") or "unknown",
            duration_ms=duration,
            request_id=event.request_id,
            sequence=event.sequence,
        )


def _dependency_summaries(
    calls: Sequence[_DependencyCall],
) -> tuple[DependencySummary, ...]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for call in calls:
        grouped[call.operation].append(call.duration_ms)
    return tuple(
        DependencySummary(
            operation=operation,
            count=len(values),
            total_ms=round(sum(values), 3),
            mean_ms=round(mean(values), 3),
            maximum_ms=round(max(values), 3),
        )
        for operation, values in sorted(grouped.items())
    )


def _slow_dependencies(
    category: Literal["r", "supabase"], calls: Sequence[_DependencyCall]
) -> tuple[SlowOperation, ...]:
    return tuple(
        SlowOperation(
            category=category,
            operation=call.operation,
            duration_ms=call.duration_ms,
            request_id=call.request_id,
            sequence=call.sequence,
            diagnostic_flag=call.duration_ms >= DEPENDENCY_SLOW_MS,
        )
        for call in sorted(calls, key=lambda value: value.duration_ms, reverse=True)[
            :5
        ]
    )


def _latency_summary(values: Sequence[float]) -> LatencySummary:
    return LatencySummary(
        count=len(values),
        total_ms=round(sum(values), 3),
        mean_ms=None if not values else round(mean(values), 3),
        median_ms=None if not values else round(median(values), 3),
        maximum_ms=None if not values else round(max(values), 3),
    )


def _diagnostic_warnings(
    events: Sequence[DiagnosticEvent], warnings: list[str]
) -> None:
    for event in events:
        if event.level != "warning" and event.type not in {
            "r_response_contract_failure",
            "item_inventory_exhausted",
        }:
            continue
        warnings.append(
            f"Diagnostic warning at sequence {event.sequence}: {event.type}."
        )
    preparation = [
        event
        for event in events
        if event.type == "request_completed"
        and (_string(_mapping(event.payload), "path") or "").endswith("/start")
    ]
    if len(preparation) > 1:
        warnings.append(
            f"Preparation endpoint was polled {len(preparation)} times; retries/polls are included in API traffic totals."
        )
    preparation_request_ids = {
        event.request_id
        for event in events
        if event.type == "request"
        and (_string(_mapping(event.payload), "path") or "").endswith("/start")
        and event.request_id is not None
    }
    preparation_events = [
        event
        for event in events
        if event.request_id in preparation_request_ids
        and event.type in {"request", "response", "request_completed"}
    ]
    if preparation_events:
        first = min(_timestamp(event.timestamp) for event in preparation_events)
        last = max(_timestamp(event.timestamp) for event in preparation_events)
        duration = max(0.0, (last - first).total_seconds() * 1000)
        if duration >= PREPARATION_SLOW_MS:
            warnings.append(
                f"Preparation/polling span was {duration:.3f} ms, above the initial {PREPARATION_SLOW_MS:.0f} ms review threshold."
            )


def _run_status(
    completed: bool, exchanges: Sequence[_ApiExchange]
) -> str:
    if completed:
        return "completed"
    if any(
        (_integer(_mapping(exchange.completed.payload), "status") or 0) >= 400
        for exchange in exchanges
        if exchange.completed is not None
    ):
        return "failed"
    if any(_is_answer_exchange(exchange) for exchange in exchanges):
        return "active"
    if any(
        (_string(_mapping(exchange.request.payload), "path") or "").endswith("/start")
        for exchange in exchanges
        if exchange.request is not None
    ):
        return "preparing"
    return "created"


def _selected_candidate(pair: _RPair) -> str | None:
    if pair.response is None:
        return None
    payload = _mapping(pair.response.payload)
    body = _mapping(None if payload is None else payload.get("body"))
    if _operation(pair.request) == "select":
        return _string(body, "candidate_id")
    next_candidate = _mapping(
        None if body is None else body.get("next_candidate")
    )
    return _string(next_candidate, "candidate_id")


def _highest_states(
    posterior: Sequence[float], knowledge_states: Sequence[tuple[str, ...]]
) -> tuple[ProbabilityState, ...]:
    ranked = sorted(enumerate(posterior), key=lambda value: value[1], reverse=True)[
        :3
    ]
    return tuple(
        ProbabilityState(
            rank=rank,
            nodes=knowledge_states[index] if index < len(knowledge_states) else (),
            probability=probability,
        )
        for rank, (index, probability) in enumerate(ranked, start=1)
    )


def _entropy(posterior: Sequence[float]) -> float | None:
    if not posterior:
        return None
    return -sum(value * math.log2(value) for value in posterior if value > 0)


def _total_variation(
    before: Sequence[float], after: Sequence[float]
) -> float | None:
    if not before or len(before) != len(after):
        return None
    return 0.5 * sum(abs(left - right) for left, right in zip(before, after))


def _is_answer_exchange(exchange: _ApiExchange) -> bool:
    if exchange.request is None:
        return False
    path = _string(_mapping(exchange.request.payload), "path") or ""
    return path.endswith("/answers")


def _operation(event: DiagnosticEvent) -> str:
    return _operation_from_path(_string(_mapping(event.payload), "path"))


def _operation_from_path(path: str | None) -> str:
    if path is None:
        return "unknown"
    return path.rstrip("/").rsplit("/", maxsplit=1)[-1] or "unknown"


def _sanitize_r_value(value: JsonValue | None) -> JsonValue:
    if isinstance(value, dict):
        return {
            key: _sanitize_r_value(child)
            for key, child in value.items()
            if key in _R_ALLOWED_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_r_value(child) for child in value]
    return value


def _json_bytes(value: JsonValue | None) -> int:
    if value is None:
        return 0
    return len(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
    )


def _mapping(value: JsonValue | None) -> Mapping[str, JsonValue] | None:
    return value if isinstance(value, dict) else None


def _sequence(value: JsonValue | None) -> Sequence[JsonValue]:
    return value if isinstance(value, list) else ()


def _string(
    value: Mapping[str, JsonValue] | None, key: str
) -> str | None:
    if value is None:
        return None
    item = value.get(key)
    return item if isinstance(item, str) else None


def _boolean(
    value: Mapping[str, JsonValue] | None, key: str
) -> bool | None:
    if value is None:
        return None
    item = value.get(key)
    return item if isinstance(item, bool) else None


def _number(
    value: Mapping[str, JsonValue] | None, key: str
) -> float | None:
    if value is None:
        return None
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, (int, float)):
        return None
    number = float(item)
    return number if math.isfinite(number) else None


def _integer(
    value: Mapping[str, JsonValue] | None, key: str
) -> int | None:
    if value is None:
        return None
    item = value.get(key)
    return item if isinstance(item, int) and not isinstance(item, bool) else None


def _strings(value: JsonValue | None) -> tuple[str, ...]:
    sequence = _sequence(value)
    return tuple(item for item in sequence if isinstance(item, str))


def _numbers(value: JsonValue | None) -> tuple[float, ...]:
    values: list[float] = []
    for item in _sequence(value):
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            continue
        number = float(item)
        if math.isfinite(number):
            values.append(number)
    return tuple(values)


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return datetime.fromtimestamp(0, UTC)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 3)
