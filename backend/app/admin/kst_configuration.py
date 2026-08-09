"""Domain contract and Supabase adapter for immutable KST configuration."""

from dataclasses import dataclass, replace
from datetime import datetime
from collections.abc import Mapping
from time import perf_counter
from typing import Protocol, cast
from uuid import UUID

import httpx
from postgrest import APIError, APIResponse
from postgrest.types import JSON
from supabase import AsyncClient

from app.domain.repository import RepositoryDataError, RepositoryUnavailable
from app.observability import record_supabase_execute

KST_VERSIONS_TABLE = "kst_configuration_versions"
KST_ACTIVATIONS_TABLE = "kst_configuration_activations"


@dataclass(frozen=True, slots=True)
class KstConfigurationVersion:
    id: UUID
    schema_version: int
    configuration: dict[str, object]
    configuration_hash: str
    created_by: str
    created_at: datetime
    is_active: bool = False
    last_activated_by: str | None = None
    last_activated_at: datetime | None = None


class KstConfigurationRepository(Protocol):
    async def get_active_configuration(self) -> KstConfigurationVersion | None: ...

    async def list_configuration_versions(
        self,
    ) -> tuple[KstConfigurationVersion, ...]: ...

    async def insert_configuration_version(
        self,
        *,
        schema_version: int,
        configuration: dict[str, object],
        configuration_hash: str,
        created_by: str,
    ) -> KstConfigurationVersion: ...

    async def activate_configuration_version(
        self, version_id: UUID, activated_by: str
    ) -> KstConfigurationVersion | None: ...

    async def get_configuration_version(
        self, version_id: UUID
    ) -> KstConfigurationVersion | None: ...


class KstConfigurationAlreadyExists(RuntimeError):
    """The immutable configuration hash already has a stored version."""


class SupabaseKstConfigurationRepository:
    """Append-only KST configuration persistence over PostgREST."""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def get_active_configuration(self) -> KstConfigurationVersion | None:
        activation_response = await self._execute(
            self._client.table(KST_ACTIVATIONS_TABLE)
            .select("id,configuration_version_id,activated_by,activated_at")
            .order("id", desc=True)
            .limit(1),
            "kst_configuration.active_activation",
        )
        activation = _one_or_none(activation_response, KST_ACTIVATIONS_TABLE)
        if activation is None:
            return None
        version_id = _uuid(activation, "configuration_version_id")
        version = await self.get_configuration_version(version_id)
        if version is None:
            raise RepositoryDataError("active KST configuration version is missing")
        return _with_activation(
            version,
            activated_by=_text(activation, "activated_by"),
            activated_at=_datetime(activation, "activated_at"),
            is_active=True,
        )

    async def list_configuration_versions(
        self,
    ) -> tuple[KstConfigurationVersion, ...]:
        versions_response = await self._execute(
            self._client.table(KST_VERSIONS_TABLE)
            .select(
                "id,schema_version,configuration,configuration_hash,created_by,created_at"
            )
            .order("created_at", desc=True)
            .order("id", desc=True),
            "kst_configuration.versions",
        )
        activation_response = await self._execute(
            self._client.table(KST_ACTIVATIONS_TABLE)
            .select("id,configuration_version_id,activated_by,activated_at")
            .order("id", desc=True),
            "kst_configuration.activations",
        )
        activations = _latest_activations(activation_response)
        active_id = (
            max(activations.values(), key=lambda value: value[0])[1]
            if activations
            else None
        )
        return tuple(
            _version_from_row(
                row,
                None
                if _uuid(row, "id") not in activations
                else (
                    activations[_uuid(row, "id")][2],
                    activations[_uuid(row, "id")][3],
                ),
                is_active=_uuid(row, "id") == active_id,
            )
            for row in _rows(versions_response, KST_VERSIONS_TABLE)
        )

    async def get_configuration_version(
        self, version_id: UUID
    ) -> KstConfigurationVersion | None:
        response = await self._execute(
            self._client.table(KST_VERSIONS_TABLE)
            .select(
                "id,schema_version,configuration,configuration_hash,created_by,created_at"
            )
            .eq("id", str(version_id))
            .limit(1),
            "kst_configuration.get",
        )
        row = _one_or_none(response, KST_VERSIONS_TABLE)
        return None if row is None else _version_from_row(row, None)

    async def insert_configuration_version(
        self,
        *,
        schema_version: int,
        configuration: dict[str, object],
        configuration_hash: str,
        created_by: str,
    ) -> KstConfigurationVersion:
        try:
            response = await self._execute(
                self._client.table(KST_VERSIONS_TABLE)
                .insert(
                    cast(
                        JSON,
                        {
                            "schema_version": schema_version,
                            "configuration": configuration,
                            "configuration_hash": configuration_hash,
                            "created_by": created_by,
                        },
                    )
                )
                .select(
                    "id,schema_version,configuration,configuration_hash,created_by,created_at"
                ),
                "kst_configuration.insert",
            )
        except RepositoryUnavailable as error:
            if isinstance(error.__cause__, APIError) and getattr(
                error.__cause__, "code", None
            ) == "23505":
                raise KstConfigurationAlreadyExists from error
            raise
        row = _one(response, KST_VERSIONS_TABLE)
        return _version_from_row(row, None)

    async def activate_configuration_version(
        self, version_id: UUID, activated_by: str
    ) -> KstConfigurationVersion | None:
        response = await self._execute(
            self._client.table(KST_ACTIVATIONS_TABLE)
            .insert(
                cast(
                    JSON,
                    {
                        "configuration_version_id": str(version_id),
                        "activated_by": activated_by,
                    },
                )
            )
            .select("id,configuration_version_id,activated_by,activated_at"),
            "kst_configuration.activate",
        )
        activation = _one_or_none(response, KST_ACTIVATIONS_TABLE)
        if activation is None:
            return None
        version = await self.get_configuration_version(version_id)
        if version is None:
            raise RepositoryDataError("activated KST configuration version is missing")
        return _with_activation(
            version,
            activated_by=_text(activation, "activated_by"),
            activated_at=_datetime(activation, "activated_at"),
            is_active=True,
        )

    async def _execute(self, query: object, operation: str) -> APIResponse:
        started_at = perf_counter()
        try:
            response = await cast(_Executable, query).execute()
            return response
        except (APIError, httpx.HTTPError, TimeoutError) as error:
            raise RepositoryUnavailable("Supabase request failed") from error
        finally:
            record_supabase_execute(started_at)


