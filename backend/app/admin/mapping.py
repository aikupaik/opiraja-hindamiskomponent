"""Mapping between admin English models and deployed Estonian columns."""

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast

from app.domain.models import ItemStatus
from app.domain.repository import RepositoryDataError

from .models import AdminItem, CourseChoice, EditableItem, SourceMaterial, YgRule

Row = Mapping[str, object]

MATERIAL_TABLE = "repo_materjalid"
RULE_TABLE = "yg_reeglid"
ITEM_TABLE = "ylesandepank"

MATERIAL_COLUMNS = "id,kursus,pealkiri,allika_url,sisu_tekst,lisatud"
RULE_COLUMNS = "id,kursus,reegli_kirjeldus,naidis_json"
ADMIN_ITEM_COLUMNS = (
    "yp_id,kursus,graafi_objekt,graafi_ema_objekt,kognitiivne_tase,"
    "juhis,tyvi,stiimul,voti,distraktor_1,distraktor_2,distraktor_3,"
    "skoor,irt_a,irt_b,beeta_error,g_guess,staatus,kasutamiste_arv,"
    "viimane_kasutus"
)

_STATUS_TO_DB = {
    ItemStatus.DRAFT: "kavand",
    ItemStatus.USABLE: "kasutatav",
    ItemStatus.REVIEW: "läbi vaatamisel",
    ItemStatus.ARCHIVED: "arhiivis",
}
_STATUS_FROM_DB = {value: key for key, value in _STATUS_TO_DB.items()}


def decode_course_rows(rows: Sequence[Row]) -> tuple[CourseChoice, ...]:
    """Use the newest nonblank title for each course, with legacy fallback."""

    choices: dict[str, tuple[str, datetime | None, int]] = {}
    for row in rows:
        title = _nonblank(row, "pealkiri")
        raw_course = row.get("kursus")
        course = (
            title if raw_course is None else _text_value(raw_course, "kursus").strip()
        )
        if not course:
            course = title
        added = _optional_datetime(row, "lisatud")
        row_id = _int(row, "id")
        current = choices.get(course)
        if current is None or _is_newer((added, row_id), (current[1], current[2])):
            choices[course] = (title, added, row_id)
    return tuple(
        CourseChoice(value=course, title=value[0], label=f"{value[0]} ({course})")
        for course, value in sorted(
            choices.items(), key=lambda item: item[0].casefold()
        )
    )


def decode_material(row: Row, *, include_content: bool) -> SourceMaterial:
    content = _text(row, "sisu_tekst")
    preview = content[:400]
    if len(content) > 400:
        preview += "…"
    return SourceMaterial(
        id=_int(row, "id"),
        course=_nonblank(row, "kursus"),
        title=_nonblank(row, "pealkiri"),
        source_url=_optional_text(row, "allika_url"),
        content=content if include_content else None,
        content_preview=preview,
        added_at=_optional_datetime(row, "lisatud"),
    )


def encode_material(
    *, course: str, title: str, source_url: str, content: str
) -> dict[str, object]:
    return {
        "kursus": course,
        "pealkiri": title,
        "allika_url": source_url,
        "sisu_tekst": content,
    }


def decode_rule(row: Row) -> YgRule:
    example = row.get("naidis_json")
    if example is None:
        raise RepositoryDataError("yg_reeglid.naidis_json must be non-null")
    return YgRule(
        id=_int(row, "id"),
        course=_nonblank(row, "kursus"),
        description=_nonblank(row, "reegli_kirjeldus"),
        example=example,
    )


def encode_rule(course: str, description: str, example: object) -> dict[str, object]:
    return {
        "kursus": course,
        "reegli_kirjeldus": description,
        "naidis_json": example,
    }


