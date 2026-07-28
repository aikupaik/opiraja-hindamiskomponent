"""Immutable domain values used at the assessment persistence boundary."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import math
from typing import NewType
from uuid import UUID

TestId = NewType("TestId", UUID)
SubmissionId = NewType("SubmissionId", UUID)
ItemId = NewType("ItemId", int)
YgOrderId = NewType("YgOrderId", int)
LearningPathId = NewType("LearningPathId", str)
OptionId = NewType("OptionId", str)
CandidateId = NewType("CandidateId", str)

PLAYER_STATE_SCHEMA_VERSION = 2
KST_MODEL_SCHEMA_VERSION = 2
KST_CONFIGURATION_SCHEMA_VERSION = 1


class SessionStatus(StrEnum):
    PREPARING = "preparing"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


class YgStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ItemStatus(StrEnum):
    DRAFT = "draft"
    USABLE = "usable"
    REVIEW = "review"
    ARCHIVED = "archived"


class AssessmentMethod(StrEnum):
    KST = "kst"


class StopReason(StrEnum):
    NATURAL = "natural"
    SAFETY_CAP = "safety_cap"
    ITEM_INVENTORY_EXHAUSTED = "item_inventory_exhausted"


class AnswerCommitOutcome(StrEnum):
    APPLIED = "applied"
    RECOVERED = "recovered"
    REPLAYED = "replayed"
    STALE = "stale"
    PAYLOAD_CONFLICT = "payload_conflict"


@dataclass(frozen=True, slots=True)
class GraphRelation:
    prerequisite: str
    dependent: str


@dataclass(frozen=True, slots=True)
class GraphDefinition:
    nodes: tuple[str, ...]
    relations: tuple[GraphRelation, ...]


@dataclass(frozen=True, slots=True)
class PendingGraph:
    graph_hash: str
    nodes: tuple[str, ...]
    relations: tuple[GraphRelation, ...]

    @property
    def graph(self) -> GraphDefinition:
        return GraphDefinition(nodes=self.nodes, relations=self.relations)


@dataclass(frozen=True, slots=True)
class KnowledgeState:
    nodes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GraphCacheEntry:
    graph_hash: str
    graph: GraphDefinition
    knowledge_states: tuple[KnowledgeState, ...]
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AssessmentItem:
    item_id: ItemId
    node: str
    instruction: str
    prompt: str
    stimulus: str | None
    answer_key: str
    distractors: tuple[str, ...]
    beta: float
    eta: float
    status: ItemStatus = ItemStatus.USABLE
    usage_count: int = 0
    last_used_at: datetime | None = None


def is_domain_valid_usable_item(item: AssessmentItem) -> bool:
    choices = {
        value
        for value in (item.answer_key, *item.distractors)
        if value.strip()
    }
    return (
        item.status is ItemStatus.USABLE
        and bool(item.node.strip())
        and bool(item.instruction.strip())
        and bool(item.prompt.strip())
        and len(choices) >= 2
        and math.isfinite(item.beta)
        and math.isfinite(item.eta)
        and 0 <= item.beta <= 1
        and 0 <= item.eta <= 1
    )


@dataclass(frozen=True, slots=True)
class ItemCandidate:
    candidate_id: CandidateId
    item_id: ItemId
    node: str
    beta: float
    eta: float


@dataclass(frozen=True, slots=True)
class DerivedLimits:
    reliability_floor: int
    safety_cap: int


@dataclass(frozen=True, slots=True)
class InventoryRequest:
    node: str
    amount: int


@dataclass(frozen=True, slots=True)
class InventoryResult:
    node: str
    requested: int
    baseline_usable: int
    created: int
    usable_after: int
    remaining: int


@dataclass(frozen=True, slots=True)
class InventoryPlan:
    required_per_node: int
    requests: tuple[InventoryRequest, ...]


@dataclass(frozen=True, slots=True)
class SessionPool:
    candidates: tuple[ItemCandidate, ...]


@dataclass(frozen=True, slots=True)
class ReliabilityFloorConfiguration:
    minimum: int
    multiplier: float
    maximum: int


@dataclass(frozen=True, slots=True)
class SafetyCapConfiguration:
    node_multiplier: float
    responses_above_floor: int


@dataclass(frozen=True, slots=True)
class KstConfiguration:
    schema_version: int
    stop_confidence: float
    feedback_credible_mass: float
    reliability_floor: ReliabilityFloorConfiguration
    safety_cap: SafetyCapConfiguration


@dataclass(frozen=True, slots=True)
class KstModel:
    schema_version: int
    method: AssessmentMethod
    nodes: tuple[str, ...]
    knowledge_states: tuple[KnowledgeState, ...]
    matrix: tuple[tuple[int, ...], ...]
    uniform_prior: tuple[float, ...]
    configuration: KstConfiguration
    configuration_hash: str
    derived_limits: DerivedLimits


@dataclass(frozen=True, slots=True)
class LegacyKstModel:
    """Readable v1 model retained only for completed historical sessions."""

    schema_version: int
    method: AssessmentMethod
    nodes: tuple[str, ...]
    knowledge_states: tuple[KnowledgeState, ...]
    matrix: tuple[tuple[int, ...], ...]
    uniform_prior: tuple[float, ...]
    beta: tuple[float, ...]
    eta: tuple[float, ...]
    configuration: KstConfiguration
    configuration_hash: str


@dataclass(frozen=True, slots=True)
class FinalProfile:
    mastered: tuple[str, ...]
    ready_to_learn: tuple[str, ...]
    uncertain_ahead: tuple[str, ...]
    uncertain_prerequisite: tuple[str, ...]
    not_yet: tuple[str, ...]
    summary: str | None
    stop_reason: StopReason
    best_state_confidence: float
    credible_mass: float
    credible_state_count: int


@dataclass(frozen=True, slots=True)
class ModelBuildResult:
    model: KstModel
    posterior: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class CandidateSelection:
    candidate_id: CandidateId
    node: str


@dataclass(frozen=True, slots=True)
class AdvanceInProgress:
    posterior: tuple[float, ...]
    next_candidate: CandidateSelection


@dataclass(frozen=True, slots=True)
class AdvanceCompleted:
    posterior: tuple[float, ...]
    profile: FinalProfile


AdvanceResult = AdvanceInProgress | AdvanceCompleted


@dataclass(frozen=True, slots=True)
class AnsweredItem:
    submission_id: SubmissionId
    item_id: ItemId
    node: str
    response_correct: bool


@dataclass(frozen=True, slots=True)
class QuestionOption:
    option_id: OptionId
    text: str


@dataclass(frozen=True, slots=True)
class CurrentQuestion:
    submission_id: SubmissionId
    item_id: ItemId
    node: str
    instruction: str
    prompt: str
    stimulus: str | None
    options: tuple[QuestionOption, ...]
    candidate_id: CandidateId
    beta: float
    eta: float
    correct_option_id: OptionId


@dataclass(frozen=True, slots=True)
class PlayerState:
    schema_version: int
    posterior: tuple[float, ...]
    answered_items: tuple[AnsweredItem, ...]
    current_question: CurrentQuestion | None
    pending_graph: PendingGraph | None = None
    session_pool: SessionPool | None = None
    inventory_plan: InventoryPlan | None = None

    @classmethod
    def new(
        cls,
        *,
        posterior: tuple[float, ...] = (),
        current_question: CurrentQuestion | None = None,
        pending_graph: PendingGraph | None = None,
        session_pool: SessionPool | None = None,
        inventory_plan: InventoryPlan | None = None,
    ) -> "PlayerState":
        return cls(
            schema_version=PLAYER_STATE_SCHEMA_VERSION,
            posterior=posterior,
            answered_items=(),
            current_question=current_question,
            pending_graph=pending_graph,
            session_pool=session_pool,
            inventory_plan=inventory_plan,
        )


@dataclass(frozen=True, slots=True)
class LegacyPlayerState:
    """Readable pre-v2 state which must never be resumed or activated."""

    posterior: tuple[float, ...]
    answered_items: tuple[AnsweredItem, ...]


PersistedPlayerState = PlayerState | LegacyPlayerState


@dataclass(frozen=True, slots=True)
class AssessmentSession:
    test_id: TestId
    user_id: str
    learning_path_id: LearningPathId
    graph_hash: str | None
    status: SessionStatus
    started_at: datetime
    method: AssessmentMethod
    player_state: PersistedPlayerState
    model: KstModel | LegacyKstModel | None = None
    final_profile: FinalProfile | None = None
    goal: str | None = None

    @property
    def is_legacy(self) -> bool:
        return isinstance(self.player_state, LegacyPlayerState)


@dataclass(frozen=True, slots=True)
class YgOrder:
    order_id: YgOrderId | None
    test_id: TestId
    course: str
    nodes: tuple[str, ...]
    cognitive_level: str | None
    volume: int
    status: YgStatus
    created_at: datetime | None = None
    item_requests: tuple[InventoryRequest, ...] = ()
    fulfillment_results: tuple[InventoryResult, ...] = ()


@dataclass(frozen=True, slots=True)
class AnswerRecord:
    submission_id: SubmissionId
    test_id: TestId
    item_id: ItemId
    score: int
    selected_answer: str
    answered_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ActivationCommand:
    test_id: TestId
    graph_hash: str
    model: KstModel
    first_question: CurrentQuestion
    session_pool: SessionPool


@dataclass(frozen=True, slots=True)
class AnswerTransition:
    next_player_state: PlayerState
    final_profile: FinalProfile | None = None


@dataclass(frozen=True, slots=True)
class AnswerCommitResult:
    outcome: AnswerCommitOutcome
    session: AssessmentSession
    answer: AnswerRecord | None
