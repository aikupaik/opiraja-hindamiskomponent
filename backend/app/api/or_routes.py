"""OR-facing assessment routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.domain.models import TestId
from app.services.assessment import AssessmentService

from .auth import TESTS_CREATE, TESTS_READ, AuthContext, authorize_or, require_or
from .dependencies import get_assessment_service
from .dtos import (
    CreateTestRequest,
    CreateTestResponse,
    ErrorResponse,
    RequestValidationResponse,
    TestStatusResponse,
    to_test_status_response,
)

router = APIRouter(prefix="/api/v1/tests", tags=["or-tests"])


@router.post(
    "",
    response_model=CreateTestResponse,
    status_code=status.HTTP_201_CREATED,
    response_description="Assessment created.",
    responses={
        403: {"model": ErrorResponse, "description": "Operation is forbidden."},
        422: {
            "model": RequestValidationResponse | ErrorResponse,
            "description": "Request or graph validation failed.",
        },
        503: {"model": ErrorResponse, "description": "A dependency is unavailable."},
        500: {"model": ErrorResponse, "description": "Request could not be completed."},
    },
    openapi_extra={"security": [{}]},
)
async def create_test(
    payload: CreateTestRequest,
    response: Response,
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    auth: Annotated[AuthContext, Depends(authorize_or)],
) -> CreateTestResponse:
    require_or(auth, TESTS_CREATE, allow_admin_simulation=True)
    result = await service.create_assessment(payload.to_command())
    response.headers["Location"] = f"/api/v1/tests/{result.test_id}"
    return CreateTestResponse.from_domain(
        result,
        player_url=f"/test/{result.test_id}",
    )


@router.get(
    "/{test_id}",
    response_model=TestStatusResponse,
    response_description="Persisted assessment status.",
    responses={
        403: {"model": ErrorResponse, "description": "Operation is forbidden."},
        404: {"model": ErrorResponse, "description": "Assessment was not found."},
        409: {"model": ErrorResponse, "description": "Assessment state is unsupported."},
        503: {"model": ErrorResponse, "description": "Persistence is unavailable."},
        500: {"model": ErrorResponse, "description": "Request could not be completed."},
    },
    openapi_extra={"security": [{}]},
)
async def get_test(
    test_id: UUID,
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    auth: Annotated[AuthContext, Depends(authorize_or)],
) -> TestStatusResponse:
    require_or(auth, TESTS_READ, allow_admin_simulation=True)
    view = await service.get_assessment(TestId(test_id))
    return to_test_status_response(view)