def decode_admin_item(row: Row) -> AdminItem:
    status_value = _nonblank(row, "staatus")
    try:
        status = _STATUS_FROM_DB[status_value]
    except KeyError as error:
        raise RepositoryDataError(f"unknown item status: {status_value!r}") from error
    return AdminItem(
        yp_id=_int(row, "yp_id"),
        course=_nonblank(row, "kursus"),
        graph_node=_nonblank(row, "graafi_objekt"),
        parent_graph_node=_optional_text(row, "graafi_ema_objekt"),
        cognitive_level=_nonblank(row, "kognitiivne_tase"),
        instruction=_text(row, "juhis"),
        prompt=_text(row, "tyvi"),
        stimulus=_optional_text(row, "stiimul"),
        answer_key=_text(row, "voti"),
        distractor_1=_optional_text(row, "distraktor_1"),
        distractor_2=_optional_text(row, "distraktor_2"),
        distractor_3=_optional_text(row, "distraktor_3"),
        score=_int(row, "skoor"),
        irt_a=_float(row, "irt_a"),
        irt_b=_float(row, "irt_b"),
        beta_error=_float(row, "beeta_error"),
        guess_probability=_float(row, "g_guess"),
        status=status,
        usage_count=_int(row, "kasutamiste_arv"),
        last_used_at=_optional_datetime(row, "viimane_kasutus"),
        created_at=_optional_datetime(row, "loodud"),
        updated_at=_optional_datetime(row, "muudetud"),
    )


def encode_editable(item: EditableItem) -> dict[str, object]:
    return {
        "juhis": item.instruction,
        "tyvi": item.prompt,
        "stiimul": item.stimulus,
        "voti": item.answer_key,
        "distraktor_1": item.distractor_1,
        "distraktor_2": item.distractor_2,
        "distraktor_3": item.distractor_3,
        "staatus": _STATUS_TO_DB[item.status],
        "irt_a": item.irt_a,
        "irt_b": item.irt_b,
        "beeta_error": item.beta_error,
        "g_guess": item.guess_probability,
    }


def encode_item_copy(source: Row, edited: EditableItem) -> dict[str, object]:
    preserved = {
        key: value
        for key, value in source.items()
        if key
        not in {"yp_id", "kasutamiste_arv", "viimane_kasutus", "loodud", "muudetud"}
    }
    return {
        **preserved,
        **encode_editable(edited),
        "kasutamiste_arv": 0,
        "viimane_kasutus": None,
    }


def _is_newer(
    candidate: tuple[datetime | None, int], current: tuple[datetime | None, int]
) -> bool:
    left, right = candidate[0], current[0]
    if left is None or right is None:
        if left is not None:
            return True
        if right is not None:
            return False
        return candidate[1] > current[1]
    return left > right or (left == right and candidate[1] > current[1])


def _text_value(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise RepositoryDataError(f"{field} must be text")
    return value


def _text(row: Row, field: str) -> str:
    if field not in row:
        raise RepositoryDataError(f"missing field: {field}")
    return _text_value(row[field], field)


def _nonblank(row: Row, field: str) -> str:
    value = _text(row, field).strip()
    if not value:
        raise RepositoryDataError(f"{field} must not be blank")
    return value


def _optional_text(row: Row, field: str) -> str | None:
    value = row.get(field)
    if value is None:
        return None
    text = _text_value(value, field).strip()
    return text or None


def _int(row: Row, field: str) -> int:
    value = row.get(field)
    if not isinstance(value, int) or isinstance(value, bool):
        raise RepositoryDataError(f"{field} must be an integer")
    return value


def _float(row: Row, field: str) -> float:
    value = row.get(field)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise RepositoryDataError(f"{field} must be numeric")
    return float(value)


def _optional_datetime(row: Row, field: str) -> datetime | None:
    value = row.get(field)
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise RepositoryDataError(f"{field} must be a timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RepositoryDataError(f"{field} must be an ISO timestamp") from error


def rows(response_data: object, table: str) -> tuple[Row, ...]:
    if not isinstance(response_data, Sequence) or isinstance(
        response_data, (str, bytes, bytearray)
    ):
        raise RepositoryDataError(f"{table} response must be an array")
    sequence = cast(Sequence[object], response_data)
    values: list[Row] = []
    for value in sequence:
        if not isinstance(value, Mapping):
            raise RepositoryDataError(f"{table} response rows must be objects")
        values.append(cast(Row, value))
    return tuple(values)
