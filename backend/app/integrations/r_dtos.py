"""Strict private DTOs for the committed internal KST v1 OpenAPI contract."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class RDto(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RelationDto(RDto):
    from_: str = Field(alias="from", min_length=1, pattern=r"\S")
    to: str = Field(min_length=1, pattern=r"\S")


class NodeParameterDto(RDto):
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
    schema_version: Literal[1]
    method: Literal["kst"]
    nodes: tuple[str, ...] = Field(min_length=1)
    knowledge_states: tuple[tuple[str, ...], ...] = Field(min_length=1)
    matrix: tuple[tuple[Annotated[int, Field(ge=0, le=1)], ...], ...] = Field(
        min_length=1
    )
    uniform_prior: tuple[Annotated[float, Field(ge=0, le=1)], ...] = Field(min_length=1)
    beta: tuple[Annotated[float, Field(ge=0, le=1)], ...] = Field(min_length=1)
    eta: tuple[Annotated[float, Field(ge=0, le=1)], ...] = Field(min_length=1)
    configuration: KstConfigurationDto
    configuration_hash: str = Field(pattern=r"^kst-config-v1:sha256:[0-9a-f]{64}$")


class ModelRequestDto(RDto):
    nodes: tuple[str, ...] = Field(min_length=1)
    relations: tuple[RelationDto, ...]
    node_parameters: tuple[NodeParameterDto, ...] = Field(min_length=1)
    cached_knowledge_states: tuple[tuple[str, ...], ...] | None = None


class ModelResponseDto(RDto):
    model: KstModelDto
    posterior: tuple[Annotated[float, Field(ge=0, le=1)], ...] = Field(min_length=1)
    next_node: str


class AdvanceRequestDto(RDto):
    model: KstModelDto
    posterior: tuple[Annotated[float, Field(ge=0, le=1)], ...] = Field(min_length=1)
    question_node: str = Field(min_length=1, pattern=r"\S")
    response_correct: bool
    response_count: int = Field(ge=1)


class FinalProfileDto(RDto):
    mastered: tuple[str, ...]
    ready_to_learn: tuple[str, ...]
    uncertain_ahead: tuple[str, ...]
    uncertain_prerequisite: tuple[str, ...]
    not_yet: tuple[str, ...]
    summary: str | None
    stop_reason: Literal["natural", "safety_cap"]
    best_state_confidence: float
    credible_mass: float
    credible_state_count: int = Field(ge=1)


class InProgressResponseDto(RDto):
    status: Literal["in_progress"]
    posterior: tuple[Annotated[float, Field(ge=0, le=1)], ...] = Field(min_length=1)
    next_node: str


class CompletedResponseDto(RDto):
    status: Literal["completed"]
    posterior: tuple[Annotated[float, Field(ge=0, le=1)], ...] = Field(min_length=1)
    profile: FinalProfileDto


class HealthResponseDto(RDto):
    status: Literal["ok"]
