"""Admin authorization, mapping, ingestion, route, and diagnostic coverage."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from io import BytesIO
import math
from time import monotonic
from typing import cast
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError
from pypdf import PdfWriter

from app.admin.diagnostics import DiagnosticHub
from app.admin.ingestion import SourceIngestor, SourceInvalid
from app.admin.mapping import (
    decode_course_rows,
    encode_editable,
    encode_item_copy,
)
from app.admin.models import (
    AdminItem,
    EditableItem,
    SourceMaterial,
    UpdateItemRequest,
)
from app.admin.repository import AdminRepository
from app.api.dependencies import (
    get_admin_repository,
    get_assessment_service,
    get_source_ingestor,
)
from app.config import Settings
from app.domain.models import ItemStatus, SessionStatus
from app.main import create_app
from app.services.assessment import (
    AssessmentService,
    CreateAssessmentCommand,
    CreateAssessmentResult,
)


def _settings(*, admin_key: str | None = "operator-secret") -> Settings:
    values: dict[str, object] = {
        "SUPABASE_URL": "https://example.supabase.co",
        "SUPABASE_SERVICE_KEY": "service-secret",
        "R_SERVICE_URL": "http://r-service:8000",
        "ALLOWED_HOSTS": ["193.40.157.124", "127.0.0.1", "testserver"],
    }
    if admin_key is not None:
        values["ADMIN_ACCESS_KEY"] = admin_key
    return Settings.model_validate(values)


@asynccontextmanager
async def _client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client


def _app(settings: Settings) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        app.state.diagnostic_hub = DiagnosticHub()
        yield

    return create_app(settings, lifespan=lifespan)


@pytest.mark.asyncio
async def test_admin_key_is_required_constant_boundary_and_can_be_disabled() -> None:
    app = _app(_settings())
    async with _client(app) as client:
        missing = await client.get("/api/v1/admin/session")
        invalid = await client.get(
            "/api/v1/admin/session",
            headers={"Authorization": "Bearer wrong"},
        )
        valid = await client.get(
            "/api/v1/admin/session",
            headers={"Authorization": "Bearer operator-secret"},
        )

    assert missing.status_code == invalid.status_code == 401
    assert "operator-secret" not in missing.text + invalid.text
    assert valid.status_code == 200
    assert set(valid.json()["capabilities"]) >= {
        "admin:read",
        "admin:write",
        "admin:diagnostics",
        "admin:simulation",
    }
    assert valid.json()["max_graph_nodes"] == 10

    async with _client(_app(_settings(admin_key=None))) as client:
        disabled = await client.get(
            "/api/v1/admin/session",
            headers={"Authorization": "Bearer operator-secret"},
        )
    assert disabled.status_code == 401


def test_course_aggregation_uses_newest_title_and_null_course_fallback() -> None:
    rows = (
        {
            "id": 1,
            "kursus": "FÜS101",
            "pealkiri": "Old title",
            "allika_url": "old.txt",
            "sisu_tekst": "old",
            "lisatud": "2026-01-01T00:00:00Z",
        },
        {
            "id": 2,
            "kursus": "FÜS101",
            "pealkiri": "Physics",
            "allika_url": "new.txt",
            "sisu_tekst": "new",
            "lisatud": "2026-02-01T00:00:00Z",
        },
        {
            "id": 3,
            "kursus": None,
            "pealkiri": "Legacy course",
            "allika_url": "legacy.txt",
            "sisu_tekst": "legacy",
            "lisatud": None,
        },
    )

    choices = decode_course_rows(rows)

    assert [choice.value for choice in choices] == ["FÜS101", "Legacy course"]
    assert choices[0].label == "Physics (FÜS101)"
    assert choices[1].label == "Legacy course (Legacy course)"


@pytest.mark.parametrize("status", tuple(ItemStatus))
def test_item_status_mapping_and_copy_telemetry(status: ItemStatus) -> None:
    editable = _editable(status=status)
    source = {
        "yp_id": 41,
        "kursus": "FÜS101",
        "graafi_objekt": "Force",
        "graafi_ema_objekt": "Mechanics",
        "kognitiivne_tase": "mõistab",
        "skoor": 1,
        "kasutamiste_arv": 9,
        "viimane_kasutus": "2026-07-01T00:00:00Z",
        "juhis": "Old",
    }

    encoded = encode_editable(editable)
    copied = encode_item_copy(source, editable)

    expected = {
        ItemStatus.DRAFT: "kavand",
        ItemStatus.USABLE: "kasutatav",
        ItemStatus.REVIEW: "läbi vaatamisel",
        ItemStatus.ARCHIVED: "arhiivis",
    }[status]
    assert encoded["staatus"] == expected
    assert "yp_id" not in copied
    assert copied["kursus"] == "FÜS101"
    assert copied["graafi_objekt"] == "Force"
    assert copied["skoor"] == 1
    assert copied["kasutamiste_arv"] == 0
    assert copied["viimane_kasutus"] is None


def test_item_payload_rejects_extra_noneditable_and_invalid_measurements() -> None:
    payload = {
        **_editable().model_dump(),
        "mode": "update_existing",
        "course": "not editable",
    }
    with pytest.raises(ValidationError):
        UpdateItemRequest.model_validate(payload)

    with pytest.raises(ValidationError):
        EditableItem.model_validate(
            {**_editable().model_dump(), "beta_error": math.inf}
        )
    with pytest.raises(ValidationError):
        EditableItem.model_validate(
            {
                **_editable().model_dump(),
                "status": "usable",
                "distractor_1": "Correct",
                "distractor_2": None,
                "distractor_3": None,
            }
        )


@pytest.mark.asyncio
async def test_text_html_private_address_and_textless_pdf_ingestion() -> None:
    settings = _settings()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "example.com"
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            content=b"<html><style>hidden</style><body><h1>Course</h1><p>Readable</p></body></html>",
        )

    async def public_resolver(_host: str, _port: int) -> tuple[str, ...]:
        return ("93.184.216.34",)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        ingestor = SourceIngestor(http, settings, resolver=public_resolver)
        assert (
            await ingestor.from_upload(
                filename="notes.md",
                content_type="text/markdown",
                data="Tere, maailm".encode(),
            )
            == "Tere, maailm"
        )
        assert await ingestor.from_url("https://example.com/source") == (
            "Course\nReadable"
        )

        async def private_resolver(_host: str, _port: int) -> tuple[str, ...]:
            return ("127.0.0.1",)

        private = SourceIngestor(http, settings, resolver=private_resolver)
        with pytest.raises(SourceInvalid):
            await private.from_url("https://example.com/source")

        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        buffer = BytesIO()
        writer.write(buffer)
        with pytest.raises(SourceInvalid):
            await ingestor.from_upload(
                filename="scan.pdf",
                content_type="application/pdf",
                data=buffer.getvalue(),
            )


@pytest.mark.asyncio
async def test_upload_takes_precedence_over_url_and_returns_saved_preview() -> None:
    repository = _FakeAdminRepository()
    ingestor = _FakeIngestor()
    app = _app(_settings())
    app.dependency_overrides[get_admin_repository] = lambda: cast(
        AdminRepository, repository
    )
    app.dependency_overrides[get_source_ingestor] = lambda: cast(
        SourceIngestor, ingestor
    )

    async with _client(app) as client:
        saved = await client.post(
            "/api/v1/admin/source-materials",
            headers={"Authorization": "Bearer operator-secret"},
            data={
                "course": "FÜS101",
                "title": "Physics",
                "source_url": "https://example.com/original",
            },
            files={"file": ("notes.txt", b"uploaded text", "text/plain")},
        )

    assert saved.status_code == 201
    assert ingestor.calls == [("upload", "notes.txt")]
    assert repository.materials[0].source_url == "https://example.com/original"
    assert repository.materials[0].content == "extracted upload"


@pytest.mark.asyncio
async def test_diagnostics_are_bounded_replayed_redacted_and_cleanup_subscribers() -> (
    None
):
    hub = DiagnosticHub(
        max_events=2,
        ttl_seconds=1,
        secrets=("operator-secret", "service-secret"),
    )
    for value in range(3):
        hub.emit(
            "experiment",
            source="client",
            level="info",
            event_type="request",
            request_id=f"request-{value}",
            test_id=None,
            payload={
                "sequence_value": value,
                "authorization": "Bearer operator-secret",
                "message": "service-secret must not leak",
            },
        )

    stream = hub.stream("experiment")
    first = await anext(stream)
    assert '"sequence":2' in first
    assert "operator-secret" not in first
    assert "service-secret" not in first
    assert hub.subscriber_count("experiment") == 1
    await stream.aclose()
    assert hub.subscriber_count("experiment") == 0
    hub.expire(now=monotonic() + 2)
    assert hub.subscriber_count("experiment") == 0


@pytest.mark.asyncio
async def test_only_authenticated_correlated_test_requests_emit_diagnostics() -> None:
    app = _app(_settings())
    service = _CreatingService()
    app.dependency_overrides[get_assessment_service] = lambda: cast(
        AssessmentService, service
    )
    experiment_id = "30000000-0000-4000-8000-000000000003"

    async with _client(app) as client:
        correlated = await asyncio.wait_for(
            client.post(
                "/api/v1/tests",
                headers={
                    "Authorization": "Bearer operator-secret",
                    "X-Experiment-ID": experiment_id,
                },
                json={
                    "user_id": "user",
                    "learning_path_id": "path",
                    "nodes": ["A"],
                },
            ),
            timeout=2,
        )
        uncorrelated = await asyncio.wait_for(
            client.post(
                "/api/v1/tests",
                headers={
                    "Authorization": "Bearer wrong",
                    "X-Experiment-ID": "40000000-0000-4000-8000-000000000004",
                },
                json={
                    "user_id": "user",
                    "learning_path_id": "path",
                    "nodes": ["A"],
                },
            ),
            timeout=2,
        )
        hub = cast(DiagnosticHub, app.state.diagnostic_hub)
        events = hub.events_after(experiment_id)

    assert correlated.status_code == uncorrelated.status_code == 201
    assert [event.type for event in events] == [
        "request",
        "response",
        "request_completed",
    ]
    assert hub.subscriber_count("40000000-0000-4000-8000-000000000004") == 0


def _editable(*, status: ItemStatus = ItemStatus.USABLE) -> EditableItem:
    return EditableItem(
        instruction="Choose one.",
        prompt="What is force?",
        stimulus=None,
        answer_key="Correct",
        distractor_1="Wrong",
        distractor_2=None,
        distractor_3=None,
        status=status,
        irt_a=1,
        irt_b=0,
        beta_error=0.05,
        guess_probability=0.25,
    )


class _FakeIngestor:
    maximum_input_bytes = 1000

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def from_upload(
        self, *, filename: str, content_type: str | None, data: bytes
    ) -> str:
        del content_type, data
        self.calls.append(("upload", filename))
        return "extracted upload"

    async def from_url(self, url: str) -> str:
        self.calls.append(("url", url))
        return "remote"


class _FakeAdminRepository:
    def __init__(self) -> None:
        self.materials: list[SourceMaterial] = []

    async def create_source_material(
        self, *, course: str, title: str, source_url: str, content: str
    ) -> SourceMaterial:
        value = SourceMaterial(
            id=1,
            course=course,
            title=title,
            source_url=source_url,
            content=content,
            content_preview=content,
            added_at=datetime.now(UTC),
        )
        self.materials.append(value)
        return value

    async def list_courses(self) -> tuple[()]:
        return ()

    async def list_source_materials(self, course: str) -> tuple[SourceMaterial, ...]:
        return tuple(value for value in self.materials if value.course == course)

    async def get_source_material(self, material_id: int) -> SourceMaterial | None:
        return next(
            (value for value in self.materials if value.id == material_id), None
        )

    async def list_yg_rules(self, course: str) -> tuple[()]:
        del course
        return ()

    async def create_yg_rule(
        self, course: str, description: str, example: object
    ) -> object:
        raise NotImplementedError

    async def list_items(
        self, course: str, limit: int, offset: int
    ) -> tuple[tuple[AdminItem, ...], int]:
        del course, limit, offset
        return (), 0

    async def get_item(self, yp_id: int) -> AdminItem | None:
        del yp_id
        return None

    async def update_item(self, yp_id: int, edited: EditableItem) -> AdminItem | None:
        del yp_id, edited
        return None

    async def create_item_copy(
        self, yp_id: int, edited: EditableItem
    ) -> AdminItem | None:
        del yp_id, edited
        return None


class _CreatingService:
    async def create_assessment(
        self, command: CreateAssessmentCommand
    ) -> CreateAssessmentResult:
        del command
        test_id = UUID("10000000-0000-4000-8000-000000000001")
        return CreateAssessmentResult(
            test_id=test_id,
            status=SessionStatus.ACTIVE,
            player_url=f"/test/{test_id}",
            missing_nodes=(),
        )
