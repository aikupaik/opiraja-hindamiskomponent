"""Supabase implementation of the isolated admin repository contract."""

from time import perf_counter
from typing import cast

import httpx
from postgrest import APIError, APIResponse
from postgrest.types import CountMethod, JSON
from supabase import AsyncClient

from app.domain.repository import RepositoryDataError, RepositoryUnavailable
from app.observability import record_supabase_execute

from .diagnostics import emit_diagnostic
from .mapping import (
    ADMIN_ITEM_COLUMNS,
    ITEM_TABLE,
    MATERIAL_COLUMNS,
    MATERIAL_TABLE,
    RULE_COLUMNS,
    RULE_TABLE,
    Row,
    decode_admin_item,
    decode_course_rows,
    decode_material,
    decode_rule,
    encode_editable,
    encode_item_copy,
    encode_material,
    encode_rule,
    rows,
)
from .models import AdminItem, CourseChoice, EditableItem, SourceMaterial, YgRule


class SupabaseAdminRepository:
    """Admin persistence using the application's existing async client."""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def list_courses(self) -> tuple[CourseChoice, ...]:
        response = await self._execute(
            self._client.table(MATERIAL_TABLE)
            .select(MATERIAL_COLUMNS)
            .order("lisatud", desc=True)
            .order("id", desc=True),
            "repo_materjalid.list_courses",
        )
        return decode_course_rows(rows(response.data, MATERIAL_TABLE))

    async def list_source_materials(self, course: str) -> tuple[SourceMaterial, ...]:
        response = await self._execute(
            self._client.table(MATERIAL_TABLE)
            .select(MATERIAL_COLUMNS)
            .eq("kursus", course)
            .order("lisatud", desc=True)
            .order("id", desc=True),
            "repo_materjalid.list",
        )
        return tuple(
            decode_material(row, include_content=False)
            for row in rows(response.data, MATERIAL_TABLE)
        )

    async def get_source_material(self, material_id: int) -> SourceMaterial | None:
        response = await self._execute(
            self._client.table(MATERIAL_TABLE)
            .select(MATERIAL_COLUMNS)
            .eq("id", material_id)
            .limit(1),
            "repo_materjalid.get",
        )
        row = self._zero_or_one(response, MATERIAL_TABLE)
        return None if row is None else decode_material(row, include_content=True)

    async def create_source_material(
        self,
        *,
        course: str,
        title: str,
        source_url: str,
        content: str,
    ) -> SourceMaterial:
        response = await self._execute(
            self._client.table(MATERIAL_TABLE)
            .insert(
                cast(
                    JSON,
                    encode_material(
                        course=course,
                        title=title,
                        source_url=source_url,
                        content=content,
                    ),
                )
            )
            .select("id"),
            "repo_materjalid.insert",
        )
        inserted = self._exactly_one(response, MATERIAL_TABLE)
        material = await self.get_source_material(self._integer(inserted, "id"))
        if material is None:
            raise RepositoryUnavailable("source material insert was not observable")
        return material

    async def list_yg_rules(self, course: str) -> tuple[YgRule, ...]:
        response = await self._execute(
            self._client.table(RULE_TABLE)
            .select(RULE_COLUMNS)
            .eq("kursus", course)
            .order("id", desc=True),
            "yg_reeglid.list",
        )
        return tuple(decode_rule(row) for row in rows(response.data, RULE_TABLE))

    async def create_yg_rule(
        self, course: str, description: str, example: object
    ) -> YgRule:
        response = await self._execute(
            self._client.table(RULE_TABLE)
            .insert(cast(JSON, encode_rule(course, description, example)))
            .select(RULE_COLUMNS),
            "yg_reeglid.insert",
        )
        return decode_rule(self._exactly_one(response, RULE_TABLE))

    async def list_items(
        self, course: str, limit: int, offset: int
    ) -> tuple[tuple[AdminItem, ...], int]:
        response = await self._execute(
            self._client.table(ITEM_TABLE)
            .select(ADMIN_ITEM_COLUMNS, count=CountMethod.exact)
            .eq("kursus", course)
            .order("yp_id")
            .range(offset, offset + limit - 1),
            "ylesandepank.audit",
        )
        decoded = tuple(
            decode_admin_item(row) for row in rows(response.data, ITEM_TABLE)
        )
        total = response.count
        if total is None:
            raise RepositoryDataError(
                "item audit response did not include an exact count"
            )
        return decoded, total

    async def get_item(self, yp_id: int) -> AdminItem | None:
        response = await self._execute(
            self._client.table(ITEM_TABLE)
            .select(ADMIN_ITEM_COLUMNS)
            .eq("yp_id", yp_id)
            .limit(1),
            "ylesandepank.get",
        )
        row = self._zero_or_one(response, ITEM_TABLE)
        return None if row is None else decode_admin_item(row)

    async def update_item(self, yp_id: int, edited: EditableItem) -> AdminItem | None:
        response = await self._execute(
            self._client.table(ITEM_TABLE)
            .update(cast(JSON, encode_editable(edited)))
            .eq("yp_id", yp_id)
            .select("yp_id"),
            "ylesandepank.update",
        )
        row = self._zero_or_one(response, ITEM_TABLE)
        if row is None:
            return None
        returned_id = self._integer(row, "yp_id")
        if returned_id != yp_id:
            raise RepositoryDataError("item update returned a different target")
        canonical = await self.get_item(yp_id)
        if canonical is None:
            raise RepositoryUnavailable("updated item was not observable")
        return canonical

    async def create_item_copy(
        self, yp_id: int, edited: EditableItem
    ) -> AdminItem | None:
        source_response = await self._execute(
            self._client.table(ITEM_TABLE).select("*").eq("yp_id", yp_id).limit(1),
            "ylesandepank.copy_source",
        )
        source = self._zero_or_one(source_response, ITEM_TABLE)
        if source is None:
            return None
        inserted_response = await self._execute(
            self._client.table(ITEM_TABLE)
            .insert(cast(JSON, encode_item_copy(source, edited)))
            .select("yp_id"),
            "ylesandepank.insert_copy",
        )
        inserted = self._exactly_one(inserted_response, ITEM_TABLE)
        new_id = self._integer(inserted, "yp_id")
        canonical = await self.get_item(new_id)
        if canonical is None:
            raise RepositoryUnavailable("copied item was not observable")
        return canonical

    async def _execute(self, query: object, operation: str) -> APIResponse:
        started_at = perf_counter()
        try:
            executable = cast("_Executable", query)
            response = await executable.execute()
            count = len(response.data)
            emit_diagnostic(
                source="supabase",
                level="info",
                event_type="supabase_operation",
                payload={
                    "operation": operation,
                    "count": count,
                    "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                },
            )
            return response
        except APIError as error:
            emit_diagnostic(
                source="supabase",
                level="warning",
                event_type="supabase_operation",
                payload={
                    "operation": operation,
                    "count": 0,
                    "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                    "outcome": "failed",
                    "diagnostic": type(error).__name__,
                },
            )
            raise RepositoryUnavailable("Supabase request failed") from error
        except (httpx.HTTPError, TimeoutError) as error:
            emit_diagnostic(
                source="supabase",
                level="warning",
                event_type="supabase_operation",
                payload={
                    "operation": operation,
                    "count": 0,
                    "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                    "outcome": "failed",
                    "diagnostic": type(error).__name__,
                },
            )
            raise RepositoryUnavailable("Supabase request failed") from error
        finally:
            record_supabase_execute(started_at)

    @staticmethod
    def _zero_or_one(response: APIResponse, table: str) -> Row | None:
        values = rows(response.data, table)
        if len(values) > 1:
            raise RepositoryDataError(f"{table} query returned multiple rows")
        return values[0] if values else None

    @classmethod
    def _exactly_one(cls, response: APIResponse, table: str) -> Row:
        row = cls._zero_or_one(response, table)
        if row is None:
            raise RepositoryDataError(f"{table} write returned no row")
        return row

    @staticmethod
    def _integer(row: Row, field: str) -> int:
        value = row.get(field)
        if not isinstance(value, int) or isinstance(value, bool):
            raise RepositoryDataError(f"{field} must be an integer")
        return value


class _Executable:
    async def execute(self) -> APIResponse:
        raise NotImplementedError
