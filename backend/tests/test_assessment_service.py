"""Behavior tests for assessment creation, start, answer, and completion."""

import asyncio
from dataclasses import replace

import pytest

from app.domain.graphs import graph_hash, make_pending_graph, normalize_graph
from app.domain.models import (
    AdvanceCompleted,
    AdvanceInProgress,
    AnsweredItem,
    GraphCacheEntry,
    GraphRelation,
    ItemId,
    ModelBuildResult,
    OptionId,
    PlayerState,
    SessionStatus,
    StopReason,
    TestId,
    YgOrder,
    YgStatus,
)
from app.integrations.kst_engine import RUnavailable
from app.services.assessment import (
    AssessmentConflict,
    AssessmentNotFound,
    AssessmentService,
    CreateAssessmentCommand,
    feedback_from_profile,
)
from tests.factories import (
    NEXT_ITEM_ID,
    NEXT_SUBMISSION_ID,
    NOW,
    SUBMISSION_ID,
    TEST_ID,
    make_answer,
    make_item,
    make_model,
    make_preparing_session,
    make_profile,
    make_question,
    make_session,
)
from tests.fakes.assessment_repository import InMemoryAssessmentRepository
from tests.fakes.kst_engine import FakeKstEngine


def _command() -> CreateAssessmentCommand:
    return CreateAssessmentCommand(
        user_id="user-1",
        learning_path_id="path-1",
        nodes=("B", "A"),
        relations=(GraphRelation("A", "B"),),
        course="Physics",
        goal="Understand the graph",
    )


def _model_result(next_node: str = "A") -> ModelBuildResult:
    model = make_model()
    return ModelBuildResult(
        model=model,
        posterior=model.uniform_prior,
        next_node=next_node,
    )


def _service(
    repository: InMemoryAssessmentRepository,
    engine: FakeKstEngine,
) -> AssessmentService:
    return AssessmentService(
        repository,
        engine,
        max_graph_nodes=10,
        now_factory=lambda: NOW,
    )


async def _pending_repository() -> InMemoryAssessmentRepository:
    graph = normalize_graph(
        ("B", "A"),
        (GraphRelation("A", "B"),),
        max_nodes=10,
    )
    repository = InMemoryAssessmentRepository()
    await repository.seed_session(
        replace(
            make_preparing_session(),
            graph_hash=None,
            player_state=PlayerState.new(pending_graph=make_pending_graph(graph)),
        )
    )
    return repository


def test_covered_creation_builds_caches_and_activates() -> None:
    async def scenario() -> None:
        repository = InMemoryAssessmentRepository()
        await repository.seed_items(make_item(), make_item(NEXT_ITEM_ID, node="B"))
        engine = FakeKstEngine(model_results=(_model_result(),))

        result = await _service(repository, engine).create_assessment(_command())
        test_id = TestId(result.test_id)
        session = repository.session_snapshot[test_id]
        state = session.player_state

        assert result.status is SessionStatus.ACTIVE
        assert result.missing_nodes == ()
        assert result.player_url == f"/test/{result.test_id}"
        assert session.status is SessionStatus.ACTIVE
        assert isinstance(state, PlayerState)
        assert state.current_question is not None
        assert state.current_question.node == "A"
        assert session.graph_hash in repository.graph_snapshot
        assert [call.method for call in engine.calls] == ["build_model"]

    asyncio.run(scenario())


def test_missing_creation_persists_pending_graph_and_one_yg_order() -> None:
    async def scenario() -> None:
        repository = InMemoryAssessmentRepository()
        await repository.seed_items(make_item())
        engine = FakeKstEngine()
        service = _service(repository, engine)

        result = await service.create_assessment(_command())
        test_id = TestId(result.test_id)
        await service.start_assessment(test_id)
        session = repository.session_snapshot[test_id]
        state = session.player_state
        orders = repository.yg_order_snapshot[test_id]

        assert result.status is SessionStatus.PREPARING
        assert result.missing_nodes == ("B",)
        assert session.graph_hash is None
        assert isinstance(state, PlayerState)
        assert state.pending_graph is not None
        assert len(orders) == 1
        assert orders[0].course == "Physics"
        assert orders[0].nodes == ("B",)
        assert orders[0].cognitive_level == "mõistab"
        assert orders[0].volume == 3
        assert engine.calls == ()

    asyncio.run(scenario())


