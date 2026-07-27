"""Assessment creation, activation, answering, and player-safe views."""

import asyncio
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain.graphs import graph_hash, make_pending_graph, normalize_graph
from app.domain.models import *
from app.domain.repository import AssessmentRepository, RepositoryDataError
from app.integrations.kst_engine import KstEngine

from .questions import QuestionOutput, RandomSource, build_question, to_question_output


class AssessmentServiceError(RuntimeError):
    """Base class for stable service failures mapped by the future API layer."""


class AssessmentNotFound(AssessmentServiceError):
    """The requested assessment does not exist."""


class AssessmentConflict(AssessmentServiceError):
    """The requested operation conflicts with persisted assessment state."""


@dataclass(frozen=True, slots=True)
class CreateAssessmentCommand:
    user_id: str
    learning_path_id: str
    nodes: tuple[str, ...]
    relations: tuple[GraphRelation, ...]
    course: str = ""
    goal: str | None = None
    method: AssessmentMethod = AssessmentMethod.KST
    cognitive_level: str = "mõistab"


@dataclass(frozen=True, slots=True)
class CreateAssessmentResult:
    test_id: UUID
    status: SessionStatus
    player_url: str
    missing_nodes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Feedback:
    already_mastered: tuple[str, ...]
    learn_next: tuple[str, ...]
    review: tuple[str, ...]
    summary: str | None
    confidence_limited: bool


@dataclass(frozen=True, slots=True)
class AssessmentView:
    status: SessionStatus
    question: QuestionOutput | None = None
    feedback: Feedback | None = None


