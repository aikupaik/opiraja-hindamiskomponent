"""Exact HTTP contract and failure mapping for the R v2 adapter."""

import json
from typing import cast

import httpx
import pytest

from app.domain.models import *
from app.integrations.kst_engine import HttpxKstEngine, RUnavailable
from tests.factories import make_model, make_profile


def _candidate(item_id: int, node: str) -> ItemCandidate:
    return ItemCandidate(
        candidate_id=CandidateId(f"yp:{item_id}"),
        item_id=ItemId(item_id),
        node=node,
        beta=0.05,
        eta=0.25,
    )


@pytest.mark.asyncio
async def test_model_select_and_advance_use_v2_candidate_contract() -> None:
    requests: list[httpx.Request] = []
    responses = iter((
        {"model": _r_model_json(), "posterior": [0.2, 0.3, 0.5]},
        {"candidate_id": "yp:1", "node": "A"},
        {
            "status": "in_progress",
            "posterior": [0.1, 0.2, 0.7],
            "next_candidate": {"candidate_id": "yp:2", "node": "B"},
        },
    ))

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=next(responses))

    async with httpx.AsyncClient(
        base_url="http://r-service",
        transport=httpx.MockTransport(handler),
    ) as client:
        engine = HttpxKstEngine(client)
        built = await engine.build_model(
            GraphDefinition(
                nodes=("A", "B"),
                relations=(GraphRelation("A", "B"),),
            ),
            (KnowledgeState(()), KnowledgeState(("A",))),
        )
        candidates = (_candidate(1, "A"), _candidate(2, "B"))
        selected = await engine.select(built.model, built.posterior, candidates)
        advanced = await engine.advance(
            built.model,
            built.posterior,
            candidates[0],
            True,
            1,
            (candidates[1],),
        )

    assert [request.url.path for request in requests] == [
        "/internal/v2/kst/model",
        "/internal/v2/kst/select",
        "/internal/v2/kst/advance",
    ]
    model_payload = _request_json(requests[0])
    assert "node_parameters" not in model_payload
    assert model_payload["cached_knowledge_states"] == [[], ["A"]]
    assert selected == CandidateSelection(CandidateId("yp:1"), "A")
    assert isinstance(advanced, AdvanceInProgress)
    assert advanced.next_candidate == CandidateSelection(CandidateId("yp:2"), "B")
    advance_payload = _request_json(requests[2])
    assert advance_payload["administered"] == {
        "candidate_id": "yp:1",
        "node": "A",
        "beta": 0.05,
        "eta": 0.25,
    }
    assert "beta" not in cast(dict[str, object], advance_payload["model"])


@pytest.mark.asyncio
async def test_completed_inventory_exhaustion_is_decoded() -> None:
    profile = _profile_json(StopReason.ITEM_INVENTORY_EXHAUSTED)

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "posterior": [0.1, 0.2, 0.7],
                "profile": profile,
            },
        )

    async with httpx.AsyncClient(
        base_url="http://r-service",
        transport=httpx.MockTransport(handler),
    ) as client:
        result = await HttpxKstEngine(client).advance(
            make_model(), (0.2, 0.3, 0.5), _candidate(1, "A"), True, 1, ()
        )
    assert isinstance(result, AdvanceCompleted)
    assert result.profile.stop_reason is StopReason.ITEM_INVENTORY_EXHAUSTED


@pytest.mark.parametrize("kind", ["transport", "status", "json", "shape"])
@pytest.mark.asyncio
async def test_failures_are_unavailable(kind: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if kind == "transport":
            raise httpx.ConnectError("synthetic", request=request)
        if kind == "status":
            return httpx.Response(503, json={})
        if kind == "json":
            return httpx.Response(200, content=b"{")
        return httpx.Response(200, json={"status": "unexpected"})

    async with httpx.AsyncClient(
        base_url="http://r-service",
        transport=httpx.MockTransport(handler),
    ) as client:
        with pytest.raises(RUnavailable):
            await HttpxKstEngine(client).advance(
                make_model(), (0.2, 0.3, 0.5), _candidate(1, "A"), True, 1, ()
            )


def _r_model_json() -> dict[str, object]:
    model = make_model()
    return {
        "schema_version": 2,
        "method": "kst",
        "nodes": list(model.nodes),
        "knowledge_states": [list(state.nodes) for state in model.knowledge_states],
        "matrix": [list(row) for row in model.matrix],
        "uniform_prior": list(model.uniform_prior),
        "configuration": {
            "schema_version": 1,
            "stop_confidence": model.configuration.stop_confidence,
            "feedback_credible_mass": model.configuration.feedback_credible_mass,
            "reliability_floor": {
                "minimum": 7, "multiplier": 1.5, "maximum": 10,
            },
            "safety_cap": {
                "minimum_above_floor": 1, "node_multiplier": 2,
            },
        },
        "configuration_hash": model.configuration_hash,
        "reliability_floor": 7,
        "safety_cap": 8,
    }


def _profile_json(reason: StopReason = StopReason.NATURAL) -> dict[str, object]:
    profile = make_profile()
    return {
        "mastered": list(profile.mastered),
        "ready_to_learn": list(profile.ready_to_learn),
        "uncertain_ahead": list(profile.uncertain_ahead),
        "uncertain_prerequisite": list(profile.uncertain_prerequisite),
        "not_yet": list(profile.not_yet),
        "summary": profile.summary,
        "stop_reason": reason.value,
        "best_state_confidence": profile.best_state_confidence,
        "credible_mass": profile.credible_mass,
        "credible_state_count": profile.credible_state_count,
        "confidence_limited": reason is not StopReason.NATURAL,
    }


def _request_json(request: httpx.Request) -> dict[str, object]:
    value = cast(object, json.loads(request.content))
    assert isinstance(value, dict)
    return cast(dict[str, object], value)
