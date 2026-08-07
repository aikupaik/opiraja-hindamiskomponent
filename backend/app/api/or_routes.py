"""OR-facing assessment routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.domain.models import TestId
from app.services.assessment import AssessmentConflict, AssessmentService

from .auth import (
    TESTS_CREATE,
    TESTS_LAUNCH,
    TESTS_READ,
    AuthContext,
    authorize_or,
    require_or,
)
from .dependencies import get_assessment_service, get_token_service
from .dtos import (
    CreateTestRequest,
    CreateTestResponse,
    ErrorResponse,
    RequestValidationResponse,
    PlayerTokenResponse,
    TestStatusResponse,
    to_test_status_response,
)
from .tokens import TokenService

router = APIRouter(prefix="/api/v1/tests", tags=["or-tests"])


@router.post(
    "",
    response_model=CreateTestResponse,
    status_code=status.HTTP_201_CREATED,
    response_description="Assessment created.",
    responses={
        401: {"model": ErrorResponse, "description": "Bearer token is invalid."},
        403: {"model": ErrorResponse, "description": "Operation is forbidden."},
        422: {
            "model": RequestValidationResponse | ErrorResponse,
            "description": "Request or graph validation failed.",
        },
        503: {"model": ErrorResponse, "description": "A dependency is unavailable."},
        500: {"model": ErrorResponse, "description": "Request could not be completed."},
    },
)
async def create_test(
    payload: CreateTestRequest,
    response: Response,
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    auth: Annotated[AuthContext, Depends(authorize_or)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> CreateTestResponse:
    require_or(auth, TESTS_CREATE, allow_admin_simulation=True)
    result = await service.create_assessment(payload.to_command())
    response.headers["Location"] = f"/api/v1/tests/{result.test_id}"
    response.headers["Cache-Control"] = "no-store"
    player_token = tokens.issue_player(result.test_id)
    return CreateTestResponse.from_domain(
        result,
        player_url=tokens.player_url(result.test_id, player_token),
    )


@router.get(
    "/{test_id}",
    response_model=TestStatusResponse,
    response_description="Persisted assessment status.",
    responses={
        401: {"model": ErrorResponse, "description": "Bearer token is invalid."},
        403: {"model": ErrorResponse, "description": "Operation is forbidden."},
        404: {"model": ErrorResponse, "description": "Assessment was not found."},
        409: {"model": ErrorResponse, "description": "Assessment state is unsupported."},
        503: {"model": ErrorResponse, "description": "Persistence is unavailable."},
        500: {"model": ErrorResponse, "description": "Request could not be completed."},
    },
)
async def get_test(
    test_id: UUID,
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    auth: Annotated[AuthContext, Depends(authorize_or)],
) -> TestStatusResponse:
    require_or(auth, TESTS_READ, allow_admin_simulation=True)
    view = await service.get_assessment(TestId(test_id))
    return to_test_status_response(view)


@router.post(
    "/{test_id}/player-token",
    response_model=PlayerTokenResponse,
    response_description="Fresh learner link for an eligible assessment.",
    responses={
        401: {"model": ErrorResponse, "description": "Bearer token is invalid."},
        403: {"model": ErrorResponse, "description": "Operation is forbidden."},
        404: {"model": ErrorResponse, "description": "Assessment was not found."},
        409: {"model": ErrorResponse, "description": "Assessment state is unsupported."},
        422: {"model": RequestValidationResponse, "description": "Path validation failed."},
        503: {"model": ErrorResponse, "description": "Persistence is unavailable."},
        500: {"model": ErrorResponse, "description": "Request could not be completed."},
    },
)
async def issue_player_token(
    test_id: UUID,
    response: Response,
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
    auth: Annotated[AuthContext, Depends(authorize_or)],
) -> PlayerTokenResponse:
    require_or(auth, TESTS_LAUNCH)
    view = await service.get_assessment(TestId(test_id))
    if view.status.value == "failed":
        raise AssessmentConflict("failed assessments cannot receive player links")
    if view.status.value not in ("preparing", "active", "completed"):
        raise AssessmentConflict("assessment state cannot receive a player link")
    token = tokens.issue_player(test_id)
    response.headers["Cache-Control"] = "no-store"
    return PlayerTokenResponse(player_url=tokens.player_url(test_id, token))