class _Executable(Protocol):
    async def execute(self) -> APIResponse: ...


def _rows(response: APIResponse, table: str) -> tuple[dict[str, object], ...]:
    value = cast(list[object], response.data)
    rows: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise RepositoryDataError(f"{table} response rows must be objects")
        rows.append(cast(dict[str, object], item))
    return tuple(rows)


def _one(response: APIResponse, table: str) -> dict[str, object]:
    rows = _rows(response, table)
    if len(rows) != 1:
        raise RepositoryDataError(f"{table} write returned {len(rows)} rows")
    return rows[0]


def _one_or_none(response: APIResponse, table: str) -> dict[str, object] | None:
    rows = _rows(response, table)
    if len(rows) > 1:
        raise RepositoryDataError(f"{table} query returned multiple rows")
    return rows[0] if rows else None


def _text(row: dict[str, object], field: str) -> str:
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise RepositoryDataError(f"{field} must be non-blank text")
    return value


def _uuid(row: dict[str, object], field: str) -> UUID:
    value = row.get(field)
    try:
        return UUID(str(value))
    except (TypeError, ValueError) as error:
        raise RepositoryDataError(f"{field} must be a UUID") from error


def _integer(row: dict[str, object], field: str) -> int:
    value = row.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise RepositoryDataError(f"{field} must be an integer")
    return value


def _datetime(row: dict[str, object], field: str) -> datetime:
    value = row.get(field)
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise RepositoryDataError(f"{field} must be a timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RepositoryDataError(f"{field} must be a timestamp") from error


def _configuration(row: dict[str, object]) -> dict[str, object]:
    value = row.get("configuration")
    if not isinstance(value, dict):
        raise RepositoryDataError("configuration must be a JSON object")
    return cast(dict[str, object], value)


def _version_from_row(
    row: dict[str, object],
    activation: tuple[str, datetime] | None,
    *,
    is_active: bool = False,
) -> KstConfigurationVersion:
    return KstConfigurationVersion(
        id=_uuid(row, "id"),
        schema_version=_integer(row, "schema_version"),
        configuration=_configuration(row),
        configuration_hash=_text(row, "configuration_hash"),
        created_by=_text(row, "created_by"),
        created_at=_datetime(row, "created_at"),
        is_active=is_active,
        last_activated_by=None if activation is None else activation[0],
        last_activated_at=None if activation is None else activation[1],
    )


def _with_activation(
    version: KstConfigurationVersion,
    *,
    activated_by: str,
    activated_at: datetime,
    is_active: bool,
) -> KstConfigurationVersion:
    return replace(
        version,
        is_active=is_active,
        last_activated_by=activated_by,
        last_activated_at=activated_at,
    )


def _latest_activations(
    response: APIResponse,
) -> dict[UUID, tuple[int, UUID, str, datetime]]:
    result: dict[UUID, tuple[int, UUID, str, datetime]] = {}
    for row in _rows(response, KST_ACTIVATIONS_TABLE):
        version_id = _uuid(row, "configuration_version_id")
        if version_id not in result:
            result[version_id] = (
                _integer(row, "id"),
                version_id,
                _text(row, "activated_by"),
                _datetime(row, "activated_at"),
            )
    return result
