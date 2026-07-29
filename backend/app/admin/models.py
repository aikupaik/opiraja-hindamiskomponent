"""Typed admin read models and strict API payloads."""

from datetime import datetime
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.models import ItemStatus


class AdminModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AdminSession(AdminModel):
    subject: str
    capabilities: tuple[str, ...]
    max_graph_nodes: int
    diagnostic_max_events: int
    diagnostic_ttl_seconds: int
    source_max_bytes: int
    source_max_pdf_pages: int
    source_max_text_chars: int


class CourseChoice(AdminModel):
    value: str
    title: str
    label: str


class SourceMaterial(AdminModel):
    id: int
    course: str
    title: str
    source_url: str | None
    content: str | None = None
    content_preview: str
    added_at: datetime | None


class YgRule(AdminModel):
    id: int
    course: str
    description: str
    example: object


class CreateYgRuleRequest(AdminModel):
    course: str = Field(min_length=1)
    description: str = Field(min_length=1)
    example: object = Field(default_factory=dict)

    @field_validator("course", "description")
    @classmethod
    def nonblank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be blank")
        return normalized

    @field_validator("example")
    @classmethod
    def nonnull_example(cls, value: object) -> object:
        if value is None:
            raise ValueError("example must be non-null JSON")
        return value


class AdminItem(AdminModel):
    yp_id: int
    course: str
    graph_node: str
    parent_graph_node: str | None
    cognitive_level: str
    instruction: str
    prompt: str
    stimulus: str | None
    answer_key: str
    distractor_1: str | None
    distractor_2: str | None
    distractor_3: str | None
    score: int
    irt_a: float
    irt_b: float
    beta_error: float
    guess_probability: float
    status: ItemStatus
    usage_count: int
    last_used_at: datetime | None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class EditableItem(AdminModel):
    instruction: str
    prompt: str
    stimulus: str | None
    answer_key: str
    distractor_1: str | None
    distractor_2: str | None
    distractor_3: str | None
    status: ItemStatus
    irt_a: float
    irt_b: float
    beta_error: float
    guess_probability: float

    @field_validator("instruction", "prompt", "answer_key")
    @classmethod
    def required_content(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("required content must not be blank")
        return normalized

    @field_validator("stimulus", "distractor_1", "distractor_2", "distractor_3")
    @classmethod
    def normalize_optional_content(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("irt_a", "irt_b", "beta_error", "guess_probability")
    @classmethod
    def finite_number(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("measurement values must be finite")
        return value

    @model_validator(mode="after")
    def validate_probabilities_and_usable_question(self) -> "EditableItem":
        for name, value in (
            ("beta_error", self.beta_error),
            ("guess_probability", self.guess_probability),
        ):
            if not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.status is ItemStatus.USABLE:
            choices = {
                value.strip()
                for value in (
                    self.answer_key,
                    self.distractor_1 or "",
                    self.distractor_2 or "",
                    self.distractor_3 or "",
                )
                if value.strip()
            }
            if len(choices) < 2:
                raise ValueError(
                    "a usable question needs at least two distinct answer choices"
                )
        return self


class UpdateItemRequest(EditableItem):
    mode: Literal["update_existing", "create_copy"] = "create_copy"


class ItemPage(AdminModel):
    items: tuple[AdminItem, ...]
    total: int
    limit: int
    offset: int
