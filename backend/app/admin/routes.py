"""Authenticated administration and experiment diagnostic endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse

from app.api.auth import (
    ADMIN_DIAGNOSTICS,
    ADMIN_READ,
    ADMIN_WRITE,
    AuthContext,
    authorize_admin,
    require_admin,
)
from app.api.dependencies import (
    get_admin_repository,
    get_diagnostic_hub,
    get_settings,
    get_source_ingestor,
)
from app.config import Settings

from .diagnostics import DiagnosticHub
from .ingestion import SourceIngestor, SourceInvalid
from .models import (
    AdminItem,
    AdminSession,
    CourseChoice,
    CreateYgRuleRequest,
    EditableItem,
    ItemPage,
    SourceMaterial,
    UpdateItemRequest,
    YgRule,
)
from .repository import AdminRepository

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/session", response_model=AdminSession)
async def get_admin_session(
    settings: Annotated[Settings, Depends(get_settings)],
    auth: Annotated[AuthContext, Depends(authorize_admin)],
) -> AdminSession:
    require_admin(auth, ADMIN_READ)
    return AdminSession(
        subject=auth.subject,
        capabilities=tuple(sorted(auth.scopes)),
        max_graph_nodes=settings.max_graph_nodes,
        diagnostic_max_events=settings.admin_diagnostic_max_events,
        diagnostic_ttl_seconds=settings.admin_diagnostic_ttl_seconds,
        source_max_bytes=settings.admin_source_max_bytes,
        source_max_pdf_pages=settings.admin_source_max_pdf_pages,
        source_max_text_chars=settings.admin_source_max_text_chars,
    )


@router.get("/courses", response_model=tuple[CourseChoice, ...])
async def list_courses(
    repository: Annotated[AdminRepository, Depends(get_admin_repository)],
    auth: Annotated[AuthContext, Depends(authorize_admin)],
) -> tuple[CourseChoice, ...]:
    require_admin(auth, ADMIN_READ)
    return await repository.list_courses()


@router.get("/source-materials", response_model=tuple[SourceMaterial, ...])
async def list_source_materials(
    course: Annotated[str, Query(min_length=1)],
    repository: Annotated[AdminRepository, Depends(get_admin_repository)],
    auth: Annotated[AuthContext, Depends(authorize_admin)],
) -> tuple[SourceMaterial, ...]:
    require_admin(auth, ADMIN_READ)
    return await repository.list_source_materials(course.strip())


@router.get("/source-materials/{material_id}", response_model=SourceMaterial)
async def get_source_material(
    material_id: int,
    repository: Annotated[AdminRepository, Depends(get_admin_repository)],
    auth: Annotated[AuthContext, Depends(authorize_admin)],
) -> SourceMaterial:
    require_admin(auth, ADMIN_READ)
    material = await repository.get_source_material(material_id)
    if material is None:
        raise AdminRowNotFound("source material was not found")
    return material


@router.post(
    "/source-materials",
    response_model=SourceMaterial,
    status_code=status.HTTP_201_CREATED,
)
async def create_source_material(
    course: Annotated[str, Form()],
    title: Annotated[str, Form()],
    repository: Annotated[AdminRepository, Depends(get_admin_repository)],
    ingestor: Annotated[SourceIngestor, Depends(get_source_ingestor)],
    auth: Annotated[AuthContext, Depends(authorize_admin)],
    source_url: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> SourceMaterial:
    require_admin(auth, ADMIN_WRITE)
    normalized_course = course.strip()
    normalized_title = title.strip()
    normalized_url = (source_url or "").strip()
    if not normalized_course or not normalized_title:
        raise SourceInvalid("course code and title must not be blank")
    if not normalized_url and file is None:
        raise SourceInvalid("a source URL or file is required")
    if file is not None:
        filename = (file.filename or "").strip()
        if not filename:
            raise SourceInvalid("uploaded source must have a filename")
        data = await file.read(ingestor.maximum_input_bytes + 1)
        content = await ingestor.from_upload(
            filename=filename,
            content_type=file.content_type,
            data=data,
        )
        provenance = normalized_url or filename
    else:
        content = await ingestor.from_url(normalized_url)
        provenance = normalized_url
    return await repository.create_source_material(
        course=normalized_course,
        title=normalized_title,
        source_url=provenance,
        content=content,
    )


@router.get("/yg-rules", response_model=tuple[YgRule, ...])
async def list_yg_rules(
    course: Annotated[str, Query(min_length=1)],
    repository: Annotated[AdminRepository, Depends(get_admin_repository)],
    auth: Annotated[AuthContext, Depends(authorize_admin)],
) -> tuple[YgRule, ...]:
    require_admin(auth, ADMIN_READ)
    return await repository.list_yg_rules(course.strip())


@router.post("/yg-rules", response_model=YgRule, status_code=status.HTTP_201_CREATED)
async def create_yg_rule(
    payload: CreateYgRuleRequest,
    repository: Annotated[AdminRepository, Depends(get_admin_repository)],
    auth: Annotated[AuthContext, Depends(authorize_admin)],
) -> YgRule:
    require_admin(auth, ADMIN_WRITE)
    return await repository.create_yg_rule(
        payload.course, payload.description, payload.example
    )


@router.get("/items", response_model=ItemPage)
async def list_items(
    course: Annotated[str, Query(min_length=1)],
    repository: Annotated[AdminRepository, Depends(get_admin_repository)],
    auth: Annotated[AuthContext, Depends(authorize_admin)],
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ItemPage:
    require_admin(auth, ADMIN_READ)
    items, total = await repository.list_items(course.strip(), limit, offset)
    return ItemPage(items=items, total=total, limit=limit, offset=offset)


@router.put("/items/{yp_id}", response_model=AdminItem)
async def update_item(
    yp_id: int,
    payload: UpdateItemRequest,
    repository: Annotated[AdminRepository, Depends(get_admin_repository)],
    auth: Annotated[AuthContext, Depends(authorize_admin)],
) -> AdminItem:
    require_admin(auth, ADMIN_WRITE)
    editable = payload.model_dump(exclude={"mode"})
    validated = EditableItem.model_validate(editable)
    if payload.mode == "update_existing":
        item = await repository.update_item(yp_id, validated)
    else:
        item = await repository.create_item_copy(yp_id, validated)
    if item is None:
        raise AdminRowNotFound("item was not found")
    return item


@router.get("/experiments/{experiment_id}/events")
async def stream_experiment_events(
    experiment_id: UUID,
    hub: Annotated[DiagnosticHub, Depends(get_diagnostic_hub)],
    auth: Annotated[AuthContext, Depends(authorize_admin)],
    after: Annotated[int, Query(ge=0)] = 0,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    require_admin(auth, ADMIN_DIAGNOSTICS)
    replay_after = after
    if last_event_id is not None:
        try:
            replay_after = max(replay_after, int(last_event_id))
        except ValueError:
            replay_after = after
    return StreamingResponse(
        hub.stream(str(experiment_id), after_sequence=replay_after),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


class AdminRowNotFound(RuntimeError):
    """An admin target row does not exist."""