def test_start_activates_pending_graph_and_is_stable_under_concurrency() -> None:
    async def scenario() -> None:
        repository = await _pending_repository()
        await repository.seed_items(make_item(), make_item(NEXT_ITEM_ID, node="B"))
        engine = FakeKstEngine(model_results=(_model_result(),))
        service = _service(repository, engine)

        first, second = await asyncio.gather(
            service.start_assessment(TEST_ID),
            service.start_assessment(TEST_ID),
        )
        session = repository.session_snapshot[TEST_ID]
        state = session.player_state

        assert first == second
        assert first.status is SessionStatus.ACTIVE
        assert first.question is not None
        assert session.graph_hash is not None
        assert isinstance(state, PlayerState)
        assert state.pending_graph is None
        assert session.graph_hash in repository.graph_snapshot
        assert [call.method for call in engine.calls] == ["build_model"]

    asyncio.run(scenario())


def test_start_uses_cached_states_and_marks_failed_yg() -> None:
    async def cached_scenario() -> None:
        graph = normalize_graph(
            ("A", "B"),
            (GraphRelation("A", "B"),),
            max_nodes=10,
        )
        cached = GraphCacheEntry(
            graph_hash=graph_hash(graph),
            graph=graph,
            knowledge_states=make_model().knowledge_states,
        )
        repository = InMemoryAssessmentRepository()
        await repository.seed_graph(cached)
        await repository.seed_items(make_item(), make_item(NEXT_ITEM_ID, node="B"))
        await repository.seed_session(
            replace(
                make_preparing_session(),
                graph_hash=cached.graph_hash,
                player_state=PlayerState.new(),
            )
        )
        engine = FakeKstEngine(model_results=(_model_result(),))

        await _service(repository, engine).start_assessment(TEST_ID)

        assert engine.calls[0].arguments[2] == cached.knowledge_states

    async def failed_scenario() -> None:
        repository = await _pending_repository()
        await repository.seed_yg_order(
            YgOrder(
                order_id=None,
                test_id=TEST_ID,
                course="",
                nodes=("B",),
                cognitive_level="mõistab",
                volume=3,
                status=YgStatus.FAILED,
            )
        )
        with pytest.raises(AssessmentConflict, match="preparation failed"):
            await _service(repository, FakeKstEngine()).start_assessment(TEST_ID)
        assert repository.session_snapshot[TEST_ID].status is SessionStatus.FAILED

    asyncio.run(cached_scenario())
    asyncio.run(failed_scenario())


def test_answer_is_scored_server_side_and_advances_to_safe_question() -> None:
    async def scenario() -> None:
        repository = InMemoryAssessmentRepository()
        await repository.seed_items(make_item(), make_item(NEXT_ITEM_ID, node="B"))
        await repository.seed_session(make_session())
        engine = FakeKstEngine(
            advance_results=(
                AdvanceInProgress(
                    posterior=(0.1, 0.2, 0.7),
                    next_node="B",
                ),
            )
        )

        view = await _service(repository, engine).submit_answer(
            TEST_ID,
            SUBMISSION_ID,
            OptionId("option-1"),
        )

        assert view.status is SessionStatus.ACTIVE
        assert view.question is not None
        output = view.question.model_dump(mode="json")
        assert set(output) == {
            "submission_id",
            "item_id",
            "instruction",
            "prompt",
            "stimulus",
            "options",
        }
        assert "node" not in str(output)
        call = engine.calls[0]
        assert call.method == "advance"
        assert call.arguments[3] is True
        assert call.arguments[4] == 1
        answer = repository.answer_snapshot[SUBMISSION_ID]
        assert answer.score == 1
        assert answer.selected_answer == "Correct"

    asyncio.run(scenario())


