"""Candidate-aware inventory and fixed-pool service behavior."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import pytest

from app.domain.models import *
from app.services.assessment import (
    AssessmentConflict,
    AssessmentService,
    CreateAssessmentCommand,
    feedback_from_profile,
)
from tests.factories import TEST_ID, make_item, make_model, make_profile
from tests.fakes.assessment_repository import InMemoryAssessmentRepository
from tests.fakes.kst_engine import FakeKstEngine


def _command() -> CreateAssessmentCommand:
    return CreateAssessmentCommand(
        user_id="user-1",
        learning_path_id="path-1",
        nodes=("A", "B"),
        relations=(GraphRelation("A", "B"),),
        course="Physics",
    )


def _built() -> ModelBuildResult:
    model = make_model()
    return ModelBuildResult(model=model, posterior=model.uniform_prior)


def _service(
    repository: InMemoryAssessmentRepository,
    engine: FakeKstEngine,
) -> AssessmentService:
    return AssessmentService(repository, engine, max_graph_nodes=10)


def _items(node: str, start: int, amount: int) -> tuple[AssessmentItem, ...]:
    return tuple(
        make_item(ItemId(start + index), node=node)
        for index in range(amount)
    )


@pytest.mark.asyncio
async def test_exact_partially_stocked_deficits_are_ordered_per_node() -> None:
    repository = InMemoryAssessmentRepository()
    await repository.seed_items(
        *_items("A", 1, 3),
        replace(make_item(ItemId(9), node="A"), prompt=""),
        *_items("B", 20, 1),
    )
    engine = FakeKstEngine(model_results=(_built(),))

    result = await _service(repository, engine).create_assessment(_command())
    session = next(iter(repository.session_snapshot.values()))
    order = next(iter(repository.yg_order_snapshot.values()))[0]

    assert result.status is SessionStatus.PREPARING
    assert result.missing_nodes == ("B",)
    assert order.item_requests == (
        InventoryRequest(node="B", amount=2),
    )
    assert isinstance(session.player_state, PlayerState)
    assert session.player_state.inventory_plan == InventoryPlan(
        required_per_node=3,
        requests=order.item_requests,
    )
    assert isinstance(session.model, KstModel)


@pytest.mark.asyncio
async def test_empty_inventory_requests_at_most_three_items_per_node() -> None:
    repository = InMemoryAssessmentRepository()
    engine = FakeKstEngine(model_results=(_built(),))

    result = await _service(repository, engine).create_assessment(_command())
    order = next(iter(repository.yg_order_snapshot.values()))[0]

    assert result.status is SessionStatus.PREPARING
    assert order.item_requests == (
        InventoryRequest(node="A", amount=3),
        InventoryRequest(node="B", amount=3),
    )
    assert all(request.amount <= 3 for request in order.item_requests)
    assert order.volume == 3


@pytest.mark.asyncio
async def test_activation_snapshots_all_items_in_stable_order() -> None:
    repository = InMemoryAssessmentRepository()
    await repository.seed_items(*_items("B", 20, 3), *_items("A", 1, 3))
    engine = FakeKstEngine(model_results=(_built(),))

    result = await _service(repository, engine).create_assessment(_command())
    session = next(iter(repository.session_snapshot.values()))
    assert result.status is SessionStatus.ACTIVE
    assert isinstance(session.player_state, PlayerState)
    pool = session.player_state.session_pool
    assert pool is not None
    assert isinstance(session.model, KstModel)
    assert tuple(candidate.item_id for candidate in pool.candidates) == (
        ItemId(1), ItemId(2), ItemId(3),
        ItemId(20), ItemId(21), ItemId(22),
    )
    assert len(pool.candidates) < session.model.derived_limits.safety_cap
    assert [call.method for call in engine.calls] == ["build_model", "select"]


@pytest.mark.asyncio
async def test_activation_pool_includes_all_valid_items_above_generation_target() -> None:
    repository = InMemoryAssessmentRepository()
    await repository.seed_items(*_items("B", 20, 5), *_items("A", 1, 4))
    engine = FakeKstEngine(model_results=(_built(),))

    result = await _service(repository, engine).create_assessment(_command())
    session = next(iter(repository.session_snapshot.values()))

    assert result.status is SessionStatus.ACTIVE
    assert isinstance(session.player_state, PlayerState)
    pool = session.player_state.session_pool
    assert pool is not None
    assert tuple(candidate.item_id for candidate in pool.candidates) == (
        ItemId(1), ItemId(2), ItemId(3), ItemId(4),
        ItemId(20), ItemId(21), ItemId(22), ItemId(23), ItemId(24),
    )


@pytest.mark.asyncio
async def test_partial_failed_generation_retries_only_remaining_deficit() -> None:
    repository = InMemoryAssessmentRepository()
    await repository.seed_items(*_items("A", 1, 3), *_items("B", 20, 1))
    engine = FakeKstEngine(model_results=(_built(),))
    service = _service(repository, engine)
    created = await service.create_assessment(_command())
    test_id = TestId(created.test_id)
    await repository.set_latest_yg_status(test_id, YgStatus.FAILED)
    await repository.seed_items(
        make_item(ItemId(4), node="A"),
        make_item(ItemId(21), node="B"),
    )

    view = await service.start_assessment(test_id)
    orders = repository.yg_order_snapshot[test_id]
    session = repository.session_snapshot[test_id]

    assert view.status is SessionStatus.PREPARING
    assert len(orders) == 2
    assert orders[-1].item_requests == (
        InventoryRequest(node="B", amount=1),
    )
    assert isinstance(session.player_state, PlayerState)
    assert session.player_state.inventory_plan == InventoryPlan(
        required_per_node=3,
        requests=(InventoryRequest(node="B", amount=1),),
    )


@pytest.mark.asyncio
async def test_answer_uses_snapshotted_parameters_and_never_reuses_current() -> None:
    repository = InMemoryAssessmentRepository()
    await repository.seed_items(*_items("A", 1, 4), *_items("B", 20, 4))
    engine = FakeKstEngine(
        model_results=(_built(),),
        advance_results=(
            AdvanceInProgress(
                posterior=(0.1, 0.3, 0.6),
                next_candidate=CandidateSelection(
                    candidate_id=CandidateId("yp:2"),
                    node="A",
                ),
            ),
        ),
    )
    service = _service(repository, engine)
    created = await service.create_assessment(_command())
    test_id = TestId(created.test_id)
    session = repository.session_snapshot[test_id]
    assert isinstance(session.player_state, PlayerState)
    current = session.player_state.current_question
    assert current is not None

    await service.submit_answer(
        test_id,
        current.submission_id,
        current.correct_option_id,
    )
    advance_call = next(call for call in engine.calls if call.method == "advance")
    administered = advance_call.arguments[2]
    remaining = cast(tuple[ItemCandidate, ...], advance_call.arguments[5])
    assert isinstance(administered, ItemCandidate)
    assert administered.item_id == current.item_id
    assert administered.beta == current.beta
    assert administered.eta == current.eta
    assert current.item_id not in {candidate.item_id for candidate in remaining}


@pytest.mark.asyncio
async def test_withdrawn_pool_item_is_not_supplied_to_r() -> None:
    repository = InMemoryAssessmentRepository()
    await repository.seed_items(*_items("A", 1, 4), *_items("B", 20, 4))
    engine = FakeKstEngine(
        model_results=(_built(),),
        advance_results=(AdvanceCompleted((0.1, 0.3, 0.6), make_profile()),),
    )
    service = _service(repository, engine)
    created = await service.create_assessment(_command())
    test_id = TestId(created.test_id)
    session = repository.session_snapshot[test_id]
    assert isinstance(session.player_state, PlayerState)
    current = session.player_state.current_question
    assert current is not None
    await repository.seed_items(
        replace(make_item(ItemId(2), node="A"), status=ItemStatus.ARCHIVED)
    )

    await service.submit_answer(
        test_id, current.submission_id, current.correct_option_id
    )
    advance_call = next(call for call in engine.calls if call.method == "advance")
    remaining = cast(tuple[ItemCandidate, ...], advance_call.arguments[5])
    assert ItemId(2) not in {candidate.item_id for candidate in remaining}


def test_inventory_exhaustion_is_publicly_confidence_limited() -> None:
    profile = replace(
        make_profile(),
        stop_reason=StopReason.ITEM_INVENTORY_EXHAUSTED,
    )
    assert feedback_from_profile(profile).confidence_limited is True


@pytest.mark.asyncio
async def test_nonterminal_v1_session_is_rejected() -> None:
    repository = InMemoryAssessmentRepository()
    session = AssessmentSession(
        test_id=TEST_ID,
        user_id="user",
        learning_path_id=LearningPathId("path"),
        graph_hash="legacy",
        status=SessionStatus.ACTIVE,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        method=AssessmentMethod.KST,
        player_state=LegacyPlayerState(posterior=(1.0,), answered_items=()),
        model=None,
    )
    await repository.seed_session(session)
    with pytest.raises(AssessmentConflict, match="v1"):
        await _service(repository, FakeKstEngine()).start_assessment(TEST_ID)


@pytest.mark.asyncio
async def test_three_node_session_reaches_eight_response_cap_without_reuse() -> None:
    repository = InMemoryAssessmentRepository()
    await repository.seed_items(
        *_items("A", 1, 3),
        *_items("B", 10, 3),
        *_items("C", 20, 3),
    )
    base = make_model()
    model = KstModel(
        schema_version=2,
        method=AssessmentMethod.KST,
        nodes=("A", "B", "C"),
        knowledge_states=(
            KnowledgeState(()),
            KnowledgeState(("A",)),
            KnowledgeState(("A", "B")),
            KnowledgeState(("A", "B", "C")),
        ),
        matrix=((0, 0, 0), (1, 0, 0), (1, 1, 0), (1, 1, 1)),
        uniform_prior=(0.25, 0.25, 0.25, 0.25),
        configuration=base.configuration,
        configuration_hash=base.configuration_hash,
        derived_limits=DerivedLimits(reliability_floor=7, safety_cap=8),
    )
    next_values = (
        ("yp:2", "A"),
        ("yp:3", "A"),
        ("yp:10", "B"),
        ("yp:11", "B"),
        ("yp:12", "B"),
        ("yp:20", "C"),
        ("yp:21", "C"),
    )
    engine = FakeKstEngine(
        model_results=(
            ModelBuildResult(model=model, posterior=model.uniform_prior),
        ),
        advance_results=tuple(
            AdvanceInProgress(
                posterior=model.uniform_prior,
                next_candidate=CandidateSelection(
                    candidate_id=CandidateId(candidate_id),
                    node=node,
                ),
            )
            for candidate_id, node in next_values
        )
        + (
            AdvanceCompleted(
                model.uniform_prior,
                replace(make_profile(), stop_reason=StopReason.SAFETY_CAP),
            ),
        ),
    )
    service = _service(repository, engine)
    created = await service.create_assessment(
        CreateAssessmentCommand(
            user_id="user",
            learning_path_id="path",
            nodes=("A", "B", "C"),
            relations=(GraphRelation("A", "B"), GraphRelation("B", "C")),
        )
    )
    test_id = TestId(created.test_id)
    administered: list[ItemId] = []
    for _ in range(8):
        session = repository.session_snapshot[test_id]
        assert isinstance(session.player_state, PlayerState)
        question = session.player_state.current_question
        assert question is not None
        administered.append(question.item_id)
        await service.submit_answer(
            test_id,
            question.submission_id,
            question.correct_option_id,
        )

    assert len(administered) == len(set(administered)) == 8
    assert repository.session_snapshot[test_id].status is SessionStatus.COMPLETED
