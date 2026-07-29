"""Candidate-aware assessment creation, activation, answering, and safe views."""

import asyncio
import logging
import math
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.domain.graphs import graph_hash, normalize_graph
from app.domain.models import *
from app.domain.repository import AssessmentRepository, RepositoryDataError
from app.integrations.kst_engine import KstEngine

from .questions import QuestionOutput, RandomSource, build_question, to_question_output

logger = logging.getLogger(__name__)

MINIMUM_VALID_ITEMS_PER_NODE = 3
MAX_GENERATED_ITEMS_PER_NODE_REQUEST = 3


class AssessmentServiceError(RuntimeError):
    """Base class for stable service failures mapped by the API layer."""


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
    """Coordinate fixed item pools, persistence, and candidate-aware R calls."""

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
        if command.method is not AssessmentMethod.KST:
            raise AssessmentConflict("unsupported assessment method")
        graph = normalize_graph(
            command.nodes,
            command.relations,
            max_nodes=self._max_graph_nodes,
        )
        identifier = graph_hash(graph)
        cached = await self._repository.get_cached_graph(identifier)
        built = await self._engine.build_model(
            graph,
            None if cached is None else cached.knowledge_states,
        )
        self._validate_model_build(graph, built)
        if cached is None:
            cached = await self._repository.insert_cached_graph_if_absent(
                GraphCacheEntry(
                    graph_hash=identifier,
                    graph=graph,
                    knowledge_states=built.model.knowledge_states,
                )
            )
        items = await self._repository.list_usable_items_for_nodes(graph.nodes)
        plan = self._inventory_plan(graph.nodes, items)
        test_id = TestId(self._uuid_factory())
        if plan.requests:
            session = AssessmentSession(
                test_id=test_id,
                user_id=command.user_id,
                learning_path_id=LearningPathId(command.learning_path_id),
                graph_hash=identifier,
                status=SessionStatus.PREPARING,
                started_at=self._now(),
                method=command.method,
                player_state=PlayerState.new(
                    posterior=built.posterior,
                    inventory_plan=plan,
                ),
                model=built.model,
                goal=command.goal,
            )
            await self._repository.create_session(session)
            await self._repository.create_yg_order_if_no_pending(
                self._yg_order(
                    test_id,
                    command.course,
                    command.cognitive_level,
                    plan.requests,
                )
            )
            return self._creation_result(
                test_id,
                SessionStatus.PREPARING,
                tuple(request.node for request in plan.requests),
            )

        pool = self._snapshot_pool(graph.nodes, built.model, items, plan)
        first_question = await self._first_question(
            built.model, built.posterior, pool
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
                session_pool=pool,
            ),
            model=built.model,
            goal=command.goal,
        )
        await self._repository.create_session(session)
        return self._creation_result(test_id, SessionStatus.ACTIVE, ())

    async def get_assessment(self, test_id: TestId) -> AssessmentView:
        session = await self._require_session(test_id)
        if session.is_legacy and session.status is not SessionStatus.COMPLETED:
            raise AssessmentConflict("v1 assessment cannot be resumed")
        return self._view(session)

    async def start_assessment(self, test_id: TestId) -> AssessmentView:
        async with self._start_locks[test_id]:
            session = await self._require_session(test_id)
            if session.is_legacy:
                if session.status is SessionStatus.COMPLETED:
                    return self._view(session)
                raise AssessmentConflict("v1 assessment cannot be resumed")
            if session.status in (SessionStatus.ACTIVE, SessionStatus.COMPLETED):
                return self._view(session)
            if session.status is SessionStatus.FAILED:
                raise AssessmentConflict("assessment preparation failed")
            if session.status is not SessionStatus.PREPARING:
                raise AssessmentConflict("assessment cannot be started")
            state = self._player_state(session)
            if not isinstance(session.model, KstModel):
                raise RepositoryDataError("preparing v2 session has no v2 model")
            if session.graph_hash is None:
                raise RepositoryDataError("preparing session has no graph")
            cached = await self._repository.get_cached_graph(session.graph_hash)
            if cached is None:
                raise RepositoryDataError("preparing session references a missing graph")

            items = await self._repository.list_usable_items_for_nodes(
                cached.graph.nodes
            )
            plan = self._inventory_plan(cached.graph.nodes, items)
            if plan.requests:
                if state.inventory_plan != plan:
                    state = PlayerState(
                        schema_version=PLAYER_STATE_SCHEMA_VERSION,
                        posterior=state.posterior,
                        answered_items=state.answered_items,
                        current_question=None,
                        inventory_plan=plan,
                    )
                    await self._repository.update_preparing_inventory_plan(
                        test_id, state
                    )
                latest = await self._repository.get_latest_yg_order(test_id)
                if latest is None or latest.status not in (
                    YgStatus.PENDING,
                    YgStatus.PROCESSING,
                ):
                    await self._repository.create_yg_order_if_no_pending(
                        self._yg_order(
                            test_id,
                            "" if latest is None else latest.course,
                            None if latest is None else latest.cognitive_level,
                            plan.requests,
                        )
                    )
                return AssessmentView(status=SessionStatus.PREPARING)

            pool = self._snapshot_pool(
                cached.graph.nodes, session.model, items, plan
            )
            first_question = await self._first_question(
                session.model, state.posterior, pool
            )
            activated = await self._repository.activate_session(
                ActivationCommand(
                    test_id=test_id,
                    graph_hash=session.graph_hash,
                    model=session.model,
                    first_question=first_question,
                    session_pool=pool,
                )
            )
            return self._view(activated)

    async def submit_answer(
        self,
        test_id: TestId,
        submission_id: SubmissionId,
        option_id: OptionId,
    ) -> AssessmentView:
        session = await self._require_session(test_id)
        if session.is_legacy:
            raise AssessmentConflict("v1 assessment cannot be resumed")
        state = self._player_state(session)
        if any(
            answered.submission_id == submission_id for answered in state.answered_items
        ):
            return self._view(session)
        if session.status is not SessionStatus.ACTIVE:
            raise AssessmentConflict("assessment does not accept answers")
        question = state.current_question
        model = session.model
        pool = state.session_pool
        if question is None or not isinstance(model, KstModel) or pool is None:
            raise AssessmentConflict("assessment has no current question")
        if question.submission_id != submission_id:
            raise AssessmentConflict("stale submission")
        selected = next(
            (option for option in question.options if option.option_id == option_id),
            None,
        )
        if selected is None:
            raise AssessmentConflict("option is unavailable")
        if any(answer.item_id == question.item_id for answer in state.answered_items):
            raise RepositoryDataError("current item is already in answer history")
        response_correct = option_id == question.correct_option_id
        administered = ItemCandidate(
            candidate_id=question.candidate_id,
            item_id=question.item_id,
            node=question.node,
            beta=question.beta,
            eta=question.eta,
        )
        remaining = await self._remaining_candidates(state)
        advanced = await self._engine.advance(
            model,
            state.posterior,
            administered,
            response_correct,
            len(state.answered_items) + 1,
            remaining,
        )
        answered = AnsweredItem(
            submission_id=submission_id,
            item_id=question.item_id,
            node=question.node,
            response_correct=response_correct,
        )
        if isinstance(advanced, AdvanceInProgress):
            candidate = self._verify_selection(
                advanced.next_candidate, remaining
            )
            next_question = await self._question_for_candidate(candidate)
            next_state = PlayerState(
                schema_version=PLAYER_STATE_SCHEMA_VERSION,
                posterior=advanced.posterior,
                answered_items=state.answered_items + (answered,),
                current_question=next_question,
                session_pool=pool,
            )
            transition = AnswerTransition(next_player_state=next_state)
        else:
            next_state = PlayerState(
                schema_version=PLAYER_STATE_SCHEMA_VERSION,
                posterior=advanced.posterior,
                answered_items=state.answered_items + (answered,),
                current_question=None,
                session_pool=pool,
            )
            transition = AnswerTransition(
                next_player_state=next_state,
                final_profile=advanced.profile,
            )
            if advanced.profile.stop_reason is StopReason.ITEM_INVENTORY_EXHAUSTED:
                logger.warning(
                    "item_inventory_exhausted",
                    extra={
                        "test_id": str(test_id),
                        "safety_cap": model.derived_limits.safety_cap,
                        "response_count": len(next_state.answered_items),
                        "original_pool_size": len(pool.candidates),
                        "remaining_usable_count": len(remaining),
                    },
                )
        committed = await self._repository.commit_answer(
            submission_id,
            AnswerRecord(
                submission_id=submission_id,
                test_id=test_id,
                item_id=question.item_id,
                score=1 if response_correct else 0,
                selected_answer=selected.text,
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

    async def _first_question(
        self,
        model: KstModel,
        posterior: tuple[float, ...],
        pool: SessionPool,
    ) -> CurrentQuestion:
        selected = await self._engine.select(model, posterior, pool.candidates)
        return await self._question_for_candidate(
            self._verify_selection(selected, pool.candidates)
        )

    async def _question_for_candidate(
        self, candidate: ItemCandidate
    ) -> CurrentQuestion:
        loaded = await self._repository.load_items_by_ids((candidate.item_id,))
        if len(loaded) != 1:
            raise RepositoryDataError(
                f"selected pool item is not usable: {candidate.item_id}"
            )
        item = loaded[0]
        self._validate_item_matches_candidate(item, candidate)
        return build_question(
            item,
            candidate=candidate,
            random_source=self._random_source,
            uuid_factory=self._uuid_factory,
        )

    async def _remaining_candidates(
        self, state: PlayerState
    ) -> tuple[ItemCandidate, ...]:
        if state.session_pool is None or state.current_question is None:
            raise RepositoryDataError("active state has no pool or current question")
        excluded = {
            state.current_question.item_id,
            *(answer.item_id for answer in state.answered_items),
        }
        eligible = tuple(
            candidate
            for candidate in state.session_pool.candidates
            if candidate.item_id not in excluded
        )
        loaded = await self._repository.load_items_by_ids(
            tuple(candidate.item_id for candidate in eligible)
        )
        loaded_by_id = {item.item_id: item for item in loaded}
        remaining: list[ItemCandidate] = []
        for candidate in eligible:
            item = loaded_by_id.get(candidate.item_id)
            if item is None:
                continue
            self._validate_item_matches_candidate(item, candidate)
            remaining.append(candidate)
        return tuple(remaining)

    @staticmethod
    def _inventory_plan(
        nodes: tuple[str, ...],
        items: tuple[AssessmentItem, ...],
    ) -> InventoryPlan:
        counts = Counter(item.node for item in items)
        requests = tuple(
            InventoryRequest(
                node=node,
                amount=min(
                    MAX_GENERATED_ITEMS_PER_NODE_REQUEST,
                    MINIMUM_VALID_ITEMS_PER_NODE - counts[node],
                ),
            )
            for node in nodes
            if counts[node] < MINIMUM_VALID_ITEMS_PER_NODE
        )
        return InventoryPlan(
            required_per_node=MINIMUM_VALID_ITEMS_PER_NODE,
            requests=requests,
        )

    @staticmethod
    def _snapshot_pool(
        nodes: tuple[str, ...],
        model: KstModel,
        items: tuple[AssessmentItem, ...],
        plan: InventoryPlan,
    ) -> SessionPool:
        candidates = tuple(
            ItemCandidate(
                candidate_id=CandidateId(f"yp:{int(item.item_id)}"),
                item_id=item.item_id,
                node=item.node,
                beta=item.beta,
                eta=item.eta,
            )
            for item in items
        )
        item_ids = [candidate.item_id for candidate in candidates]
        candidate_ids = [candidate.candidate_id for candidate in candidates]
        if len(item_ids) != len(set(item_ids)):
            raise RepositoryDataError("activation pool contains duplicate item IDs")
        if len(candidate_ids) != len(set(candidate_ids)):
            raise RepositoryDataError("activation pool contains duplicate candidate IDs")
        if any(
            not str(candidate.candidate_id).strip()
            or not math.isfinite(candidate.beta)
            or not math.isfinite(candidate.eta)
            or not 0 <= candidate.beta <= 1
            or not 0 <= candidate.eta <= 1
            for candidate in candidates
        ):
            raise RepositoryDataError("activation pool has invalid candidate metadata")
        if any(candidate.node not in model.nodes for candidate in candidates):
            raise RepositoryDataError("activation pool contains a foreign node")
        counts = Counter(candidate.node for candidate in candidates)
        if any(counts[node] < plan.required_per_node for node in nodes):
            raise RepositoryDataError("activation pool does not meet per-node target")
        return SessionPool(candidates=candidates)

    @staticmethod
    def _verify_selection(
        selected: CandidateSelection,
        supplied: tuple[ItemCandidate, ...],
    ) -> ItemCandidate:
        matches = tuple(
            candidate
            for candidate in supplied
            if candidate.candidate_id == selected.candidate_id
            and candidate.node == selected.node
        )
        if len(matches) != 1:
            raise RepositoryDataError("R selected a candidate outside the supplied set")
        return matches[0]

    @staticmethod
    def _validate_item_matches_candidate(
        item: AssessmentItem, candidate: ItemCandidate
    ) -> None:
        if (
            item.item_id != candidate.item_id
            or item.node != candidate.node
            or item.beta != candidate.beta
            or item.eta != candidate.eta
        ):
            raise RepositoryDataError("pool metadata no longer matches the item bank")

    @staticmethod
    def _validate_model_build(
        graph: GraphDefinition, built: ModelBuildResult
    ) -> None:
        if built.model.schema_version != KST_MODEL_SCHEMA_VERSION:
            raise RepositoryDataError("R returned an unsupported model version")
        if built.model.nodes != graph.nodes:
            raise RepositoryDataError("R model nodes do not match graph")
        if built.posterior != built.model.uniform_prior:
            raise RepositoryDataError("R initial posterior does not match model prior")
        limits = built.model.derived_limits
        if limits.reliability_floor < 0 or limits.safety_cap < limits.reliability_floor:
            raise RepositoryDataError("R returned invalid derived limits")

    @staticmethod
    def _yg_order(
        test_id: TestId,
        course: str,
        cognitive_level: str | None,
        requests: tuple[InventoryRequest, ...],
    ) -> YgOrder:
        if any(
            request.amount > MAX_GENERATED_ITEMS_PER_NODE_REQUEST
            for request in requests
        ):
            raise RepositoryDataError(
                "YG item request exceeds the per-node generation limit"
            )
        return YgOrder(
            order_id=None,
            test_id=test_id,
            course=course,
            nodes=tuple(request.node for request in requests),
            cognitive_level=cognitive_level,
            volume=max((request.amount for request in requests), default=0),
            status=YgStatus.PENDING,
            item_requests=requests,
        )

    async def _require_session(self, test_id: TestId) -> AssessmentSession:
        session = await self._repository.get_session(test_id)
        if session is None:
            raise AssessmentNotFound("assessment not found")
        return session

    @staticmethod
    def _player_state(session: AssessmentSession) -> PlayerState:
        if not isinstance(session.player_state, PlayerState):
            raise AssessmentConflict("v1 assessment cannot be resumed")
        return session.player_state

    @staticmethod
    def _view(session: AssessmentSession) -> AssessmentView:
        if session.status is SessionStatus.COMPLETED:
            if session.final_profile is None:
                raise RepositoryDataError("completed assessment has no profile")
            return AssessmentView(
                status=SessionStatus.COMPLETED,
                feedback=feedback_from_profile(session.final_profile),
            )
        state = AssessmentService._player_state(session)
        if session.status is SessionStatus.ACTIVE:
            if state.current_question is None:
                raise RepositoryDataError("active assessment has no question")
            return AssessmentView(
                status=SessionStatus.ACTIVE,
                question=to_question_output(state.current_question),
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
    return Feedback(
        already_mastered=profile.mastered,
        learn_next=profile.ready_to_learn + profile.uncertain_ahead,
        review=profile.uncertain_prerequisite,
        summary=profile.summary,
        confidence_limited=profile.stop_reason
        in (StopReason.SAFETY_CAP, StopReason.ITEM_INVENTORY_EXHAUSTED),
    )
