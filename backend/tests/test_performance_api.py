"""API-only performance application contract and integrity coverage."""

import asyncio
import json
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import jwt
import pytest
from fastapi import FastAPI

from app.api.auth import TESTS_CREATE, TESTS_LAUNCH, TESTS_READ
from performance_api.app import create_app
from performance_api.fixtures import FIXTURE_SHAPES, build_item_bank, load_fixtures


def _configure(monkeypatch: pytest.MonkeyPatch, evidence_path: Path) -> None:
    values = {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_KEY": "unused-performance-service-key",
        "R_SERVICE_URL": "http://unused-r-service:8000",
        "ALLOWED_HOSTS": '["127.0.0.1"]',
        "OR_JWT_SECRET": "or-performance-secret-000000000000000000000000",
        "API_JWT_SECRET": "api-performance-secret-00000000000000000000000",
        "OR_JWT_ISSUER": "performance-or",
        "PLAYER_APP_URL": "http://127.0.0.1:5173",
        "PERF_RUN_ID": "perf-api-only-test",
        "PERF_API_WORKLOAD": "session",
        "PERF_API_SHAPE": "3-chain",
        "PERF_API_EVIDENCE_PATH": str(evidence_path),
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def _or_token() -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": "performance-or",
            "aud": "assessment-api",
            "sub": "performance-test",
            "scope": " ".join((TESTS_CREATE, TESTS_READ, TESTS_LAUNCH)),
            "iat": now,
            "exp": now + 300,
        },
        "or-performance-secret-000000000000000000000000",
        algorithm="HS256",
    )


@asynccontextmanager
async def _client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://127.0.0.1",
        ) as client:
            yield client


def test_committed_api_fixtures_provide_covered_inventory() -> None:
    fixtures = load_fixtures()

    assert tuple(fixtures) == FIXTURE_SHAPES
    assert {shape: fixture.answer_count for shape, fixture in fixtures.items()} == {
        "3-chain": 7,
        "10-chain": 10,
        "10-independent": 10,
    }
    items = build_item_bank(fixtures)
    assert len(items) == 30
    assert all(sum(item.node == node for item in items) == 3 for node in fixtures["10-chain"].graph.nodes)


@pytest.mark.asyncio
async def test_concurrent_sessions_complete_and_export_integrity_evidence(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    evidence_path = tmp_path / "api-only-state.json"
    _configure(monkeypatch, evidence_path)
    fixtures = load_fixtures()
    fixture = fixtures["3-chain"]
    app = create_app()
    headers = {"Authorization": f"Bearer {_or_token()}"}

    async with _client(app) as client:
        ready = await client.get("/health/ready")
        assert ready.status_code == 200
        assert ready.json() == {
            "status": "ready",
            "dependencies": {"supabase": "ready", "r": "ready"},
        }

        async def complete(marker: int) -> None:
            created = await client.post(
                "/api/v1/tests",
                headers=headers,
                json={
                    "user_id": f"perf-api-only-test-user-{marker}",
                    "learning_path_id": f"perf-api-only-test-path-{marker}",
                    "nodes": list(fixture.graph.nodes),
                    "relations": [
                        {
                            "from": relation.prerequisite,
                            "to": relation.dependent,
                        }
                        for relation in fixture.graph.relations
                    ],
                },
            )
            assert created.status_code == 201
            created_body = created.json()
            assert created_body["status"] == "active"
            test_id = created_body["test_id"]
            player_token = created_body["player_url"].split("#token=", 1)[1]
            player_headers = {"Authorization": f"Bearer {player_token}"}
            response = await client.post(
                f"/api/v1/player/tests/{test_id}/start",
                headers=player_headers,
            )
            assert response.status_code == 200
            body: dict[str, Any] = response.json()
            last_payload: dict[str, str] | None = None
            for index in range(fixture.answer_count):
                question = body["question"]
                last_payload = {
                    "submission_id": question["submission_id"],
                    "option_id": question["options"][0]["id"],
                }
                response = await client.post(
                    f"/api/v1/player/tests/{test_id}/answers",
                    headers=player_headers,
                    json=last_payload,
                )
                assert response.status_code == 200
                body = response.json()
                assert body["status"] == (
                    "completed" if index + 1 == fixture.answer_count else "active"
                )
            assert last_payload is not None
            assert len(body["question_results"]) == fixture.answer_count
            replay = await client.post(
                f"/api/v1/player/tests/{test_id}/answers",
                headers=player_headers,
                json=last_payload,
            )
            assert replay.status_code == 200
            assert replay.json() == body

        await asyncio.gather(*(complete(marker) for marker in range(5)))

    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert evidence["run_id"] == "perf-api-only-test"
    assert evidence["session_count"] == 5
    assert evidence["session_status_counts"] == {"completed": 5}
    assert evidence["answer_count"] == 5 * fixture.answer_count
    assert evidence["unique_submission_count"] == 5 * fixture.answer_count
    assert evidence["yg_order_count"] == 0
    assert evidence["integrity_errors"] == []
    assert evidence["engine_call_counts"]["advance"] == 5 * fixture.answer_count
    assert evidence["event_loop_lag"]["sample_count"] >= 0

