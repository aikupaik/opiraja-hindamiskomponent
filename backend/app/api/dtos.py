"""Strict public request and response models."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import AssessmentMethod, GraphRelation, OptionId, SubmissionId
from app.services.assessment import (
    AssessmentView,
    CreateAssessmentCommand,
    CreateAssessmentResult,
    Feedback,
)
from app.services.questions import QuestionOutput


class PublicModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ErrorDetail(PublicModel):
    code: str
    message: str


class ErrorResponse(PublicModel):
    error: ErrorDetail


class RequestValidationDetail(BaseModel):
    loc: tuple[str | int, ...]
    msg: str
    type: str


class RequestValidationResponse(BaseModel):
    detail: tuple[RequestValidationDetail, ...]


class RelationRequest(PublicModel):
    prerequisite: str = Field(alias="from")
    dependent: str = Field(alias="to")


class CreateTestRequest(PublicModel):
    user_id: str = Field(min_length=1)
    learning_path_id: str = Field(min_length=1)
    nodes: tuple[str, ...]
    relations: tuple[RelationRequest, ...] = ()
    course: str = ""
    goal: str | None = None
    method: Literal["kst"] = "kst"
    cognitive_level: str = "mõistab"

    def to_command(self) -> CreateAssessmentCommand:
        return CreateAssessmentCommand(
            user_id=self.user_id,
            learning_path_id=self.learning_path_id,
            nodes=self.nodes,
            relations=tuple(
                GraphRelation(value.prerequisite, value.dependent)
                for value in self.relations
            ),
            course=self.course,
            goal=self.goal,
            method=AssessmentMethod(self.method),
            cognitive_level=self.cognitive_level,
        )


class SubmitAnswerRequest(PublicModel):
    submission_id: UUID
    option_id: str = Field(min_length=1)

    @property
    def domain_submission_id(self) -> SubmissionId:
        return SubmissionId(self.submission_id)

    @property
    def domain_option_id(self) -> OptionId:
        return OptionId(self.option_id)


class FeedbackResponse(PublicModel):
    already_mastered: tuple[str, ...]
    learn_next: tuple[str, ...]
    review: tuple[str, ...]
    summary: str | None
    confidence_limited: bool

    @classmethod
    def from_domain(cls, feedback: Feedback) -> "FeedbackResponse":
        return cls(
            already_mastered=feedback.already_mastered,
            learn_next=feedback.learn_next,
            review=feedback.review,
            summary=feedback.summary,
            confidence_limited=feedback.confidence_limited,
        )


class CreateTestResponse(PublicModel):
    test_id: UUID
    status: Literal["active", "preparing"]
    player_url: str
    missing_nodes: tuple[str, ...]

    @classmethod
    def from_domain(
        cls, result: CreateAssessmentResult, *, player_url: str
    ) -> "CreateTestResponse":
        if result.status.value not in ("active", "preparing"):
            raise ValueError("new assessment has an invalid public status")
        return cls(
            test_id=result.test_id,
            status=result.status.value,
            player_url=player_url,
            missing_nodes=result.missing_nodes,
        )


class PlayerTokenResponse(PublicModel):
    player_url: str


class TestPreparingResponse(PublicModel):
    status: Literal["preparing"] = "preparing"


class TestActiveResponse(PublicModel):
    status: Literal["active"] = "active"


class TestFailedResponse(PublicModel):
    status: Literal["failed"] = "failed"


class TestCompletedResponse(PublicModel):
    status: Literal["completed"] = "completed"
    feedback: FeedbackResponse


TestStatusResponse = (
    TestPreparingResponse
    | TestActiveResponse
    | TestCompletedResponse
    | TestFailedResponse
)


def to_test_status_response(view: AssessmentView) -> TestStatusResponse:
    if view.status.value == "preparing":
        return TestPreparingResponse()
    if view.status.value == "active":
        return TestActiveResponse()
    if view.status.value == "failed":
        return TestFailedResponse()
    if view.status.value == "completed" and view.feedback is not None:
        return TestCompletedResponse(
            feedback=FeedbackResponse.from_domain(view.feedback)
        )
    raise ValueError("assessment has an invalid OR status")


class PlayerPreparingResponse(PublicModel):
    status: Literal["preparing"] = "preparing"


class PlayerActiveResponse(PublicModel):
    status: Literal["active"] = "active"
    question: QuestionOutput


class PlayerCompletedResponse(PublicModel):
    status: Literal["completed"] = "completed"
    feedback: FeedbackResponse


PlayerReadyResponse = PlayerActiveResponse | PlayerCompletedResponse


def to_player_ready_response(view: AssessmentView) -> PlayerReadyResponse:
    if view.status.value == "active" and view.question is not None:
        return PlayerActiveResponse(question=view.question)
    if view.status.value == "completed" and view.feedback is not None:
        return PlayerCompletedResponse(
            feedback=FeedbackResponse.from_domain(view.feedback)
        )
    raise ValueError("assessment does not have a ready player view")


class HealthResponse(PublicModel):
    status: Literal["ok"]


class DependencyStatus(PublicModel):
    supabase: Literal["ready", "unavailable"]
    r: Literal["ready", "unavailable"]


class ReadinessResponse(PublicModel):
    status: Literal["ready", "unavailable"]
    dependencies: DependencyStatus
