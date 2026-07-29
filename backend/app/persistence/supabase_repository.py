"""Concrete asynchronous Supabase implementation of the assessment repository."""

import asyncio
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from time import perf_counter
from typing import Protocol, Self, cast

import httpx
from postgrest import APIError, APIResponse
from supabase import AsyncClient

from app.admin.diagnostics import emit_diagnostic
from app.domain.models import *
from app.domain.repository import *
from app.observability import record_supabase_execute

from .supabase_mapping import *

_UNIQUE_VIOLATION = "23505"
_TELEMETRY_RETRIES = 8


class _ExecutableQuery(Protocol):
    async def execute(self) -> APIResponse: ...


class _FilterQuery(_ExecutableQuery, Protocol):
    def eq(self, column: str, value: object) -> Self: ...


class SupabaseAssessmentRepository:
    """Awaited PostgREST operations with strict domain decoding."""

    def __init__(self, client: AsyncClient) -> None:
        self._client = client
        self._yg_locks: defaultdict[TestId, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def get_cached_graph(self, graph_hash: str) -> GraphCacheEntry | None:
        response = await self._execute(
            self._apply_filters(
                self._client.table(GRAPH_TABLE).select(GRAPH_COLUMNS),
                graph_hash_filters(graph_hash),
            ).limit(1),
            operation="graafid_kst.get",
        )
        row = self._zero_or_one(response, GRAPH_TABLE)
        return None if row is None else decode_graph_entry(row)

    async def insert_cached_graph_if_absent(
        self, entry: GraphCacheEntry
    ) -> GraphCacheEntry:
        await self._execute(
            self._client.table(GRAPH_TABLE).upsert(
                encode_graph_entry(entry),
                on_conflict=GRAPH_CONFLICT_COLUMN,
                ignore_duplicates=True,
            ),
            operation="graafid_kst.insert_if_absent",
        )
        canonical = await self.get_cached_graph(entry.graph_hash)
        if canonical is None:
            raise RepositoryUnavailable("graph cache insert was not observable")
        return canonical

    async def create_session(self, session: AssessmentSession) -> AssessmentSession:
        response = await self._execute(
            self._client.table(SESSION_TABLE)
            .insert(encode_session(session))
            .select(SESSION_COLUMNS),
            operation="testisessioonid.insert",
        )
        return decode_session(self._exactly_one(response, SESSION_TABLE))

    async def get_session(self, test_id: TestId) -> AssessmentSession | None:
        response = await self._execute(
            self._apply_filters(
                self._client.table(SESSION_TABLE).select(SESSION_COLUMNS),
                session_id_filters(test_id),
            ).limit(1),
            operation="testisessioonid.get",
        )
        row = self._zero_or_one(response, SESSION_TABLE)
        return None if row is None else decode_session(row)

    async def activate_session(self, command: ActivationCommand) -> AssessmentSession:
        response = await self._execute(
            self._apply_filters(
                self._client.table(SESSION_TABLE)
                .update(activation_updates(command))
                .select(SESSION_COLUMNS),
                preparing_session_filters(command.test_id),
            ),
            operation="testisessioonid.activate",
        )
        row = self._zero_or_one(response, SESSION_TABLE)
        if row is not None:
            return decode_session(row)
        session = await self._require_session(command.test_id)
        if session.status is SessionStatus.ACTIVE:
            return session
        raise RepositoryDataError(
            f"cannot activate session in status {session.status.value}"
        )

    async def mark_session_failed(self, test_id: TestId) -> AssessmentSession:
        response = await self._execute(
            self._apply_filters(
                self._client.table(SESSION_TABLE)
                .update(failed_session_updates())
                .select(SESSION_COLUMNS),
                preparing_session_filters(test_id),
            ),
            operation="testisessioonid.fail",
        )
        row = self._zero_or_one(response, SESSION_TABLE)
        if row is not None:
            return decode_session(row)
        session = await self._require_session(test_id)
        if session.status is SessionStatus.FAILED:
            return session
        raise RepositoryDataError(
            f"cannot fail session in status {session.status.value}"
        )

    async def update_preparing_inventory_plan(
        self, test_id: TestId, state: PlayerState
    ) -> AssessmentSession:
        response = await self._execute(
            self._apply_filters(
                self._client.table(SESSION_TABLE)
                .update(preparing_inventory_updates(state))
                .select(SESSION_COLUMNS),
                preparing_session_filters(test_id),
            ),
            operation="testisessioonid.update_inventory",
        )
        row = self._zero_or_one(response, SESSION_TABLE)
        if row is not None:
            return decode_session(row)
        session = await self._require_session(test_id)
        if session.status is not SessionStatus.PREPARING:
            return session
        raise RepositoryUnavailable(
            "preparing inventory plan update was not observable"
        )

    async def is_ready(self) -> bool:
        await self._execute(
            self._client.table(SESSION_TABLE).select(SESSION_ID_COLUMN).limit(1),
            operation="testisessioonid.readiness",
        )
        return True

    async def list_usable_items_for_nodes(
        self, nodes: tuple[str, ...]
    ) -> tuple[AssessmentItem, ...]:
        items: list[AssessmentItem] = []
        for node in nodes:
            response = await self._execute(
                self._apply_filters(
                    self._client.table(ITEM_TABLE).select(ITEM_COLUMNS),
                    item_eligibility_filters(node),
                ).order(ITEM_ORDER_COLUMN),
                operation="ylesandepank.list_usable",
            )
            decoded_values: list[AssessmentItem] = []
            for row in self._rows(response, ITEM_TABLE):
                try:
                    item = decode_item(row)
                except RepositoryDataError:
                    continue
                if is_domain_valid_usable_item(item):
                    decoded_values.append(item)
            decoded = tuple(decoded_values)
            if any(item.node != node for item in decoded):
                raise RepositoryDataError(
                    "usable item query returned an item for another node"
                )
            items.extend(decoded)
        if len({item.item_id for item in items}) != len(items):
            raise RepositoryDataError("usable item query returned duplicate IDs")
        return tuple(items)

    async def load_items_by_ids(
        self, item_ids: tuple[ItemId, ...]
    ) -> tuple[AssessmentItem, ...]:
        if len(set(item_ids)) != len(item_ids):
            raise RepositoryDataError("pool item IDs must be unique")
        items: list[AssessmentItem] = []
        for item_id in item_ids:
            filters = item_id_filters(item_id)
            filters[ITEM_STATUS_COLUMN] = USABLE_ITEM_STATUS
            response = await self._execute(
                self._apply_filters(
                    self._client.table(ITEM_TABLE).select(ITEM_COLUMNS),
                    filters,
                ).limit(1),
                operation="ylesandepank.load_pool_item",
            )
            row = self._zero_or_one(response, ITEM_TABLE)
            if row is not None:
                try:
                    item = decode_item(row)
                except RepositoryDataError:
                    continue
                if is_domain_valid_usable_item(item):
                    items.append(item)
        return tuple(items)

    async def get_item(self, item_id: ItemId) -> AssessmentItem | None:
        response = await self._execute(
            self._apply_filters(
                self._client.table(ITEM_TABLE).select(ITEM_COLUMNS),
                item_id_filters(item_id),
            ).limit(1),
            operation="ylesandepank.get",
        )
        row = self._zero_or_one(response, ITEM_TABLE)
        return None if row is None else decode_item(row)

    async def get_latest_yg_order(self, test_id: TestId) -> YgOrder | None:
        response = await self._execute(
            self._apply_filters(
                self._client.table(YG_ORDER_TABLE).select(YG_ORDER_COLUMNS),
                yg_order_test_filters(test_id),
            )
            .order(YG_ORDER_ORDER_COLUMN, desc=True)
            .limit(1),
            operation="yg_tellimused.latest",
        )
        row = self._zero_or_one(response, YG_ORDER_TABLE)
        return None if row is None else decode_yg_order(row)

    async def create_yg_order_if_no_pending(self, order: YgOrder) -> YgOrder:
        async with self._yg_locks[order.test_id]:
            in_flight_query = self._apply_filters(
                self._client.table(YG_ORDER_TABLE).select(YG_ORDER_COLUMNS),
                yg_order_test_filters(order.test_id),
            )
            in_flight_query = in_flight_query.in_(
                YG_ORDER_STATUS_COLUMN, IN_FLIGHT_YG_STATUSES
            )
            response = await self._execute(
                in_flight_query.order(YG_ORDER_ORDER_COLUMN, desc=True).limit(1),
                operation="yg_tellimused.in_flight",
            )
            row = self._zero_or_one(response, YG_ORDER_TABLE)
            if row is not None:
                return decode_yg_order(row)
            inserted = await self._execute(
                self._client.table(YG_ORDER_TABLE)
                .insert(encode_yg_order(order))
                .select(YG_ORDER_COLUMNS),
                operation="yg_tellimused.insert",
            )
            return decode_yg_order(self._exactly_one(inserted, YG_ORDER_TABLE))

    async def commit_answer(
        self,
        expected_submission_id: SubmissionId,
        answer: AnswerRecord,
        transition: AnswerTransition,
    ) -> AnswerCommitResult:
        if answer.submission_id != expected_submission_id:
            raise RepositoryDataError(
                "answer submission ID must match the expected token"
            )
        self._validate_transition(expected_submission_id, answer, transition)

        inserted = True
        try:
            response = await self._execute(
                self._client.table(ANSWER_TABLE)
                .insert(encode_answer(answer))
                .select(ANSWER_COLUMNS),
                preserve_unique_violation=True,
                operation="tulemustepank.insert",
            )
            stored_answer = decode_answer(self._exactly_one(response, ANSWER_TABLE))
        except APIError as error:
            if error.code != _UNIQUE_VIOLATION:
                raise
            inserted = False
            stored_answer = await self._require_answer(answer.submission_id)
            if not self._same_answer_payload(stored_answer, answer):
                session = await self._require_session(answer.test_id)
                return AnswerCommitResult(
                    outcome=AnswerCommitOutcome.PAYLOAD_CONFLICT,
                    session=session,
                    answer=stored_answer,
                )

        if inserted:
            await self._increment_item_telemetry(answer)

        response = await self._execute(
            self._apply_filters(
                self._client.table(SESSION_TABLE)
                .update(answer_transition_updates(transition))
                .select(SESSION_COLUMNS),
                active_answer_session_filters(answer.test_id, expected_submission_id),
            ),
            operation="testisessioonid.commit_answer",
        )
        row = self._zero_or_one(response, SESSION_TABLE)
        if row is not None:
            return AnswerCommitResult(
                outcome=(
                    AnswerCommitOutcome.APPLIED
                    if inserted
                    else AnswerCommitOutcome.RECOVERED
                ),
                session=decode_session(row),
                answer=stored_answer,
            )

        session = await self._require_session(answer.test_id)
        state = session.player_state
        accepted = isinstance(state, PlayerState) and any(
            item.submission_id == expected_submission_id
            for item in state.answered_items
        )
        return AnswerCommitResult(
            outcome=(
                AnswerCommitOutcome.REPLAYED if accepted else AnswerCommitOutcome.STALE
            ),
            session=session,
            answer=stored_answer,
        )

    async def _increment_item_telemetry(self, answer: AnswerRecord) -> None:
        for _ in range(_TELEMETRY_RETRIES):
            item = await self.get_item(answer.item_id)
            if item is None:
                raise RepositoryDataError(f"unknown item: {answer.item_id}")
            used_at = answer.answered_at or datetime.now(UTC)
            filters = item_id_filters(answer.item_id)
            filters[ITEM_USAGE_COUNT_COLUMN] = item.usage_count
            response = await self._execute(
                self._apply_filters(
                    self._client.table(ITEM_TABLE)
                    .update(item_telemetry_updates(item.usage_count + 1, used_at))
                    .select(ITEM_COLUMNS),
                    filters,
                ),
                operation="ylesandepank.increment_telemetry",
            )
            if self._zero_or_one(response, ITEM_TABLE) is not None:
                return
        raise RepositoryUnavailable("item telemetry update remained contended")

    async def _require_answer(self, submission_id: SubmissionId) -> AnswerRecord:
        response = await self._execute(
            self._apply_filters(
                self._client.table(ANSWER_TABLE).select(ANSWER_COLUMNS),
                answer_id_filters(submission_id),
            ).limit(1),
            operation="tulemustepank.get",
        )
        row = self._zero_or_one(response, ANSWER_TABLE)
        if row is None:
            raise RepositoryUnavailable("conflicting answer could not be reloaded")
        return decode_answer(row)

    async def _require_session(self, test_id: TestId) -> AssessmentSession:
        session = await self.get_session(test_id)
        if session is None:
            raise RepositoryDataError(f"unknown session: {test_id}")
        return session

    async def _execute(
        self,
        query: _ExecutableQuery,
        *,
        preserve_unique_violation: bool = False,
        operation: str = "supabase.execute",
    ) -> APIResponse:
        started_at = perf_counter()
        try:
            response = await query.execute()
            emit_diagnostic(
                source="supabase",
                level="info",
                event_type="supabase_operation",
                payload={
                    "operation": operation,
                    "count": len(response.data),
                    "duration_ms": round((perf_counter() - started_at) * 1000, 3),
                },
            )
            return response
        except APIError as error:
            if preserve_unique_violation and error.code == _UNIQUE_VIOLATION:
                raise
            raise RepositoryUnavailable("Supabase request failed") from error
        except (httpx.HTTPError, TimeoutError) as error:
            raise RepositoryUnavailable("Supabase request failed") from error
        finally:
            record_supabase_execute(started_at)

    @staticmethod
    def _apply_filters[QueryT: _FilterQuery](
        query: QueryT, filters: Mapping[str, str | int | bool]
    ) -> QueryT:
        for column, value in filters.items():
            query = query.eq(column, value)
        return query

    @classmethod
    def _rows(cls, response: APIResponse, table: str) -> tuple[Row, ...]:
        raw_data = cast(object, response.data)
        if not isinstance(raw_data, Sequence) or isinstance(
            raw_data, (str, bytes, bytearray)
        ):
            raise RepositoryDataError(f"{table} response must be an array")
        data = cast(Sequence[object], raw_data)
        rows: list[Row] = []
        for value in data:
            if not isinstance(value, Mapping):
                raise RepositoryDataError(f"{table} response rows must be objects")
            rows.append(cast(Row, value))
        return tuple(rows)

    @classmethod
    def _zero_or_one(cls, response: APIResponse, table: str) -> Row | None:
        rows = cls._rows(response, table)
        if len(rows) > 1:
            raise RepositoryDataError(f"{table} query returned multiple rows")
        return rows[0] if rows else None

    @classmethod
    def _exactly_one(cls, response: APIResponse, table: str) -> Row:
        row = cls._zero_or_one(response, table)
        if row is None:
            raise RepositoryDataError(f"{table} write returned no row")
        return row

    @staticmethod
    def _same_answer_payload(left: AnswerRecord, right: AnswerRecord) -> bool:
        return (
            left.submission_id == right.submission_id
            and left.test_id == right.test_id
            and left.item_id == right.item_id
            and left.score == right.score
            and left.selected_answer == right.selected_answer
        )

    @staticmethod
    def _validate_transition(
        submission_id: SubmissionId,
        answer: AnswerRecord,
        transition: AnswerTransition,
    ) -> None:
        state = transition.next_player_state
        if state.schema_version != PLAYER_STATE_SCHEMA_VERSION:
            raise RepositoryDataError("answer transition must use schema version 2")
        if not state.answered_items:
            raise RepositoryDataError("answer transition must append an answered item")
        appended = state.answered_items[-1]
        if (
            appended.submission_id != submission_id
            or appended.item_id != answer.item_id
        ):
            raise RepositoryDataError(
                "answer transition does not contain the committed answer"
            )
        if transition.final_profile is not None and state.current_question is not None:
            raise RepositoryDataError(
                "a completed answer transition cannot have a current question"
            )
        answered_ids = tuple(item.item_id for item in state.answered_items)
        if len(answered_ids) != len(set(answered_ids)):
            raise RepositoryDataError("answer history contains duplicate item IDs")
        if (
            state.current_question is not None
            and state.current_question.item_id in set(answered_ids)
        ):
            raise RepositoryDataError("current item already appears in answer history")
