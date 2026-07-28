"""Behavioral and concurrency tests for the reusable repository fake."""

import asyncio
from dataclasses import replace
from uuid import UUID

import pytest

from app.domain.models import (
    AnswerCommitOutcome,
    AnsweredItem,
    GraphCacheEntry,
    GraphDefinition,
    ItemId,
    ItemStatus,
    KnowledgeState,
    LegacyPlayerState,
    PendingGraph,
    PlayerState,
    SessionStatus,
    SubmissionId,
    TestId,
    YgOrder,
    YgStatus,
)
from app.domain.repository import AssessmentRepository, RepositoryDataError
from tests.factories import (
    ITEM_ID,
    NEXT_ITEM_ID,
    NEXT_SUBMISSION_ID,
    SUBMISSION_ID,
    TEST_ID,
    make_activation,
    make_answer,
    make_item,
    make_preparing_session,
    make_profile,
    make_question,
    make_session,
    make_transition,
)
from tests.fakes import InMemoryAssessmentRepository


def test_fake_structurally_satisfies_protocol() -> None:
    repository: AssessmentRepository = InMemoryAssessmentRepository()
    assert repository is not None


def test_graph_insert_if_absent_race_returns_one_canonical_entry() -> None:
    async def scenario() -> None:
        repository = InMemoryAssessmentRepository()
        first = GraphCacheEntry(
            graph_hash="same",
            graph=GraphDefinition(nodes=("A",), relations=()),
            knowledge_states=(KnowledgeState(()), KnowledgeState(("A",))),
        )
        second = replace(
            first,
            graph=GraphDefinition(nodes=("different",), relations=()),
        )

        left, right = await asyncio.gather(
            repository.insert_cached_graph_if_absent(first),
            repository.insert_cached_graph_if_absent(second),
        )

        assert left == right
        assert len(repository.graph_snapshot) == 1

    asyncio.run(scenario())


def test_session_creation_activation_and_failure_rules() -> None:
    async def scenario() -> None:
        repository = InMemoryAssessmentRepository()
        preparing = make_preparing_session()
        created = await repository.create_session(preparing)
        assert isinstance(created.player_state, PlayerState)
        assert created.player_state.schema_version == 2

        active = await repository.activate_session(make_activation())
        repeated = await repository.activate_session(make_activation())
        assert active == repeated
        assert active.status is SessionStatus.ACTIVE
        assert isinstance(active.player_state, PlayerState)
        assert active.player_state.current_question == make_question()

        other = replace(
            make_preparing_session(),
            test_id=TestId(UUID("10000000-0000-4000-8000-000000000002")),
        )
        await repository.create_session(other)
        failed = await repository.mark_session_failed(other.test_id)
        assert failed.status is SessionStatus.FAILED

        with pytest.raises(RepositoryDataError, match="cannot fail"):
            await repository.mark_session_failed(TEST_ID)

    asyncio.run(scenario())


def test_activation_writes_graph_hash_and_clears_pending_snapshot() -> None:
    async def scenario() -> None:
        repository = InMemoryAssessmentRepository()
        activation = make_activation()
        pending = PendingGraph(
            graph_hash=activation.graph_hash,
            nodes=activation.model.nodes,
            relations=(),
        )
        preparing = replace(
            make_preparing_session(),
            graph_hash=None,
            player_state=PlayerState.new(pending_graph=pending),
        )
        await repository.create_session(preparing)

        active = await repository.activate_session(activation)

        assert active.graph_hash == activation.graph_hash
        assert isinstance(active.player_state, PlayerState)
        assert active.player_state.pending_graph is None
        assert active.player_state.posterior == activation.model.uniform_prior

    asyncio.run(scenario())


def test_legacy_session_cannot_activate() -> None:
    async def scenario() -> None:
        repository = InMemoryAssessmentRepository()
        legacy = replace(
            make_preparing_session(),
            player_state=LegacyPlayerState(posterior=(), answered_items=()),
        )
        await repository.seed_session(legacy)

        with pytest.raises(RepositoryDataError, match="legacy"):
            await InMemoryAssessmentRepository().create_session(legacy)
        with pytest.raises(RepositoryDataError, match="legacy"):
            await repository.activate_session(make_activation())

    asyncio.run(scenario())


def test_complete_inventory_reads_and_exact_pool_loading() -> None:
    async def scenario() -> None:
        repository = InMemoryAssessmentRepository()
        first = make_item()
        second = make_item(NEXT_ITEM_ID)
        archived = replace(make_item(ItemId(43), node="B"), status=ItemStatus.ARCHIVED)
        await repository.seed_items(first, second, archived)

        inventory = await repository.list_usable_items_for_nodes(("B", "A", "C"))
        assert [item.item_id for item in inventory] == [ITEM_ID, NEXT_ITEM_ID]
        exact = await repository.load_items_by_ids(
            (NEXT_ITEM_ID, ItemId(43), ITEM_ID)
        )
        assert [item.item_id for item in exact] == [NEXT_ITEM_ID, ITEM_ID]
        with pytest.raises(RepositoryDataError, match="unique"):
            await repository.load_items_by_ids((ITEM_ID, ITEM_ID))

    asyncio.run(scenario())


