"""HTTP-level contract tests for the concrete asynchronous Supabase adapter."""

import asyncio
import json
from collections.abc import Awaitable, Callable, Coroutine, Mapping
from dataclasses import replace
from typing import cast

import httpx
import pytest
from postgrest import AsyncPostgrestClient
from supabase import AsyncClient

from app.domain.models import (
    AnswerCommitOutcome,
    GraphCacheEntry,
    GraphDefinition,
    KnowledgeState,
    YgOrder,
    YgStatus,
)
from app.domain.repository import RepositoryDataError, RepositoryUnavailable
from app.observability import collect_dependency_metrics
from app.persistence.supabase_mapping import (
    ANSWER_TABLE,
    ITEM_TABLE,
    SESSION_TABLE,
    YG_ORDER_TABLE,
    encode_answer,
    encode_graph_entry,
    encode_item,
    encode_session,
)
from app.persistence.supabase_repository import SupabaseAssessmentRepository
from tests.factories import (
    ITEM_ID,
    NEXT_ITEM_ID,
    NOW,
    SUBMISSION_ID,
    TEST_ID,
    make_activation,
    make_answer,
    make_item,
    make_session,
    make_transition,
)

Handler = Callable[[httpx.Request], httpx.Response]
AsyncHandler = Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]


async def _with_repository[T](handler: Handler, scenario: Callable[
    [SupabaseAssessmentRepository], Awaitable[T]
]) -> T:
    async with httpx.AsyncClient(
        base_url="https://database.test",
        transport=httpx.MockTransport(handler),
    ) as transport:
        postgrest = AsyncPostgrestClient(
            "https://database.test",
            http_client=transport,
        )
        repository = SupabaseAssessmentRepository(cast(AsyncClient, postgrest))
        return await scenario(repository)


async def _with_async_repository[T](
    handler: AsyncHandler,
    scenario: Callable[[SupabaseAssessmentRepository], Awaitable[T]],
) -> T:
    async with httpx.AsyncClient(
        base_url="https://database.test",
        transport=httpx.MockTransport(handler),
    ) as transport:
        postgrest = AsyncPostgrestClient(
            "https://database.test",
            http_client=transport,
        )
        repository = SupabaseAssessmentRepository(cast(AsyncClient, postgrest))
        return await scenario(repository)


def _response(data: object, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=data)


def _body(request: httpx.Request) -> dict[str, object]:
    value = json.loads(request.content)
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _path_table(request: httpx.Request) -> str:
    return request.url.path.rsplit("/", 1)[-1]


def _with_server_fields(row: Mapping[str, object]) -> dict[str, object]:
    result = dict(row)
    if "graaf_hash" in result and "graafi_struktuur" in result:
        result.setdefault("loodud", None)
    if "id" in result and "graafi_objektid" in result:
        result.setdefault("loodud", NOW.isoformat())
    return result


def test_reads_use_exact_filters_stable_order_and_request_metrics() -> None:
    requests: list[httpx.Request] = []
    first = make_item()
    second = make_item(NEXT_ITEM_ID)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        table = _path_table(request)
        if table == ITEM_TABLE:
            if "yp_id" in request.url.params:
                return _response([encode_item(first)])
            node = request.url.params.get("graafi_objekt")
            assert request.url.params.get("staatus") == "eq.kasutatav"
            assert request.url.params.get("order") == "yp_id.asc"
            if node == "eq.A,B":
                assert request.url.params.get("limit") == "1"
                return _response([encode_item(first)])
            if node == "eq.A":
                return _response([encode_item(first), encode_item(second)])
            return _response([])
        if table == SESSION_TABLE:
            assert request.url.params.get("limit") == "1"
            return _response([encode_session(make_session())])
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    async def scenario(repository: SupabaseAssessmentRepository) -> None:
        with collect_dependency_metrics() as metrics:
            session = await repository.get_session(TEST_ID)
            coverage = await repository.resolve_usable_coverage(("A,B", "missing"))
            items = await repository.list_usable_items("A", (ITEM_ID,))
            item = await repository.get_item(ITEM_ID)

        assert session == make_session()
        assert [entry.covered for entry in coverage] == [True, False]
        assert [candidate.item_id for candidate in items] == [NEXT_ITEM_ID, ITEM_ID]
        assert item == first
        assert metrics.supabase_execute_count == 5
        assert metrics.supabase_seconds >= 0

    asyncio.run(_with_repository(handler, scenario))
    assert len(requests) == 5


