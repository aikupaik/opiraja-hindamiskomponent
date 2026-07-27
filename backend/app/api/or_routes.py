"""OR-facing assessment routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.domain.models import TestId
from app.services.assessment import AssessmentService

from .auth import AuthContext, authorize_or, require_or
from .dependencies import get_assessment_service
from .dtos import (
    CreateTestRequest,
    CreateTestResponse,
    TestStatusResponse,
    to_test_status_response,
)

router = APIRouter(prefix="/api/v1/tests", tags=["or-tests"])


@router.post("", response_model=CreateTestResponse, status_code=status.HTTP_201_CREATED)
async def create_test(
    payload: CreateTestRequest,
    response: Response,
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    auth: Annotated[AuthContext, Depends(authorize_or)],
) -> CreateTestResponse:
    require_or(auth, "tests:create")
    result = await service.create_assessment(payload.to_command())
    response.headers["Location"] = f"/api/v1/tests/{result.test_id}"
    return CreateTestResponse.from_domain(result)


@router.get("/{test_id}", response_model=TestStatusResponse)
async def get_test(
    test_id: UUID,
    service: Annotated[AssessmentService, Depends(get_assessment_service)],
    auth: Annotated[AuthContext, Depends(authorize_or)],
) -> TestStatusResponse:
    require_or(auth, "tests:read")
    view = await service.get_assessment(TestId(test_id))
    return to_test_status_response(view)
