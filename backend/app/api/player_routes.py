"""Player-facing assessment routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.domain.models import TestId
from app.services.assessment import AssessmentService

from .auth import AuthContext, authorize_player, require_player
from .dependencies import get_assessment_service
from .dtos import (
    ErrorResponse,
    PlayerPreparingResponse,
    PlayerReadyResponse,
    SubmitAnswerRequest,
    to_player_ready_response,
)

router = APIRouter(prefix="/api/v1/player/tests", tags=["player-tests"])


@router.post(
    "/{test_id}/start",
    response_model=PlayerReadyResponse,
    response_description="Current question or completed feedback.",
    responses={
        202: {
            "model": PlayerPreparingResponse,
            "description": "Assessment is still preparing; honor Retry-After.",
        },
        403: {"model": ErrorResponse, "description": "Operation is forbidden."},
        404: {"model": ErrorResponse, "description": "Assessment was not found."},
        409: {"model": ErrorResponse, "description": "Assessment cannot be started."},
        503: {"model": ErrorResponse, "description": "A dependency is unavailable."},
        500: {"model": ErrorResponse, "description": "Request could not be completed."},
    },
    openapi_extra={"security": [{}]},
)
async def start_test(
    test_id: UUID,
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    auth: Annotated[AuthContext, Depends(authorize_player)],
) -> PlayerReadyResponse | JSONResponse:
    require_player(auth, test_id, allow_admin_simulation=True)
    view = await service.start_assessment(TestId(test_id))
    if view.status.value == "preparing":
        body = PlayerPreparingResponse()
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            headers={"Retry-After": "3"},
            content=body.model_dump(mode="json"),
        )
    return to_player_ready_response(view)


@router.post(
    "/{test_id}/answers",
    response_model=PlayerReadyResponse,
    response_description="Next question or completed feedback.",
    responses={
        403: {"model": ErrorResponse, "description": "Operation is forbidden."},
        404: {"model": ErrorResponse, "description": "Assessment was not found."},
        409: {"model": ErrorResponse, "description": "Submission conflicts with state."},
        503: {"model": ErrorResponse, "description": "A dependency is unavailable."},
        500: {"model": ErrorResponse, "description": "Request could not be completed."},
    },
    openapi_extra={"security": [{}]},
)
async def submit_answer(
    test_id: UUID,
    payload: SubmitAnswerRequest,
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    auth: Annotated[AuthContext, Depends(authorize_player)],
) -> PlayerReadyResponse:
    require_player(auth, test_id, allow_admin_simulation=True)
    view = await service.submit_answer(
        TestId(test_id),
        payload.domain_submission_id,
        payload.domain_option_id,
    )
    return to_player_ready_response(view)
