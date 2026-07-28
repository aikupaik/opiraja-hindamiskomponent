"""Exact tests for the pure database/domain mapping boundary."""

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest

from app.domain.models import (
    AssessmentMethod,
    AssessmentSession,
    GraphCacheEntry,
    GraphDefinition,
    GraphRelation,
    KnowledgeState,
    InventoryRequest,
    LearningPathId,
    LegacyPlayerState,
    PlayerState,
    SessionStatus,
    TestId,
    YgOrder,
    YgOrderId,
    YgStatus,
)
from app.domain.repository import RepositoryDataError
from app.persistence.supabase_mapping import (
    SESSION_COLUMNS,
    decode_answer,
    decode_graph_entry,
    decode_item,
    decode_final_profile,
    decode_session,
    decode_yg_order,
    encode_answer,
    encode_graph_entry,
    encode_item,
    encode_final_profile,
    encode_session,
    encode_yg_order,
    item_eligibility_filters,
)
from tests.factories import (
    NOW,
    SUBMISSION_ID,
    TEST_ID,
    make_answer,
    make_item,
    make_profile,
    make_session,
)


def test_answer_round_trip_uses_only_explicit_vastus_id() -> None:
    answer = make_answer()

    encoded = encode_answer(answer)

    assert encoded["vastus_id"] == str(SUBMISSION_ID)
    assert "submission_id" not in encoded
    assert decode_answer(encoded) == answer


def test_jsonb_values_are_structured_and_session_has_no_course() -> None:
    session = make_session()

    encoded = encode_session(session)

    assert isinstance(encoded["tp_seisund"], dict)
    assert isinstance(encoded["testi_loogika"], dict)
    assert encoded["lopp_profiil"] is None
    assert "kursus" not in encoded
    assert "kursus" not in SESSION_COLUMNS
    assert decode_session(encoded) == session


def test_final_profile_jsonb_round_trip_remains_structured() -> None:
    profile = make_profile()

    encoded = encode_final_profile(profile)

    assert isinstance(encoded, dict)
    assert isinstance(encoded["omandatud"], list)
    assert decode_final_profile(encoded) == profile


def test_item_round_trip_and_eligibility_never_use_course() -> None:
    item = make_item()

    encoded = encode_item(item)

    assert "kursus" not in encoded
    assert item_eligibility_filters("A") == {
        "graafi_objekt": "A",
        "staatus": "kasutatav",
    }
    assert decode_item(encoded) == item


def test_graph_round_trip() -> None:
    graph = GraphCacheEntry(
        graph_hash="graph-v1:abc",
        graph=GraphDefinition(
            nodes=("A", "B"),
            relations=(GraphRelation("A", "B"),),
        ),
        knowledge_states=(
            KnowledgeState(()),
            KnowledgeState(("A",)),
            KnowledgeState(("A", "B")),
        ),
    )

    assert decode_graph_entry(encode_graph_entry(graph)) == graph


def test_yg_order_round_trip_preserves_course_only_on_order() -> None:
    order = YgOrder(
        order_id=YgOrderId(5),
        test_id=TEST_ID,
        course="Physics",
        nodes=("A", "B"),
        cognitive_level="mõistab",
        volume=3,
        status=YgStatus.PENDING,
        item_requests=(
            InventoryRequest(node="A", amount=3),
            InventoryRequest(node="B", amount=3),
        ),
    )

    assert decode_yg_order(encode_yg_order(order)) == order


def test_legacy_session_is_readable_but_not_writable() -> None:
    row: dict[str, object] = {
        "test_id": str(TEST_ID),
        "kasutaja_id": "user-1",
        "rada_id": "path-1",
        "graaf_hash": None,
        "staatus": "planeerimisel",
        "alustatud": NOW.isoformat(),
        "lopp_profiil": None,
        "testi_loogika": None,
        "metoodika": "kst",
        "tp_seisund": {
            "posterior": [0.4, 0.6],
            "kysitud": [{"yp_id": 1, "solm": "A", "vastus_oige": True}],
        },
        "eesmark": None,
    }

    session = decode_session(row)

    assert isinstance(session.player_state, LegacyPlayerState)
    assert session.is_legacy
    with pytest.raises(RepositoryDataError, match="legacy"):
        encode_session(session)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("staatus", "mystery", "unknown staatus"),
        ("test_id", "not-a-uuid", "must be a UUID"),
    ],
)
def test_malformed_session_row_is_rejected(
    field: str, value: str, message: str
) -> None:
    encoded: dict[str, object] = dict(encode_session(make_session()))
    encoded[field] = value

    with pytest.raises(RepositoryDataError, match=message):
        decode_session(encoded)


def test_unknown_player_state_schema_is_rejected() -> None:
    encoded: dict[str, object] = dict(encode_session(make_session()))
    state = dict(cast(dict[str, object], encoded["tp_seisund"]))
    state["schema_version"] = 3
    encoded["tp_seisund"] = state

    with pytest.raises(RepositoryDataError, match="unsupported player state"):
        decode_session(encoded)


def test_new_session_encoder_requires_v2() -> None:
    invalid = AssessmentSession(
        test_id=TestId(UUID("10000000-0000-4000-8000-000000000099")),
        user_id="user",
        learning_path_id=LearningPathId("path"),
        graph_hash=None,
        status=SessionStatus.PREPARING,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        method=AssessmentMethod.KST,
        player_state=PlayerState(
            schema_version=3,
            posterior=(),
            answered_items=(),
            current_question=None,
        ),
    )

    with pytest.raises(RepositoryDataError, match="unsupported player state"):
        encode_session(invalid)


def test_malformed_item_and_yg_statuses_are_rejected() -> None:
    item_row: dict[str, object] = dict(encode_item(make_item()))
    item_row["staatus"] = "unknown"
    with pytest.raises(RepositoryDataError, match="unknown staatus"):
        decode_item(item_row)

    order_row: dict[str, object] = {
        "id": 1,
        "test_id": str(TEST_ID),
        "kursus": "Physics",
        "graafi_objektid": ["A"],
        "kognitiivne_tase": None,
        "maht": 3,
        "staatus": "unknown",
        "loodud": None,
    }
    with pytest.raises(RepositoryDataError, match="unknown staatus"):
        decode_yg_order(order_row)
