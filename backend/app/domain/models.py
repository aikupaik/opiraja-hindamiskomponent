"""Immutable domain values used at the assessment persistence boundary."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import NewType
from uuid import UUID

TestId = NewType("TestId", UUID)
SubmissionId = NewType("SubmissionId", UUID)
ItemId = NewType("ItemId", int)
YgOrderId = NewType("YgOrderId", int)
LearningPathId = NewType("LearningPathId", str)
OptionId = NewType("OptionId", str)

PLAYER_STATE_SCHEMA_VERSION = 1
KST_MODEL_SCHEMA_VERSION = 1
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


@dataclass(frozen=True, slots=True)
class NodeParameters:
    node: str
    item_id: ItemId
    beta: float
    eta: float


@dataclass(frozen=True, slots=True)
class NodeCoverage:
    node: str
    parameters: NodeParameters | None

    @property
    def covered(self) -> bool:
        return self.parameters is not None


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
    next_node: str


@dataclass(frozen=True, slots=True)
class AdvanceInProgress:
    posterior: tuple[float, ...]
    next_node: str


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


@dataclass(frozen=True, slots=True)
class PlayerState:
    schema_version: int
    posterior: tuple[float, ...]
    answered_items: tuple[AnsweredItem, ...]
    current_question: CurrentQuestion | None
    pending_graph: PendingGraph | None = None

    @classmethod
    def new(
        cls,
        *,
        posterior: tuple[float, ...] = (),
        current_question: CurrentQuestion | None = None,
        pending_graph: PendingGraph | None = None,
    ) -> "PlayerState":
        return cls(
            schema_version=PLAYER_STATE_SCHEMA_VERSION,
            posterior=posterior,
            answered_items=(),
            current_question=current_question,
            pending_graph=pending_graph,
        )


@dataclass(frozen=True, slots=True)
class LegacyPlayerState:
    """Readable pre-v1 state which must never be resumed or activated."""

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
    model: KstModel | None = None
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


@dataclass(frozen=True, slots=True)
class AnswerTransition:
    next_player_state: PlayerState
    final_profile: FinalProfile | None = None


@dataclass(frozen=True, slots=True)
class AnswerCommitResult:
    outcome: AnswerCommitOutcome
    session: AssessmentSession
    answer: AnswerRecord | None
