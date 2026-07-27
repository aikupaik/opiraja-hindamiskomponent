"""Player-facing assessment routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.domain.models import TestId
from app.services.assessment import AssessmentService

from .auth import AuthContext, authorize_player, require_player
from .dependencies import get_assessment_service
from .dtos import PlayerViewResponse, SubmitAnswerRequest, to_player_view_response

router = APIRouter(prefix="/api/v1/player/tests", tags=["player-tests"])


@router.post("/{test_id}/start", response_model=PlayerViewResponse)
async def start_test(
    test_id: UUID,
    response: Response,
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    auth: Annotated[AuthContext, Depends(authorize_player)],
) -> PlayerViewResponse:
    require_player(auth, test_id)
    view = await service.start_assessment(TestId(test_id))
    if view.status.value == "preparing":
        response.status_code = status.HTTP_202_ACCEPTED
        response.headers["Retry-After"] = "3"
    return to_player_view_response(view)


@router.post("/{test_id}/answers", response_model=PlayerViewResponse)
async def submit_answer(
    test_id: UUID,
    payload: SubmitAnswerRequest,
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    auth: Annotated[AuthContext, Depends(authorize_player)],
) -> PlayerViewResponse:
    require_player(auth, test_id)
    view = await service.submit_answer(
        TestId(test_id),
        payload.domain_submission_id,
        payload.domain_option_id,
    )
    return to_player_view_response(view)
