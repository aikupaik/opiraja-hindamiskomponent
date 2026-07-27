"""Focused coverage for Step 4 foundation and domain evolution."""

from dataclasses import replace

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.domain.graphs import (
    GraphValidationError,
    canonical_graph_json,
    graph_hash,
    make_pending_graph,
    normalize_graph,
)
from app.domain.models import GraphRelation, PlayerState
from app.persistence.supabase_mapping import decode_session, encode_session
from tests.factories import make_preparing_session


def test_settings_require_service_locations_and_credentials() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({})

    settings = Settings.model_validate(
        {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_KEY": "secret",
            "R_SERVICE_URL": "http://r-service:8000",
        }
    )

    assert settings.max_graph_nodes == 10
    assert settings.r_max_connections == 4
    assert settings.r_connect_timeout_seconds == 2
    assert settings.r_read_timeout_seconds == 30
    assert settings.r_write_timeout_seconds == 5
    assert settings.r_pool_timeout_seconds == 1
    assert settings.readiness_timeout_seconds == 1
    assert settings.supabase_request_timeout_seconds == 10


def test_graph_normalization_hash_is_order_independent_and_utf8_stable() -> None:
    first = normalize_graph(
        ("Õun", "A"),
        (
            GraphRelation("Õun", "A"),
            GraphRelation("Õun", "A"),
        ),
        max_nodes=10,
    )
    second = normalize_graph(
        ("A", "Õun"),
        (GraphRelation("Õun", "A"),),
        max_nodes=10,
    )

    assert first == second
    assert canonical_graph_json(first) == (
        '{"nodes":["A","Õun"],"relations":[{"from":"Õun","to":"A"}]}'
    )
    assert graph_hash(first) == (
        "kst-graph-v1:sha256:"
        "3a007fc866c6b6bb4a2dfb5cded24b5d6b4e6cef3133411f9b7d0dca0fb8c47b"
    )
    changed = normalize_graph(("A", "Õun"), (), max_nodes=10)
    assert graph_hash(changed) != graph_hash(first)


@pytest.mark.parametrize(
    ("nodes", "relations"),
    [
        ((), ()),
        (("A", "A"), ()),
        ((" ",), ()),
        (("A",), (GraphRelation("A", "B"),)),
    ],
)
def test_graph_validation_rejects_invalid_boundaries(
    nodes: tuple[str, ...], relations: tuple[GraphRelation, ...]
) -> None:
    with pytest.raises(GraphValidationError):
        normalize_graph(nodes, relations, max_nodes=10)


def test_pending_graph_round_trip_and_old_v1_state_compatibility() -> None:
    graph = normalize_graph(
        ("B", "A"),
        (GraphRelation("A", "B"),),
        max_nodes=10,
    )
    pending = make_pending_graph(graph)
    session = replace(
        make_preparing_session(),
        graph_hash=None,
        player_state=PlayerState.new(pending_graph=pending),
    )

    encoded = encode_session(session)
    assert decode_session(encoded) == session

    state = encoded["tp_seisund"]
    assert isinstance(state, dict)
    del state["pending_graph"]
    decoded_old = decode_session(encoded)
    assert isinstance(decoded_old.player_state, PlayerState)
    assert decoded_old.player_state.pending_graph is None


def test_empty_preparing_model_decodes_as_absent() -> None:
    encoded = encode_session(make_preparing_session())
    encoded["testi_loogika"] = {}

    assert decode_session(encoded).model is None