def test_only_one_pending_yg_order_is_created_under_race() -> None:
    async def scenario() -> None:
        repository = InMemoryAssessmentRepository()
        order = YgOrder(
            order_id=None,
            test_id=TEST_ID,
            course="Physics",
            nodes=("A",),
            cognitive_level=None,
            volume=3,
            status=YgStatus.PENDING,
        )

        first, second = await asyncio.gather(
            repository.create_yg_order_if_no_pending(order),
            repository.create_yg_order_if_no_pending(replace(order, nodes=("B",))),
        )

        assert first == second
        assert len(repository.yg_order_snapshot[TEST_ID]) == 1

    asyncio.run(scenario())


def test_new_answer_applies_and_increments_telemetry_once() -> None:
    async def scenario() -> None:
        repository = await _active_repository()

        result = await repository.commit_answer(
            SUBMISSION_ID, make_answer(), make_transition()
        )

        assert result.outcome is AnswerCommitOutcome.APPLIED
        assert repository.item_snapshot[ITEM_ID].usage_count == 1
        assert len(repository.answer_snapshot) == 1
        assert isinstance(result.session.player_state, PlayerState)
        assert result.session.player_state.current_question == make_question(
            NEXT_SUBMISSION_ID, NEXT_ITEM_ID, node="B"
        )

    asyncio.run(scenario())


def test_identical_inserted_answer_recovers_interrupted_transition() -> None:
    async def scenario() -> None:
        repository = await _active_repository()
        await repository.seed_answer(make_answer())

        result = await repository.commit_answer(
            SUBMISSION_ID, make_answer(), make_transition()
        )

        assert result.outcome is AnswerCommitOutcome.RECOVERED
        assert repository.item_snapshot[ITEM_ID].usage_count == 0

    asyncio.run(scenario())


def test_completed_retry_replays_without_increment() -> None:
    async def scenario() -> None:
        repository = await _active_repository()
        profile = make_profile()
        transition = make_transition(profile=profile)
        first = await repository.commit_answer(SUBMISSION_ID, make_answer(), transition)
        retry = await repository.commit_answer(SUBMISSION_ID, make_answer(), transition)

        assert first.outcome is AnswerCommitOutcome.APPLIED
        assert retry.outcome is AnswerCommitOutcome.REPLAYED
        assert retry.session.status is SessionStatus.COMPLETED
        assert repository.item_snapshot[ITEM_ID].usage_count == 1

    asyncio.run(scenario())


def test_stale_token_is_never_accepted_and_conflict_is_distinct() -> None:
    async def scenario() -> None:
        accepted = AnsweredItem(
            submission_id=SUBMISSION_ID,
            item_id=ITEM_ID,
            node="A",
            response_correct=True,
        )
        repository = InMemoryAssessmentRepository()
        await repository.seed_items(make_item(), make_item(NEXT_ITEM_ID))
        advanced = make_session(
            current_question=make_question(NEXT_SUBMISSION_ID, NEXT_ITEM_ID, node="B"),
            answered_items=(accepted,),
        )
        await repository.seed_session(advanced)
        stale_id = SubmissionId(UUID("20000000-0000-4000-8000-000000000099"))
        stale_answer = make_answer(stale_id)
        stale_transition = make_transition(submission_id=stale_id)

        stale = await repository.commit_answer(stale_id, stale_answer, stale_transition)
        conflict = await repository.commit_answer(
            stale_id,
            replace(stale_answer, selected_answer="different"),
            stale_transition,
        )

        assert stale.outcome is AnswerCommitOutcome.STALE
        assert conflict.outcome is AnswerCommitOutcome.PAYLOAD_CONFLICT
        assert (
            repository.session_snapshot[TEST_ID].player_state == advanced.player_state
        )

    asyncio.run(scenario())


def test_failure_injection_is_one_shot_and_leaves_state_unchanged() -> None:
    async def scenario() -> None:
        repository = await _active_repository()
        before = repository.session_snapshot
        repository.fail_next("commit_answer")

        with pytest.raises(RuntimeError, match="injected"):
            await repository.commit_answer(
                SUBMISSION_ID, make_answer(), make_transition()
            )

        assert repository.session_snapshot == before
        assert repository.answer_snapshot == {}
        applied = await repository.commit_answer(
            SUBMISSION_ID, make_answer(), make_transition()
        )
        assert applied.outcome is AnswerCommitOutcome.APPLIED

    asyncio.run(scenario())


def test_seed_and_return_values_are_isolated_and_calls_are_recorded() -> None:
    async def scenario() -> None:
        repository = InMemoryAssessmentRepository()
        item = make_item()
        await repository.seed_items(item)

        returned = await repository.get_item(ITEM_ID)

        assert returned == item
        assert returned is not item
        assert repository.item_snapshot is not repository.item_snapshot
        assert repository.calls[-1].method == "get_item"

    asyncio.run(scenario())


async def _active_repository() -> InMemoryAssessmentRepository:
    repository = InMemoryAssessmentRepository()
    await repository.seed_items(make_item(), make_item(NEXT_ITEM_ID, node="B"))
    await repository.seed_session(make_session())
    return repository
