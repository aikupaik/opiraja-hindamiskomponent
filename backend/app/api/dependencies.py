"""Dependency accessors kept small so tests can override each seam."""

from typing import Annotated, cast

from fastapi import Depends, Request

from app.admin.diagnostics import DiagnosticHub
from app.admin.ingestion import SourceIngestor
from app.admin.repository import AdminRepository
from app.admin.kst_configuration import KstConfigurationRepository
from app.config import Settings
from app.domain.repository import AssessmentRepository
from app.integrations.kst_engine import KstConfigurationValidator, KstEngine
from app.services.assessment import AssessmentService
from app.api.tokens import TokenService


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_token_service(request: Request) -> TokenService:
    return cast(TokenService, request.app.state.token_service)


def get_repository(request: Request) -> AssessmentRepository:
    return cast(AssessmentRepository, request.app.state.repository)


def get_kst_engine(request: Request) -> KstEngine:
    return cast(KstEngine, request.app.state.kst_engine)


def get_kst_configuration_validator(request: Request) -> KstConfigurationValidator:
    return cast(KstConfigurationValidator, request.app.state.kst_engine)


def get_admin_repository(request: Request) -> AdminRepository:
    return cast(AdminRepository, request.app.state.admin_repository)


def get_kst_configuration_repository(request: Request) -> KstConfigurationRepository:
    return cast(
        KstConfigurationRepository,
        request.app.state.kst_configuration_repository,
    )


def get_source_ingestor(request: Request) -> SourceIngestor:
    return cast(SourceIngestor, request.app.state.source_ingestor)


def get_diagnostic_hub(request: Request) -> DiagnosticHub:
    return cast(DiagnosticHub, request.app.state.diagnostic_hub)


def get_assessment_service(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    repository: Annotated[AssessmentRepository, Depends(get_repository)],
    engine: Annotated[KstEngine, Depends(get_kst_engine)],
) -> AssessmentService:
    """Reuse production wiring, or rebuild it when a test overrides a seam."""

    state_repository = cast(AssessmentRepository, request.app.state.repository)
    state_engine = cast(KstEngine, request.app.state.kst_engine)
    if repository is state_repository and engine is state_engine:
        return cast(AssessmentService, request.app.state.assessment_service)
    return AssessmentService(
        repository,
        engine,
        max_graph_nodes=settings.max_graph_nodes,
    )