def test_graph_cache_ignores_conflicts_and_reloads_canonical_row() -> None:
    entry = GraphCacheEntry(
        graph_hash="kst-graph-v1:sha256:abc",
        graph=GraphDefinition(("A",), ()),
        knowledge_states=(KnowledgeState(()), KnowledgeState(("A",))),
    )
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            assert request.url.params.get("on_conflict") == "graaf_hash"
            prefer = request.headers["prefer"]
            assert "resolution=ignore-duplicates" in prefer
            assert _body(request) == encode_graph_entry(entry)
            return _response([])
        assert request.method == "GET"
        assert request.url.params.get("graaf_hash") == f"eq.{entry.graph_hash}"
        return _response([_with_server_fields(encode_graph_entry(entry))])

    async def scenario(repository: SupabaseAssessmentRepository) -> None:
        assert await repository.insert_cached_graph_if_absent(entry) == entry

    asyncio.run(_with_repository(handler, scenario))
    assert [request.method for request in requests] == ["POST", "GET"]


def test_preparing_compare_and_set_and_yg_in_flight_deduplication() -> None:
    from tests.factories import make_preparing_session

    preparing = make_preparing_session()
    session_row = encode_session(preparing)
    orders: list[dict[str, object]] = []
    activation = make_activation()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal session_row
        table = _path_table(request)
        if table == SESSION_TABLE and request.method == "PATCH":
            assert request.url.params.get("test_id") == f"eq.{TEST_ID}"
            assert request.url.params.get("staatus") == "eq.planeerimisel"
            session_row = {**session_row, **_body(request)}
            return _response([session_row])
        if table == YG_ORDER_TABLE and request.method == "GET":
            assert request.url.params.get("test_id") == f"eq.{TEST_ID}"
            assert request.url.params.get("staatus") == "in.(ootel,tootmises)"
            assert request.url.params.get("order") == "id.desc"
            return _response(orders[-1:] if orders else [])
        if table == YG_ORDER_TABLE and request.method == "POST":
            stored = _with_server_fields({"id": 1, **_body(request)})
            orders.append(stored)
            return _response([stored])
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    async def scenario(repository: SupabaseAssessmentRepository) -> None:
        active = await repository.activate_session(activation)
        assert active.status.value == "active"
        order = YgOrder(
            order_id=None,
            test_id=TEST_ID,
            course="",
            nodes=("A",),
            cognitive_level="mõistab",
            volume=3,
            status=YgStatus.PENDING,
        )
        left, right = await asyncio.gather(
            repository.create_yg_order_if_no_pending(order),
            repository.create_yg_order_if_no_pending(replace(order, nodes=("B",))),
        )
        assert left == right
        assert len(orders) == 1

    asyncio.run(_with_repository(handler, scenario))