def test_incorrect_answer_completes_and_maps_every_feedback_category() -> None:
    async def scenario() -> None:
        repository = InMemoryAssessmentRepository()
        await repository.seed_items(make_item())
        await repository.seed_session(make_session())
        profile = replace(
            make_profile(),
            ready_to_learn=("B",),
            uncertain_ahead=("C",),
            uncertain_prerequisite=("D",),
            not_yet=("E",),
            summary="Done",
            stop_reason=StopReason.SAFETY_CAP,
        )
        engine = FakeKstEngine(
            advance_results=(
                AdvanceCompleted(
                    posterior=(0.05, 0.15, 0.8),
                    profile=profile,
                ),
            )
        )

        view = await _service(repository, engine).submit_answer(
            TEST_ID,
            SUBMISSION_ID,
            OptionId("option-2"),
        )

        assert view.status is SessionStatus.COMPLETED
        assert view.question is None
        assert view.feedback == feedback_from_profile(profile)
        assert view.feedback is not None
        assert view.feedback.already_mastered == ("A",)
        assert view.feedback.learn_next == ("B", "C")
        assert view.feedback.review == ("D",)
        assert view.feedback.confidence_limited is True
        answer = repository.answer_snapshot[SUBMISSION_ID]
        assert answer.score == 0
        assert engine.calls[0].arguments[3] is False

    asyncio.run(scenario())


def test_accepted_replay_returns_persisted_view_without_r_or_item_calls() -> None:
    async def scenario() -> None:
        accepted = AnsweredItem(
            submission_id=SUBMISSION_ID,
            item_id=ItemId(41),
            node="A",
            response_correct=True,
        )
        repository = InMemoryAssessmentRepository()
        await repository.seed_session(
            make_session(
                current_question=make_question(
                    NEXT_SUBMISSION_ID, NEXT_ITEM_ID, node="B"
                ),
                answered_items=(accepted,),
            )
        )
        engine = FakeKstEngine()

        view = await _service(repository, engine).submit_answer(
            TEST_ID,
            SUBMISSION_ID,
            OptionId("changed-option"),
        )

        assert view.question is not None
        assert view.question.submission_id == NEXT_SUBMISSION_ID
        assert engine.calls == ()
        assert not any(call.method == "get_item" for call in repository.calls)

    asyncio.run(scenario())


def test_concurrent_duplicate_answers_return_the_same_persisted_transition() -> None:
    async def scenario() -> None:
        repository = InMemoryAssessmentRepository()
        await repository.seed_items(make_item(), make_item(NEXT_ITEM_ID, node="B"))
        await repository.seed_session(make_session())
        advance = AdvanceInProgress(
            posterior=(0.1, 0.2, 0.7),
            next_node="B",
        )
        engine = FakeKstEngine(advance_results=(advance, advance))
        service = _service(repository, engine)

        first, second = await asyncio.gather(
            service.submit_answer(
                TEST_ID,
                SUBMISSION_ID,
                OptionId("option-1"),
            ),
            service.submit_answer(
                TEST_ID,
                SUBMISSION_ID,
                OptionId("option-1"),
            ),
        )

        assert first == second
        assert len(repository.answer_snapshot) == 1
        assert repository.item_snapshot[ItemId(41)].usage_count == 1

    asyncio.run(scenario())


