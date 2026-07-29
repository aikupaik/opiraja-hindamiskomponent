"""Admin-specific persistence protocol."""

from typing import Protocol

from .models import AdminItem, CourseChoice, EditableItem, SourceMaterial, YgRule


class AdminRepository(Protocol):
    async def list_courses(self) -> tuple[CourseChoice, ...]: ...

    async def list_source_materials(
        self, course: str
    ) -> tuple[SourceMaterial, ...]: ...

    async def get_source_material(self, material_id: int) -> SourceMaterial | None: ...

    async def create_source_material(
        self,
        *,
        course: str,
        title: str,
        source_url: str,
        content: str,
    ) -> SourceMaterial: ...

    async def list_yg_rules(self, course: str) -> tuple[YgRule, ...]: ...

    async def create_yg_rule(
        self, course: str, description: str, example: object
    ) -> YgRule: ...

    async def list_items(
        self, course: str, limit: int, offset: int
    ) -> tuple[tuple[AdminItem, ...], int]: ...

    async def get_item(self, yp_id: int) -> AdminItem | None: ...

    async def update_item(
        self, yp_id: int, edited: EditableItem
    ) -> AdminItem | None: ...

    async def create_item_copy(
        self, yp_id: int, edited: EditableItem
    ) -> AdminItem | None: ...
