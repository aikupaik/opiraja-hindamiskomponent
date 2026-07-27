"""Exact HTTP contract and failure mapping for the asynchronous R adapter."""

import asyncio
from typing import cast

import httpx
import pytest

from app.domain.models import (
    AdvanceCompleted,
    AdvanceInProgress,
    GraphDefinition,
    GraphRelation,
    ItemId,
    KnowledgeState,
    NodeParameters,
)
from app.integrations.kst_engine import HttpxKstEngine, RUnavailable
from tests.factories import make_model, make_profile


def test_model_payload_cache_and_configuration_translation() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_model_response_json())

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url="http://r-service",
            transport=httpx.MockTransport(handler),
        ) as client:
            result = await HttpxKstEngine(client).build_model(
                GraphDefinition(
                    nodes=("A", "B"),
                    relations=(GraphRelation("A", "B"),),
                ),
                (
                    NodeParameters("A", item_id=ItemId(1), beta=0.05, eta=0.25),
                    NodeParameters("B", item_id=ItemId(2), beta=0.06, eta=0.24),
                ),
                (KnowledgeState(()), KnowledgeState(("A",))),
            )
        assert result.model.configuration.safety_cap.responses_above_floor == 1
        assert result.next_node == "A"

    asyncio.run(scenario())
    assert requests[0].url.path == "/internal/v1/kst/model"
    payload = _request_json(requests[0])
    assert payload == {
        "nodes": ["A", "B"],
        "relations": [{"from": "A", "to": "B"}],
        "node_parameters": [
            {"node": "A", "beta": 0.05, "eta": 0.25},
            {"node": "B", "beta": 0.06, "eta": 0.24},
        ],
        "cached_knowledge_states": [[], ["A"]],
    }


def test_advance_payload_and_both_response_variants() -> None:
    requests: list[httpx.Request] = []
    responses = iter(
        (
            {"status": "in_progress", "posterior": [0.1, 0.2, 0.7], "next_node": "B"},
            {
                "status": "completed",
                "posterior": [0.02, 0.03, 0.95],
                "profile": _profile_json(),
            },
        )
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=next(responses))

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url="http://r-service",
            transport=httpx.MockTransport(handler),
        ) as client:
            engine = HttpxKstEngine(client)
            first = await engine.advance(make_model(), (0.2, 0.3, 0.5), "A", True, 1)
            second = await engine.advance(make_model(), (0.1, 0.2, 0.7), "B", False, 8)
        assert isinstance(first, AdvanceInProgress)
        assert first.next_node == "B"
        assert isinstance(second, AdvanceCompleted)
        assert second.profile == make_profile()

    asyncio.run(scenario())
    payload = _request_json(requests[0])
    assert payload["question_node"] == "A"
    assert payload["response_correct"] is True
    assert payload["response_count"] == 1
    model_payload = cast(dict[str, object], payload["model"])
    configuration = cast(dict[str, object], model_payload["configuration"])
    assert configuration["safety_cap"] == {
        "minimum_above_floor": 1,
        "node_multiplier": 2.0,
    }
    assert "responses_above_floor" not in str(payload)


@pytest.mark.parametrize(
    "exception_type",
    [
        httpx.ConnectTimeout,
        httpx.ReadTimeout,
        httpx.WriteTimeout,
        httpx.PoolTimeout,
        httpx.ConnectError,
    ],
)
def test_transport_failures_are_unavailable(
    exception_type: type[httpx.RequestError],
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise exception_type("synthetic", request=request)

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url="http://r-service",
            transport=httpx.MockTransport(handler),
        ) as client:
            with pytest.raises(RUnavailable, match="R service unavailable"):
                await HttpxKstEngine(client).advance(
                    make_model(), (0.2, 0.3, 0.5), "A", True, 1
                )

    asyncio.run(scenario())


@pytest.mark.parametrize("response_kind", ["status", "json", "shape"])
def test_status_and_malformed_responses_are_unavailable(
    response_kind: str,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        if response_kind == "status":
            return httpx.Response(503, json={"secret": "not exposed"})
        if response_kind == "json":
            return httpx.Response(200, content=b"{")
        return httpx.Response(200, json={"status": "unexpected"})

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url="http://r-service",
            transport=httpx.MockTransport(handler),
        ) as client:
            with pytest.raises(RUnavailable, match="R service unavailable"):
                await HttpxKstEngine(client).advance(
                    make_model(), (0.2, 0.3, 0.5), "A", True, 1
                )

    asyncio.run(scenario())


def test_readiness_requires_exact_health_shape() -> None:
    responses = iter(({"status": "ok"}, {"status": "ok", "extra": True}))

    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(responses))

    async def scenario() -> None:
        async with httpx.AsyncClient(
            base_url="http://r-service",
            transport=httpx.MockTransport(handler),
        ) as client:
            engine = HttpxKstEngine(client)
            assert await engine.is_ready()
            assert not await engine.is_ready()

    asyncio.run(scenario())


def _model_response_json() -> dict[str, object]:
    return {
        "model": _r_model_json(),
        "posterior": [0.2, 0.3, 0.5],
        "next_node": "A",
    }


def _r_model_json() -> dict[str, object]:
    model = make_model()
    return {
        "schema_version": model.schema_version,
        "method": model.method.value,
        "nodes": list(model.nodes),
        "knowledge_states": [list(state.nodes) for state in model.knowledge_states],
        "matrix": [list(row) for row in model.matrix],
        "uniform_prior": list(model.uniform_prior),
        "beta": list(model.beta),
        "eta": list(model.eta),
        "configuration": {
            "schema_version": model.configuration.schema_version,
            "stop_confidence": model.configuration.stop_confidence,
            "feedback_credible_mass": model.configuration.feedback_credible_mass,
            "reliability_floor": {
                "minimum": model.configuration.reliability_floor.minimum,
                "multiplier": model.configuration.reliability_floor.multiplier,
                "maximum": model.configuration.reliability_floor.maximum,
            },
            "safety_cap": {
                "minimum_above_floor": (
                    model.configuration.safety_cap.responses_above_floor
                ),
                "node_multiplier": model.configuration.safety_cap.node_multiplier,
            },
        },
        "configuration_hash": model.configuration_hash,
    }


def _profile_json() -> dict[str, object]:
    profile = make_profile()
    return {
        "mastered": list(profile.mastered),
        "ready_to_learn": list(profile.ready_to_learn),
        "uncertain_ahead": list(profile.uncertain_ahead),
        "uncertain_prerequisite": list(profile.uncertain_prerequisite),
        "not_yet": list(profile.not_yet),
        "summary": profile.summary,
        "stop_reason": profile.stop_reason.value,
        "best_state_confidence": profile.best_state_confidence,
        "credible_mass": profile.credible_mass,
        "credible_state_count": profile.credible_state_count,
    }


def _request_json(request: httpx.Request) -> dict[str, object]:
    import json

    decoded = cast(object, json.loads(request.content))
    assert isinstance(decoded, dict)
    return cast(dict[str, object], decoded)
