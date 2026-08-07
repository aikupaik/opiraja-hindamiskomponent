"""Experiment report reconstruction, metrics, privacy, and route coverage."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import httpx
from fastapi import FastAPI
import pytest

from app.admin.diagnostics import (
    DiagnosticEvent,
    DiagnosticHub,
    DiagnosticSnapshot,
    JsonValue,
)
from app.admin.reporting import build_experiment_report
from app.config import Settings
from app.api.tokens import TokenService
from app.main import create_app

EXPERIMENT_ID = "30000000-0000-4000-8000-000000000003"
TEST_ID = "10000000-0000-4000-8000-000000000001"
NOW = datetime(2026, 7, 29, 9, tzinfo=UTC)


def _model() -> dict[str, JsonValue]:
    return {
        "schema_version": 2,
        "method": "kst",
        "nodes": ["A", "B"],
        "knowledge_states": [[], ["A"], ["A", "B"]],
        "matrix": [[0, 0], [1, 0], [1, 1]],
        "uniform_prior": [0.34, 0.33, 0.33],
        "configuration": {
            "schema_version": 1,
            "stop_confidence": 0.8,
            "feedback_credible_mass": 0.9,
            "reliability_floor": {
                "minimum": 2,
                "multiplier": 1.5,
                "maximum": 8,
            },
            "safety_cap": {
                "minimum_above_floor": 1,
                "node_multiplier": 2.0,
            },
        },
        "configuration_hash": (
            "kst-config-v1:sha256:"
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        ),
        "reliability_floor": 3,
        "safety_cap": 5,
    }


def _event(
    sequence: int,
    event_type: str,
    payload: JsonValue,
    *,
    request_id: str | None,
    source: str = "client",
    level: str = "info",
    seconds: float | None = None,
) -> DiagnosticEvent:
    return DiagnosticEvent(
        sequence=sequence,
        timestamp=(NOW + timedelta(seconds=seconds or sequence)).isoformat(),
        source=source,
        level=level,
        type=event_type,
        request_id=request_id,
        test_id=TEST_ID,
        payload=payload,
    )


def _complete_snapshot() -> DiagnosticSnapshot:
    model = _model()
    create_id = "request-create"
    answer_one = "request-answer-1"
    answer_two = "request-answer-2"
    events = (
        _event(
            1,
            "request",
            {
                "method": "POST",
                "path": "/api/v1/tests",
                "body": {
                    "user_id": "participant-secret",
                    "learning_path_id": "path-secret",
                    "raw_client_body": "client-secret",
                    "nodes": ["A", "B"],
                },
            },
            request_id=create_id,
        ),
        _event(
            2,
            "r_request",
            {
                "method": "POST",
                "path": "/internal/v2/kst/model",
                "body": {
                    "nodes": ["A", "B"],
                    "relations": [{"from": "A", "to": "B"}],
                    "cached_knowledge_states": None,
                    "authorization": "service-secret",
                },
            },
            request_id=create_id,
            source="fastapi-to-r",
        ),
        _event(
            3,
            "r_response",
            {
                "status": 200,
                "duration_ms": 600.0,
                "body": {
                    "model": model,
                    "posterior": [0.34, 0.33, 0.33],
                    "prompt": "question-secret",
                },
            },
            request_id=create_id,
            source="r-to-fastapi",
        ),
        _event(
            4,
            "r_request",
            {
                "method": "POST",
                "path": "/internal/v2/kst/select",
                "body": {
                    "model": model,
                    "posterior": [0.34, 0.33, 0.33],
                    "candidates": [
                        {
                            "candidate_id": "yp:41",
                            "node": "A",
                            "beta": 0.05,
                            "eta": 0.25,
                        }
                    ],
                },
            },
            request_id=create_id,
            source="fastapi-to-r",
        ),
        _event(
            5,
            "r_response",
            {
                "status": 200,
                "duration_ms": 20.0,
                "body": {"candidate_id": "yp:41", "node": "A"},
            },
            request_id=create_id,
            source="r-to-fastapi",
        ),
        _event(
            6,
            "supabase_operation",
            {
                "operation": "testisessioonid.insert",
                "duration_ms": 550.0,
                "count": 1,
            },
            request_id=create_id,
            source="supabase",
        ),
        _event(
            7,
            "response",
            {
                "status": 201,
                "body": {
                    "test_id": TEST_ID,
                    "question": "question-secret",
                },
            },
            request_id=create_id,
        ),
        _event(
            8,
            "request_completed",
            {
                "method": "POST",
                "path": "/api/v1/tests",
                "status": 201,
                "outcome": "created",
                "total_ms": 1300.0,
                "r_ms": 620.0,
                "supabase_ms": 550.0,
            },
            request_id=create_id,
            source="fastapi",
        ),
        _answer_request(9, answer_one, "option-answer-secret"),
        _advance_request(
            10,
            answer_one,
            model,
            candidate_id="yp:41",
            node="A",
            posterior=[0.34, 0.33, 0.33],
            correct=True,
            response_count=1,
        ),
        _event(
            11,
            "r_response",
            {
                "status": 200,
                "duration_ms": 25.0,
                "body": {
                    "status": "in_progress",
                    "posterior": [0.1, 0.3, 0.6],
                    "next_candidate": {
                        "candidate_id": "yp:42",
                        "node": "B",
                    },
                },
            },
            request_id=answer_one,
            source="r-to-fastapi",
        ),
        _answer_response(12, answer_one, "active"),
        _completed_request(13, answer_one, 120.0, 25.0, 40.0),
        _answer_request(14, answer_two, "another-answer-secret"),
        _advance_request(
            15,
            answer_two,
            model,
            candidate_id="yp:42",
            node="B",
            posterior=[0.1, 0.3, 0.6],
            correct=False,
            response_count=2,
        ),
        _event(
            16,
            "r_response",
            {
                "status": 200,
                "duration_ms": 30.0,
                "body": {
                    "status": "completed",
                    "posterior": [0.15, 0.55, 0.3],
                    "profile": {
                        "mastered": ["A"],
                        "ready_to_learn": ["B"],
                        "uncertain_ahead": [],
                        "uncertain_prerequisite": [],
                        "not_yet": [],
                        "summary": "Descriptive profile",
                        "stop_reason": "natural",
                        "best_state_confidence": 0.55,
                        "credible_mass": 0.9,
                        "credible_state_count": 2,
                        "confidence_limited": False,
                    },
                },
            },
            request_id=answer_two,
            source="r-to-fastapi",
        ),
        _answer_response(17, answer_two, "completed"),
        _completed_request(18, answer_two, 140.0, 30.0, 45.0),
    )
    return DiagnosticSnapshot(events=events, truncated=False, maximum_events=500)


def _answer_request(
    sequence: int, request_id: str, selected: str
) -> DiagnosticEvent:
    return _event(
        sequence,
        "request",
        {
            "method": "POST",
            "path": f"/api/v1/player/tests/{TEST_ID}/answers",
            "body": {
                "submission_id": "submission-secret",
                "option_id": selected,
            },
        },
        request_id=request_id,
    )


def _advance_request(
    sequence: int,
    request_id: str,
    model: dict[str, JsonValue],
    *,
    candidate_id: str,
    node: str,
    posterior: list[JsonValue],
    correct: bool,
    response_count: int,
) -> DiagnosticEvent:
    return _event(
        sequence,
        "r_request",
        {
            "method": "POST",
            "path": "/internal/v2/kst/advance",
            "body": {
                "model": model,
                "posterior": posterior,
                "administered": {
                    "candidate_id": candidate_id,
                    "node": node,
                    "beta": 0.05,
                    "eta": 0.25,
                },
                "response_correct": correct,
                "response_count": response_count,
                "remaining_candidates": [],
            },
        },
        request_id=request_id,
        source="fastapi-to-r",
    )


def _answer_response(
    sequence: int, request_id: str, status: str
) -> DiagnosticEvent:
    return _event(
        sequence,
        "response",
        {
            "status": 200,
            "body": {
                "status": status,
                "question": "question-secret",
                "selected_answer": "answer-secret",
            },
        },
        request_id=request_id,
    )


def _completed_request(
    sequence: int,
    request_id: str,
    total_ms: float,
    r_ms: float,
    supabase_ms: float,
) -> DiagnosticEvent:
    return _event(
        sequence,
        "request_completed",
        {
            "method": "POST",
            "path": f"/api/v1/player/tests/{TEST_ID}/answers",
            "status": 200,
            "outcome": "ok",
            "total_ms": total_ms,
            "r_ms": r_ms,
            "supabase_ms": supabase_ms,
        },
        request_id=request_id,
        source="fastapi",
    )


def test_complete_report_reconstructs_research_and_developer_metrics() -> None:
    report = build_experiment_report(
        EXPERIMENT_ID,
        _complete_snapshot(),
        generated_at=NOW,
    )

    assert report.schema_version == "1.0"
    assert report.completion_state == "completed"
    assert report.run_status == "completed"
    assert report.research.metadata.nodes == ("A", "B")
    assert report.research.metadata.relations[0].prerequisite == "A"
    assert report.research.metadata.reliability_floor.derived_floor == 3
    assert report.research.metadata.safety_cap.derived_cap == 5
    assert report.research.metadata.knowledge_state_count == 3
    assert len(report.research.operations) == 4

    steps = report.research.adaptive_steps
    assert len(steps) == 2
    assert steps[0].candidate_id == "yp:41"
    assert steps[0].response_correct is True
    assert steps[0].posterior_before == (0.34, 0.33, 0.33)
    assert steps[0].posterior_after == (0.1, 0.3, 0.6)
    assert steps[0].maximum_state_confidence == pytest.approx(0.6)
    assert steps[0].total_variation_movement == pytest.approx(0.27)
    assert steps[0].highest_probability_states[0].nodes == ("A", "B")
    assert steps[0].approximate_response_interval_ms == 4000.0
    assert steps[0].system_processing_ms == 120.0
    assert steps[1].decision == "completed"
    assert steps[1].r_processing_ms == 30.0

    summary = report.research.summary
    assert summary.response_count == 2
    assert summary.correct_count == 1
    assert summary.overall_accuracy == 0.5
    assert summary.node_path == ("A", "B")
    assert summary.stopping_reason == "natural"
    assert summary.final_profile is not None
    assert summary.final_profile.ready_to_learn == ("B",)

    developer = report.developer
    assert developer.api_latency.count == 3
    assert developer.api_latency.total_ms == 1560.0
    assert developer.backend_time.r_ms == 675.0
    assert developer.backend_time.supabase_ms == 635.0
    assert developer.backend_time.residual_application_ms == 250.0
    assert developer.r_by_operation[0].count >= 1
    assert developer.supabase_by_operation[0].operation == (
        "testisessioonid.insert"
    )
    assert developer.slowest_api_requests[0].diagnostic_flag is True
    assert developer.slowest_r_calls[0].diagnostic_flag is True
    assert developer.slowest_supabase_operations[0].diagnostic_flag is True
    assert sum(item.approximate_request_bytes for item in developer.traffic) > 0


def test_report_output_enforces_privacy_allowlist() -> None:
    report = build_experiment_report(EXPERIMENT_ID, _complete_snapshot())
    serialized = report.model_dump_json()

    for forbidden in (
        "participant-secret",
        "path-secret",
        "client-secret",
        "question-secret",
        "answer-secret",
        "option-answer-secret",
        "another-answer-secret",
        "submission-secret",
        "service-secret",
        "authorization",
        "user_id",
        "learning_path_id",
        "selected_answer",
    ):
        assert forbidden not in serialized
    assert report.exact_r_calls[0].input == {
        "nodes": ["A", "B"],
        "relations": [{"from": "A", "to": "B"}],
        "cached_knowledge_states": None,
    }
    assert "prompt" not in cast(dict[str, object], report.exact_r_calls[0].output)


def test_partial_truncated_and_missing_pairs_report_warnings_without_guessing() -> None:
    request = _event(
        9,
        "r_request",
        {
            "method": "POST",
            "path": "/internal/v2/kst/advance",
            "body": {
                "posterior": [0.5, 0.5],
                "administered": {
                    "candidate_id": "yp:1",
                    "node": "A",
                    "beta": 0.1,
                    "eta": 0.2,
                },
                "response_correct": True,
                "response_count": 1,
                "remaining_candidates": [],
            },
        },
        request_id="partial-request",
        source="fastapi-to-r",
    )
    report = build_experiment_report(
        EXPERIMENT_ID,
        DiagnosticSnapshot(
            events=(request,),
            truncated=True,
            maximum_events=1,
        ),
    )

    assert report.completion_state == "partial"
    assert report.buffer_truncated is True
    assert report.developer.last_successful_stage == "none observed"
    assert "sequence 9" in report.developer.last_recorded_event
    assert any("truncated" in warning for warning in report.data_quality_warnings)
    assert any("no response" in warning for warning in report.data_quality_warnings)
    assert any("does not infer a root cause" in warning for warning in report.data_quality_warnings)


def _settings() -> Settings:
    return Settings.model_validate(
        {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_KEY": "service-secret",
            "R_SERVICE_URL": "http://r-service:8000",
            "ALLOWED_HOSTS": ["193.40.157.124", "127.0.0.1", "testserver"],
            "ADMIN_ACCESS_KEY": "operator-secret",
            "OR_JWT_SECRET": "or-test-secret-00000000000000000000000000000000",
            "API_JWT_SECRET": "api-test-secret-0000000000000000000000000000000",
            "OR_JWT_ISSUER": "test-or",
            "PLAYER_APP_URL": "http://localhost:5173",
        }
    )


def _app(hub: DiagnosticHub) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        app.state.diagnostic_hub = hub
        yield

    return create_app(_settings(), lifespan=lifespan)


def _admin_token() -> str:
    return TokenService(_settings()).issue_admin()


@pytest.mark.asyncio
async def test_report_endpoint_requires_diagnostics_auth_and_returns_404() -> None:
    hub = DiagnosticHub()
    jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiJwbGF5ZXIifQ."
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNO"
    )
    app = _app(hub)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            unauthorized = await client.get(
                f"/api/v1/admin/experiments/{EXPERIMENT_ID}/report"
            )
            missing = await client.get(
                f"/api/v1/admin/experiments/{EXPERIMENT_ID}/report",
                headers={"Authorization": f"Bearer {_admin_token()}"},
            )
            hub.emit(
                EXPERIMENT_ID,
                source="client",
                level="info",
                event_type="request",
                request_id="request",
                test_id=None,
                payload={
                    "method": "POST",
                    "path": "/api/v1/tests",
                    "body": {"player_url": f"/test/{TEST_ID}#token={jwt}"},
                },
            )
            partial = await client.get(
                f"/api/v1/admin/experiments/{EXPERIMENT_ID}/report",
                headers={"Authorization": f"Bearer {_admin_token()}"},
            )

    assert unauthorized.status_code == 401
    assert missing.status_code == 404
    assert partial.status_code == 200
    assert partial.json()["completion_state"] == "partial"
    assert jwt not in partial.text


def test_expired_experiment_has_no_report_snapshot() -> None:
    hub = DiagnosticHub(ttl_seconds=1)
    hub.emit(
        str(UUID(EXPERIMENT_ID)),
        source="client",
        level="info",
        event_type="request",
        request_id="request",
        test_id=None,
        payload={},
    )
    hub.expire(now=10**12)

    assert hub.snapshot(EXPERIMENT_ID) is None
