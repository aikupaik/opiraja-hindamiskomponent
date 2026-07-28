"""Strict private DTOs for the candidate-aware internal KST v2 contract."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class RDto(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RelationDto(RDto):
    from_: str = Field(alias="from", min_length=1, pattern=r"\S")
    to: str = Field(min_length=1, pattern=r"\S")


class CandidateDto(RDto):
    candidate_id: str = Field(min_length=1, pattern=r"\S")
    node: str = Field(min_length=1, pattern=r"\S")
    beta: float = Field(ge=0, le=1)
    eta: float = Field(ge=0, le=1)


class ReliabilityFloorDto(RDto):
    minimum: int = Field(ge=0)
    multiplier: float = Field(gt=0)
    maximum: int = Field(ge=0)


class SafetyCapDto(RDto):
    minimum_above_floor: int = Field(ge=0)
    node_multiplier: float = Field(gt=0)


class KstConfigurationDto(RDto):
    schema_version: Literal[1]
    stop_confidence: float = Field(gt=0, le=1)
    feedback_credible_mass: float = Field(gt=0, le=1)
    reliability_floor: ReliabilityFloorDto
    safety_cap: SafetyCapDto


class KstModelDto(RDto):
    schema_version: Literal[2]
    method: Literal["kst"]
    nodes: tuple[str, ...] = Field(min_length=1)
    knowledge_states: tuple[tuple[str, ...], ...] = Field(min_length=1)
    matrix: tuple[tuple[Annotated[int, Field(ge=0, le=1)], ...], ...] = Field(
        min_length=1
    )
    uniform_prior: tuple[Annotated[float, Field(ge=0, le=1)], ...] = Field(min_length=1)
    configuration: KstConfigurationDto
    configuration_hash: str = Field(pattern=r"^kst-config-v1:sha256:[0-9a-f]{64}$")
    reliability_floor: int = Field(ge=0)
    safety_cap: int = Field(ge=0)


class ModelRequestDto(RDto):
    nodes: tuple[str, ...] = Field(min_length=1)
    relations: tuple[RelationDto, ...]
    cached_knowledge_states: tuple[tuple[str, ...], ...] | None = None


class ModelResponseDto(RDto):
    model: KstModelDto
    posterior: tuple[Annotated[float, Field(ge=0, le=1)], ...] = Field(min_length=1)


class SelectRequestDto(RDto):
    model: KstModelDto
    posterior: tuple[Annotated[float, Field(ge=0, le=1)], ...] = Field(min_length=1)
    candidates: tuple[CandidateDto, ...] = Field(min_length=1)


class SelectedCandidateDto(RDto):
    candidate_id: str = Field(min_length=1, pattern=r"\S")
    node: str = Field(min_length=1, pattern=r"\S")


class AdvanceRequestDto(RDto):
    model: KstModelDto
    posterior: tuple[Annotated[float, Field(ge=0, le=1)], ...] = Field(min_length=1)
    administered: CandidateDto
    response_correct: bool
    response_count: int = Field(ge=1)
    remaining_candidates: tuple[CandidateDto, ...]


class FinalProfileDto(RDto):
    mastered: tuple[str, ...]
    ready_to_learn: tuple[str, ...]
    uncertain_ahead: tuple[str, ...]
    uncertain_prerequisite: tuple[str, ...]
    not_yet: tuple[str, ...]
    summary: str | None
    stop_reason: Literal[
        "natural", "safety_cap", "item_inventory_exhausted"
    ]
    best_state_confidence: float
    credible_mass: float
    credible_state_count: int = Field(ge=1)
    confidence_limited: bool


class InProgressResponseDto(RDto):
    status: Literal["in_progress"]
    posterior: tuple[Annotated[float, Field(ge=0, le=1)], ...] = Field(min_length=1)
    next_candidate: SelectedCandidateDto


class CompletedResponseDto(RDto):
    status: Literal["completed"]
    posterior: tuple[Annotated[float, Field(ge=0, le=1)], ...] = Field(min_length=1)
    profile: FinalProfileDto


class HealthResponseDto(RDto):
    status: Literal["ok"]
