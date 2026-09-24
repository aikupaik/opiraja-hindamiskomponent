"""OR-facing assessment routes."""

import hashlib
import json
import logging
from collections.abc import Mapping, Sequence
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status

from app.domain.models import TestId
from app.logging_config import production_sanitizer, truncate_utf8
from app.observability import current_request_id
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
logger = logging.getLogger("app.requests")
_CREATE_BODY_LIMIT = 32 * 1024
_PREVIEW_STRING_LIMIT = 128


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
    _log_create_request(payload)
    result = await service.create_assessment(payload.to_command())
    response.headers["Location"] = f"/api/v1/tests/{result.test_id}"
    response.headers["Cache-Control"] = "no-store"
    player_token = tokens.issue_player(result.test_id)
    return CreateTestResponse.from_domain(
        result,
        player_url=tokens.player_url(result.test_id, player_token),
    )


def _log_create_request(payload: CreateTestRequest) -> None:
    body = cast(
        dict[str, object],
        payload.model_dump(
            mode="json",
            by_alias=True,
            include={
                "nodes",
                "relations",
                "course",
                "goal",
                "method",
                "cognitive_level",
                "parent_node",
            },
        ),
    )
    serialized = json.dumps(
        body,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    truncated = len(serialized) > _CREATE_BODY_LIMIT
    logged_body: object = _create_body_preview(body) if truncated else body
    event: dict[str, object] = {
        "event": "assessment_create_received",
        "method": "POST",
        "route": "/api/v1/tests",
        "body": logged_body,
        "node_count": len(payload.nodes),
        "relation_count": len(payload.relations),
        "body_bytes": len(serialized),
        "body_sha256": hashlib.sha256(serialized).hexdigest(),
        "body_truncated": truncated,
    }
    request_id = current_request_id()
    if request_id is not None:
        event["request_id"] = request_id
    safe_event = production_sanitizer().sanitize(event)
    if not isinstance(safe_event, dict):
        raise TypeError("sanitized assessment event must remain an object")
    logger.info("assessment_create_received", extra=safe_event)


def _create_body_preview(body: dict[str, object]) -> dict[str, object]:
    nodes = body.get("nodes")
    relations = body.get("relations")
    node_values = cast(list[object], nodes) if isinstance(nodes, list) else []
    relation_values = (
        cast(list[object], relations) if isinstance(relations, list) else []
    )
    preview = {
        key: _truncate_preview_strings(value)
        for key, value in body.items()
        if key not in {"nodes", "relations"}
    }
    preview["nodes"] = _truncate_preview_strings(node_values[:25])
    preview["relations"] = _truncate_preview_strings(relation_values[:50])
    preview["omitted_node_count"] = max(0, len(node_values) - 25)
    preview["omitted_relation_count"] = max(0, len(relation_values) - 50)
    return preview


def _truncate_preview_strings(value: object) -> object:
    if isinstance(value, str):
        return truncate_utf8(value, _PREVIEW_STRING_LIMIT)
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        values = cast(Sequence[object], value)
        return [_truncate_preview_strings(item) for item in values]
    if isinstance(value, Mapping):
        values = cast(Mapping[object, object], value)
        return {
            str(key): _truncate_preview_strings(item)
            for key, item in values.items()
        }
    return value


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