class _AnswerStore:
    def __init__(self) -> None:
        self.answer: dict[str, object] | None = None
        self.item = cast(dict[str, object], encode_item(make_item()))
        self.session = cast(dict[str, object], encode_session(make_session()))
        self.telemetry_updates = 0
        self.session_updates = 0
        self.calls: list[tuple[str, str]] = []
        self.fail_table: str | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        table = _path_table(request)
        self.calls.append((request.method, table))
        if table == self.fail_table:
            return _response(
                {
                    "code": "PGRST000",
                    "message": "database unavailable",
                    "details": None,
                    "hint": None,
                },
                503,
            )
        if table == ANSWER_TABLE:
            return self._answers(request)
        if table == ITEM_TABLE:
            return self._items(request)
        if table == SESSION_TABLE:
            return self._sessions(request)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    def _answers(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            if self.answer is not None:
                return _response(
                    {
                        "code": "23505",
                        "message": "duplicate key",
                        "details": None,
                        "hint": None,
                    },
                    409,
                )
            self.answer = _body(request)
            return _response([self.answer])
        assert request.url.params.get("vastus_id") == f"eq.{SUBMISSION_ID}"
        return _response([] if self.answer is None else [self.answer])

    def _items(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            assert request.url.params.get("yp_id") == f"eq.{ITEM_ID}"
            return _response([self.item])
        expected = request.url.params.get("kasutamiste_arv")
        if expected != f"eq.{self.item['kasutamiste_arv']}":
            return _response([])
        self.item.update(_body(request))
        self.telemetry_updates += 1
        return _response([self.item])

    def _sessions(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return _response([self.session])
        expected = request.url.params.get(
            "tp_seisund->current_question->>submission_id"
        )
        current = cast(
            dict[str, object],
            cast(dict[str, object], self.session["tp_seisund"])[
                "current_question"
            ],
        )
        if (
            request.url.params.get("staatus") != "eq.aktiivne"
            or expected != f"eq.{current['submission_id']}"
        ):
            return _response([])
        self.session.update(_body(request))
        self.session_updates += 1
        return _response([self.session])


def test_answer_commit_is_sequential_exactly_once_and_replays() -> None:
    store = _AnswerStore()

    async def scenario(repository: SupabaseAssessmentRepository) -> None:
        first = await repository.commit_answer(
            SUBMISSION_ID, make_answer(), make_transition()
        )
        retry = await repository.commit_answer(
            SUBMISSION_ID, make_answer(), make_transition()
        )

        assert first.outcome is AnswerCommitOutcome.APPLIED
        assert retry.outcome is AnswerCommitOutcome.REPLAYED
        assert store.telemetry_updates == 1
        assert store.session_updates == 1
        assert store.answer is not None
        assert store.answer["vastus_id"] == str(SUBMISSION_ID)
        assert store.calls[:4] == [
            ("POST", ANSWER_TABLE),
            ("GET", ITEM_TABLE),
            ("PATCH", ITEM_TABLE),
            ("PATCH", SESSION_TABLE),
        ]

    asyncio.run(_with_repository(store, scenario))


def test_existing_identical_answer_recovers_without_telemetry() -> None:
    store = _AnswerStore()
    store.answer = cast(dict[str, object], encode_answer(make_answer()))

    async def scenario(repository: SupabaseAssessmentRepository) -> None:
        result = await repository.commit_answer(
            SUBMISSION_ID, make_answer(), make_transition()
        )
        assert result.outcome is AnswerCommitOutcome.RECOVERED
        assert store.telemetry_updates == 0
        assert store.session_updates == 1

    asyncio.run(_with_repository(store, scenario))


def test_conflicting_answer_payload_is_classified_without_writes() -> None:
    store = _AnswerStore()
    store.answer = cast(
        dict[str, object],
        encode_answer(make_answer(selected_answer="different")),
    )

    async def scenario(repository: SupabaseAssessmentRepository) -> None:
        result = await repository.commit_answer(
            SUBMISSION_ID, make_answer(), make_transition()
        )
        assert result.outcome is AnswerCommitOutcome.PAYLOAD_CONFLICT
        assert store.telemetry_updates == 0
        assert store.session_updates == 0

    asyncio.run(_with_repository(store, scenario))


def test_concurrent_duplicate_answers_have_one_result_and_telemetry_update() -> None:
    store = _AnswerStore()

    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0)
        return store(request)

    async def scenario(repository: SupabaseAssessmentRepository) -> None:
        first, second = await asyncio.gather(
            repository.commit_answer(
                SUBMISSION_ID, make_answer(), make_transition()
            ),
            repository.commit_answer(
                SUBMISSION_ID, make_answer(), make_transition()
            ),
        )
        assert {
            first.outcome,
            second.outcome,
        } in (
            {
                AnswerCommitOutcome.APPLIED,
                AnswerCommitOutcome.REPLAYED,
            },
            {
                AnswerCommitOutcome.RECOVERED,
                AnswerCommitOutcome.REPLAYED,
            },
        )
        assert store.telemetry_updates == 1
        assert store.session_updates == 1

    asyncio.run(_with_async_repository(handler, scenario))


@pytest.mark.parametrize("table", [ANSWER_TABLE, ITEM_TABLE, SESSION_TABLE])
def test_failure_at_each_answer_persistence_stage_is_unavailable(table: str) -> None:
    store = _AnswerStore()
    store.fail_table = table

    async def scenario(repository: SupabaseAssessmentRepository) -> None:
        with pytest.raises(RepositoryUnavailable, match="Supabase request failed"):
            await repository.commit_answer(
                SUBMISSION_ID, make_answer(), make_transition()
            )
        if table == ANSWER_TABLE:
            assert store.answer is None
            assert store.telemetry_updates == 0
            return

        assert store.answer is not None
        assert store.telemetry_updates == (1 if table == SESSION_TABLE else 0)
        store.fail_table = None
        recovered = await repository.commit_answer(
            SUBMISSION_ID, make_answer(), make_transition()
        )
        assert recovered.outcome is AnswerCommitOutcome.RECOVERED
        # Recovery never guesses whether an interrupted request reached
        # telemetry; it only increments after the winning answer insert.
        assert store.telemetry_updates == (1 if table == SESSION_TABLE else 0)

    asyncio.run(_with_repository(store, scenario))


def test_unavailable_and_malformed_rows_are_distinct() -> None:
    def unavailable(_: httpx.Request) -> httpx.Response:
        return _response(
            {
                "code": "PGRST000",
                "message": "connection failed",
                "details": None,
                "hint": None,
            },
            503,
        )

    async def unavailable_scenario(
        repository: SupabaseAssessmentRepository,
    ) -> None:
        with pytest.raises(RepositoryUnavailable):
            await repository.is_ready()

    asyncio.run(_with_repository(unavailable, unavailable_scenario))

    def malformed(_: httpx.Request) -> httpx.Response:
        return _response([{"test_id": str(TEST_ID)}])

    async def malformed_scenario(repository: SupabaseAssessmentRepository) -> None:
        with pytest.raises(RepositoryDataError, match="missing required field"):
            await repository.get_session(TEST_ID)

    asyncio.run(_with_repository(malformed, malformed_scenario))