class AssessmentService:
    """Coordinate persistence and R without exposing either implementation."""

    def __init__(
        self,
        repository: AssessmentRepository,
        engine: KstEngine,
        *,
        max_graph_nodes: int,
        random_source: RandomSource | None = None,
        uuid_factory: Callable[[], UUID] = uuid4,
        now_factory: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._engine = engine
        self._max_graph_nodes = max_graph_nodes
        self._random_source = random_source
        self._uuid_factory = uuid_factory
        self._now_factory = now_factory or (lambda: datetime.now(UTC))
        self._start_locks: defaultdict[TestId, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def create_assessment(
        self, command: CreateAssessmentCommand
    ) -> CreateAssessmentResult:
        """Create an active assessment or one restart-safe preparation."""

        if command.method is not AssessmentMethod.KST:
            raise AssessmentConflict("unsupported assessment method")
        graph = normalize_graph(
            command.nodes,
            command.relations,
            max_nodes=self._max_graph_nodes,
        )
        identifier = graph_hash(graph)
        cached = await self._repository.get_cached_graph(identifier)
        coverage = await self._repository.resolve_usable_coverage(graph.nodes)
        missing_nodes = tuple(
            entry.node for entry in coverage if entry.parameters is None
        )
        test_id = TestId(self._uuid_factory())

        if missing_nodes:
            session = AssessmentSession(
                test_id=test_id,
                user_id=command.user_id,
                learning_path_id=LearningPathId(command.learning_path_id),
                graph_hash=identifier if cached is not None else None,
                status=SessionStatus.PREPARING,
                started_at=self._now(),
                method=command.method,
                player_state=PlayerState.new(
                    pending_graph=make_pending_graph(graph) if cached is None else None
                ),
                goal=command.goal,
            )
            await self._repository.create_session(session)
            await self._repository.create_yg_order_if_no_pending(
                YgOrder(
                    order_id=None,
                    test_id=test_id,
                    course=command.course,
                    nodes=missing_nodes,
                    cognitive_level=command.cognitive_level,
                    volume=3,
                    status=YgStatus.PENDING,
                )
            )
            return self._creation_result(
                test_id, SessionStatus.PREPARING, missing_nodes
            )

        parameters = self._covered_parameters(coverage)
        built = await self._engine.build_model(
            graph,
            parameters,
            None if cached is None else cached.knowledge_states,
        )
        self._validate_model_build(graph, built)
        if cached is None:
            await self._repository.insert_cached_graph_if_absent(
                GraphCacheEntry(
                    graph_hash=identifier,
                    graph=graph,
                    knowledge_states=built.model.knowledge_states,
                )
            )
        first_question = await self._question_for_node(
            built.next_node,
            used_item_ids=(),
        )
        session = AssessmentSession(
            test_id=test_id,
            user_id=command.user_id,
            learning_path_id=LearningPathId(command.learning_path_id),
            graph_hash=identifier,
            status=SessionStatus.ACTIVE,
            started_at=self._now(),
            method=command.method,
            player_state=PlayerState.new(
                posterior=built.posterior,
                current_question=first_question,
            ),
            model=built.model,
            goal=command.goal,
        )
        await self._repository.create_session(session)
        return self._creation_result(test_id, SessionStatus.ACTIVE, ())

    async def start_assessment(self, test_id: TestId) -> AssessmentView:
        """Start once coverage exists and otherwise return a preparing view."""

        async with self._start_locks[test_id]:
            session = await self._require_session(test_id)
            if session.is_legacy:
                raise AssessmentConflict("legacy assessment cannot be resumed")
            if session.status is SessionStatus.FAILED:
                raise AssessmentConflict("assessment preparation failed")
            if session.status in (SessionStatus.ACTIVE, SessionStatus.COMPLETED):
                return self._view(session)
            if session.status is not SessionStatus.PREPARING:
                raise AssessmentConflict("assessment cannot be started")

            order = await self._repository.get_latest_yg_order(test_id)
            if order is not None and order.status is YgStatus.FAILED:
                await self._repository.mark_session_failed(test_id)
                raise AssessmentConflict("assessment preparation failed")

            graph, identifier, cached = await self._preparing_graph(session)
            coverage = await self._repository.resolve_usable_coverage(graph.nodes)
            if any(entry.parameters is None for entry in coverage):
                return AssessmentView(status=SessionStatus.PREPARING)

            built = await self._engine.build_model(
                graph,
                self._covered_parameters(coverage),
                None if cached is None else cached.knowledge_states,
            )
            self._validate_model_build(graph, built)
            if cached is None:
                await self._repository.insert_cached_graph_if_absent(
                    GraphCacheEntry(
                        graph_hash=identifier,
                        graph=graph,
                        knowledge_states=built.model.knowledge_states,
                    )
                )
            first_question = await self._question_for_node(
                built.next_node,
                used_item_ids=(),
            )
            activated = await self._repository.activate_session(
                ActivationCommand(
                    test_id=test_id,
                    graph_hash=identifier,
                    model=built.model,
                    first_question=first_question,
                )
            )
            return self._view(activated)

    async def submit_answer(
        self,
        test_id: TestId,
        submission_id: SubmissionId,
        option_id: OptionId,
    ) -> AssessmentView:
        """Score one persisted option and commit the R transition idempotently."""

        session = await self._require_session(test_id)
        state = self._player_state(session)
        if any(
            answered.submission_id == submission_id for answered in state.answered_items
        ):
            return self._view(session)
        if session.status is not SessionStatus.ACTIVE:
            raise AssessmentConflict("assessment does not accept answers")
        question = state.current_question
        model = session.model
        if question is None or model is None:
            raise AssessmentConflict("assessment has no current question")
        if question.submission_id != submission_id:
            raise AssessmentConflict("stale submission")

        selected = next(
            (
                option.text
                for option in question.options
                if option.option_id == option_id
            ),
            None,
        )
        if selected is None:
            raise AssessmentConflict("option is unavailable")
        item = await self._repository.get_item(question.item_id)
        if item is None:
            raise RepositoryDataError(f"unknown item: {question.item_id}")
        if item.node != question.node:
            raise RepositoryDataError("persisted question item node changed")
        response_correct = selected == item.answer_key
        advanced = await self._engine.advance(
            model,
            state.posterior,
            question.node,
            response_correct,
            len(state.answered_items) + 1,
        )
        answered = AnsweredItem(
            submission_id=submission_id,
            item_id=question.item_id,
            node=question.node,
            response_correct=response_correct,
        )
        if isinstance(advanced, AdvanceInProgress):
            used_ids = tuple(previous.item_id for previous in state.answered_items) + (
                question.item_id,
            )
            next_question = await self._question_for_node(
                advanced.next_node,
                used_item_ids=used_ids,
            )
            transition = AnswerTransition(
                next_player_state=PlayerState(
                    schema_version=PLAYER_STATE_SCHEMA_VERSION,
                    posterior=advanced.posterior,
                    answered_items=state.answered_items + (answered,),
                    current_question=next_question,
                )
            )
        else:
            transition = AnswerTransition(
                next_player_state=PlayerState(
                    schema_version=PLAYER_STATE_SCHEMA_VERSION,
                    posterior=advanced.posterior,
                    answered_items=state.answered_items + (answered,),
                    current_question=None,
                ),
                final_profile=advanced.profile,
            )
        committed = await self._repository.commit_answer(
            submission_id,
            AnswerRecord(
                submission_id=submission_id,
                test_id=test_id,
                item_id=question.item_id,
                score=1 if response_correct else 0,
                selected_answer=selected,
                answered_at=self._now(),
            ),
            transition,
        )
        if committed.outcome in (
            AnswerCommitOutcome.STALE,
            AnswerCommitOutcome.PAYLOAD_CONFLICT,
        ):
            raise AssessmentConflict(
                "stale submission"
                if committed.outcome is AnswerCommitOutcome.STALE
                else "submission payload conflicts with an earlier attempt"
            )
        return self._view(committed.session)

    async def _preparing_graph(
        self, session: AssessmentSession
    ) -> tuple[GraphDefinition, str, GraphCacheEntry | None]:
        state = self._player_state(session)
        pending = state.pending_graph
        if pending is not None:
            cached = await self._repository.get_cached_graph(pending.graph_hash)
            return pending.graph, pending.graph_hash, cached
        if session.graph_hash is None:
            raise RepositoryDataError("preparing session has no graph")
        cached = await self._repository.get_cached_graph(session.graph_hash)
        if cached is None:
            raise RepositoryDataError("preparing session references a missing graph")
        return cached.graph, cached.graph_hash, cached

    async def _question_for_node(
        self,
        node: str,
        *,
        used_item_ids: tuple[ItemId, ...],
    ) -> CurrentQuestion:
        items = await self._repository.list_usable_items(node, used_item_ids)
        if not items:
            raise RepositoryDataError(f"no usable item for node: {node}")
        return build_question(
            items[0],
            random_source=self._random_source,
            uuid_factory=self._uuid_factory,
        )

    async def _require_session(self, test_id: TestId) -> AssessmentSession:
        session = await self._repository.get_session(test_id)
        if session is None:
            raise AssessmentNotFound("assessment not found")
        return session

    @staticmethod
    def _player_state(session: AssessmentSession) -> PlayerState:
        if not isinstance(session.player_state, PlayerState):
            raise AssessmentConflict("legacy assessment cannot be resumed")
        return session.player_state

    @staticmethod
    def _covered_parameters(
        coverage: tuple[NodeCoverage, ...],
    ) -> tuple[NodeParameters, ...]:
        parameters: list[NodeParameters] = []
        for entry in coverage:
            if entry.parameters is None:
                raise RepositoryDataError("coverage unexpectedly incomplete")
            parameters.append(entry.parameters)
        return tuple(parameters)

    @staticmethod
    def _validate_model_build(graph: GraphDefinition, built: ModelBuildResult) -> None:
        if built.model.nodes != graph.nodes:
            raise RepositoryDataError("R model nodes do not match graph")
        if built.posterior != built.model.uniform_prior:
            raise RepositoryDataError("R initial posterior does not match model prior")
        if built.next_node not in graph.nodes:
            raise RepositoryDataError("R next node is outside graph")

    @staticmethod
    def _view(session: AssessmentSession) -> AssessmentView:
        state = AssessmentService._player_state(session)
        if session.status is SessionStatus.ACTIVE:
            if state.current_question is None:
                raise RepositoryDataError("active assessment has no question")
            return AssessmentView(
                status=SessionStatus.ACTIVE,
                question=to_question_output(state.current_question),
            )
        if session.status is SessionStatus.COMPLETED:
            if session.final_profile is None:
                raise RepositoryDataError("completed assessment has no profile")
            return AssessmentView(
                status=SessionStatus.COMPLETED,
                feedback=feedback_from_profile(session.final_profile),
            )
        return AssessmentView(status=session.status)

    @staticmethod
    def _creation_result(
        test_id: TestId,
        status: SessionStatus,
        missing_nodes: tuple[str, ...],
    ) -> CreateAssessmentResult:
        value = UUID(str(test_id))
        return CreateAssessmentResult(
            test_id=value,
            status=status,
            player_url=f"/test/{value}",
            missing_nodes=missing_nodes,
        )

    def _now(self) -> datetime:
        value = self._now_factory()
        if value.tzinfo is None:
            raise ValueError("now_factory must return a timezone-aware datetime")
        return value


def feedback_from_profile(profile: FinalProfile) -> Feedback:
    """Map internal five-way KST output to the three public sections."""

    return Feedback(
        already_mastered=profile.mastered,
        learn_next=profile.ready_to_learn + profile.uncertain_ahead,
        review=profile.uncertain_prerequisite,
        summary=profile.summary,
        confidence_limited=profile.stop_reason is StopReason.SAFETY_CAP,
    )