def test_interrupted_identical_write_recovers_session_transition() -> None:
    async def scenario() -> None:
        repository = InMemoryAssessmentRepository()
        await repository.seed_items(make_item(), make_item(NEXT_ITEM_ID, node="B"))
        await repository.seed_session(make_session())
        await repository.seed_answer(make_answer())
        engine = FakeKstEngine(
            advance_results=(
                AdvanceInProgress(
                    posterior=(0.1, 0.2, 0.7),
                    next_node="B",
                ),
            )
        )

        view = await _service(repository, engine).submit_answer(
            TEST_ID,
            SUBMISSION_ID,
            OptionId("option-1"),
        )

        assert view.status is SessionStatus.ACTIVE
        assert view.question is not None
        state = repository.session_snapshot[TEST_ID].player_state
        assert isinstance(state, PlayerState)
        assert len(state.answered_items) == 1

    asyncio.run(scenario())


def test_stale_and_unavailable_options_are_rejected_before_r() -> None:
    async def scenario() -> None:
        repository = InMemoryAssessmentRepository()
        await repository.seed_session(make_session())
        engine = FakeKstEngine()
        service = _service(repository, engine)

        with pytest.raises(AssessmentConflict, match="stale"):
            await service.submit_answer(
                TEST_ID,
                NEXT_SUBMISSION_ID,
                OptionId("option-1"),
            )
        with pytest.raises(AssessmentConflict, match="unavailable"):
            await service.submit_answer(
                TEST_ID,
                SUBMISSION_ID,
                OptionId("not-persisted"),
            )
        assert engine.calls == ()
        assert repository.answer_snapshot == {}

    asyncio.run(scenario())


def test_interrupted_write_changed_option_is_a_payload_conflict() -> None:
    async def scenario() -> None:
        repository = InMemoryAssessmentRepository()
        await repository.seed_items(make_item(), make_item(NEXT_ITEM_ID, node="B"))
        await repository.seed_session(make_session())
        await repository.seed_answer(make_answer())
        engine = FakeKstEngine(
            advance_results=(
                AdvanceInProgress(
                    posterior=(0.1, 0.2, 0.7),
                    next_node="B",
                ),
            )
        )

        with pytest.raises(AssessmentConflict, match="payload conflicts"):
            await _service(repository, engine).submit_answer(
                TEST_ID,
                SUBMISSION_ID,
                OptionId("option-2"),
            )
        state = repository.session_snapshot[TEST_ID].player_state
        assert isinstance(state, PlayerState)
        assert state.current_question == make_question()

    asyncio.run(scenario())


def test_r_failure_does_not_persist_or_advance_and_unknown_test_is_distinct() -> None:
    async def scenario() -> None:
        repository = InMemoryAssessmentRepository()
        await repository.seed_items(make_item())
        await repository.seed_session(make_session())
        before = repository.session_snapshot
        engine = FakeKstEngine()
        engine.fail_next("advance", RUnavailable("offline"))
        service = _service(repository, engine)

        with pytest.raises(RUnavailable):
            await service.submit_answer(
                TEST_ID,
                SUBMISSION_ID,
                OptionId("option-1"),
            )
        assert repository.answer_snapshot == {}
        assert repository.session_snapshot == before
        with pytest.raises(AssessmentNotFound):
            await service.start_assessment(TestId(NEXT_SUBMISSION_ID))

    asyncio.run(scenario())


def test_repository_commit_failure_leaves_fake_state_retryable() -> None:
    async def scenario() -> None:
        repository = InMemoryAssessmentRepository()
        await repository.seed_items(make_item())
        await repository.seed_session(make_session())
        before = repository.session_snapshot
        repository.fail_next("commit_answer")
        engine = FakeKstEngine(
            advance_results=(
                AdvanceCompleted(
                    posterior=(0.05, 0.15, 0.8),
                    profile=make_profile(),
                ),
            )
        )

        with pytest.raises(RuntimeError, match="injected"):
            await _service(repository, engine).submit_answer(
                TEST_ID,
                SUBMISSION_ID,
                OptionId("option-1"),
            )
        assert repository.answer_snapshot == {}
        assert repository.session_snapshot == before

    asyncio.run(scenario())
