"""Application service for validating and activating KST configurations."""

from uuid import UUID

from app.domain.repository import RepositoryDataError
from app.integrations.kst_engine import RValidationError
from app.integrations.kst_engine import KstConfigurationValidator

from .kst_configuration import (
    KstConfigurationAlreadyExists,
    KstConfigurationRepository,
    KstConfigurationVersion,
)


class KstConfigurationAlreadyActive(RuntimeError):
    """The requested version is already the active version."""


class KstConfigurationVersionNotFound(RuntimeError):
    """The requested immutable version does not exist."""


class KstConfigurationService:
    def __init__(
        self,
        repository: KstConfigurationRepository,
        engine: KstConfigurationValidator,
    ) -> None:
        self._repository = repository
        self._engine = engine

    async def history(self) -> tuple[UUID | None, tuple[KstConfigurationVersion, ...]]:
        versions = await self._repository.list_configuration_versions()
        active = next((version for version in versions if version.is_active), None)
        return (None if active is None else active.id, versions)

    async def create_draft(
        self, configuration: dict[str, object], created_by: str
    ) -> KstConfigurationVersion:
        canonical, configuration_hash = await self._validate(configuration)
        return await self._repository.insert_configuration_version(
            schema_version=1,
            configuration=canonical,
            configuration_hash=configuration_hash,
            created_by=created_by,
        )

    async def activate(
        self, version_id: UUID, activated_by: str
    ) -> KstConfigurationVersion:
        version = await self._repository.get_configuration_version(version_id)
        if version is None:
            raise KstConfigurationVersionNotFound
        active = await self._repository.get_active_configuration()
        if active is not None and active.id == version_id:
            raise KstConfigurationAlreadyActive
        canonical, configuration_hash = await self._validate(version.configuration)
        if canonical != version.configuration or configuration_hash != version.configuration_hash:
            raise RepositoryDataError(
                "stored KST configuration does not match R canonicalization"
            )
        activated = await self._repository.activate_configuration_version(
            version_id, activated_by
        )
        if activated is None:
            raise RepositoryDataError("KST activation was not observable")
        return activated

    async def _validate(
        self, configuration: dict[str, object]
    ) -> tuple[dict[str, object], str]:
        result = await self._engine.validate_configuration(configuration)
        return result


__all__ = [
    "KstConfigurationAlreadyActive",
    "KstConfigurationAlreadyExists",
    "KstConfigurationService",
    "KstConfigurationVersionNotFound",
    "RValidationError",
]
