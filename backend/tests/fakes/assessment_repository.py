"""Concurrency-safe in-memory implementation of the repository contract."""

import asyncio
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import UTC, datetime

from app.domain.models import (
    PLAYER_STATE_SCHEMA_VERSION,
    ActivationCommand,
    AnswerCommitOutcome,
    AnswerCommitResult,
    AnswerRecord,
    AnswerTransition,
    AnsweredItem,
    AssessmentItem,
    AssessmentSession,
    GraphCacheEntry,
    ItemId,
    is_domain_valid_usable_item,
    PlayerState,
    SessionStatus,
    SubmissionId,
    TestId,
    YgOrder,
    YgOrderId,
    YgStatus,
)
from app.domain.repository import AssessmentRepository, RepositoryDataError


@dataclass(frozen=True, slots=True)
class RepositoryCall:
    method: str
    arguments: tuple[object, ...]


class InMemoryAssessmentRepository:
    """A deterministic fake with the same state-transition rules as storage."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._graphs: dict[str, GraphCacheEntry] = {}
        self._sessions: dict[TestId, AssessmentSession] = {}
        self._items: dict[ItemId, AssessmentItem] = {}
        self._yg_orders: dict[TestId, list[YgOrder]] = {}
        self._answers: dict[SubmissionId, AnswerRecord] = {}
        self._calls: list[RepositoryCall] = []
        self._failures: dict[str, BaseException] = {}
        self._next_order_id = 1

    async def get_cached_graph(self, graph_hash: str) -> GraphCacheEntry | None:
        async with self._lock:
            self._record("get_cached_graph", graph_hash)
            self._raise_injected("get_cached_graph")
            entry = self._graphs.get(graph_hash)
            return deepcopy(entry)

    async def insert_cached_graph_if_absent(
        self, entry: GraphCacheEntry
    ) -> GraphCacheEntry:
        async with self._lock:
            self._record("insert_cached_graph_if_absent", entry)
            self._raise_injected("insert_cached_graph_if_absent")
            canonical = self._graphs.setdefault(entry.graph_hash, deepcopy(entry))
            return deepcopy(canonical)

    async def create_session(self, session: AssessmentSession) -> AssessmentSession:
        async with self._lock:
            self._record("create_session", session)
            self._raise_injected("create_session")
            if not isinstance(session.player_state, PlayerState):
                raise RepositoryDataError("new sessions cannot use legacy player state")
            if session.player_state.schema_version != PLAYER_STATE_SCHEMA_VERSION:
                raise RepositoryDataError(
                    "new sessions must use player state schema version 2"
                )
            self._validate_new_session(session)
            if session.test_id in self._sessions:
                raise RepositoryDataError(f"session already exists: {session.test_id}")
            self._sessions[session.test_id] = deepcopy(session)
            return deepcopy(session)

    async def get_session(self, test_id: TestId) -> AssessmentSession | None:
        async with self._lock:
            self._record("get_session", test_id)
            self._raise_injected("get_session")
            return deepcopy(self._sessions.get(test_id))

    async def activate_session(self, command: ActivationCommand) -> AssessmentSession:
        async with self._lock:
            self._record("activate_session", command)
            self._raise_injected("activate_session")
            session = self._require_session(command.test_id)
            if session.is_legacy:
                raise RepositoryDataError(
                    "legacy sessions cannot be activated or resumed"
                )
            if session.status is SessionStatus.ACTIVE:
                return deepcopy(session)
            if session.status is not SessionStatus.PREPARING:
                raise RepositoryDataError(
                    f"cannot activate session in status {session.status.value}"
                )
            state = session.player_state
            if not isinstance(state, PlayerState):
                raise RepositoryDataError("legacy sessions cannot be activated")
            expected_hash = (
                state.pending_graph.graph_hash
                if state.pending_graph is not None
                else session.graph_hash
            )
            if expected_hash is not None and expected_hash != command.graph_hash:
                raise RepositoryDataError(
                    "activation graph hash does not match the preparing session"
                )
            if (
                state.pending_graph is not None
                and state.pending_graph.nodes != command.model.nodes
            ):
                raise RepositoryDataError(
                    "activation model nodes do not match the pending graph"
                )
            active = replace(
                session,
                graph_hash=command.graph_hash,
                status=SessionStatus.ACTIVE,
                model=deepcopy(command.model),
                player_state=PlayerState.new(
                    posterior=command.model.uniform_prior,
                    current_question=deepcopy(command.first_question),
                    pending_graph=None,
                    session_pool=deepcopy(command.session_pool),
                ),
            )
            self._sessions[command.test_id] = active
            return deepcopy(active)

    async def mark_session_failed(self, test_id: TestId) -> AssessmentSession:
        async with self._lock:
            self._record("mark_session_failed", test_id)
            self._raise_injected("mark_session_failed")
            session = self._require_session(test_id)
            if session.status is SessionStatus.FAILED:
                return deepcopy(session)
            if session.status is not SessionStatus.PREPARING:
                raise RepositoryDataError(
                    f"cannot fail session in status {session.status.value}"
                )
            failed = replace(session, status=SessionStatus.FAILED)
            self._sessions[test_id] = failed
            return deepcopy(failed)

    async def update_preparing_inventory_plan(
        self, test_id: TestId, state: PlayerState
    ) -> AssessmentSession:
        async with self._lock:
            self._record("update_preparing_inventory_plan", test_id, state)
            self._raise_injected("update_preparing_inventory_plan")
            session = self._require_session(test_id)
            if session.status is not SessionStatus.PREPARING:
                return deepcopy(session)
            updated = replace(session, player_state=deepcopy(state))
            self._sessions[test_id] = updated
            return deepcopy(updated)

    async def is_ready(self) -> bool:
        async with self._lock:
            self._record("is_ready")
            self._raise_injected("is_ready")
            return True

    async def list_usable_items_for_nodes(
        self, nodes: tuple[str, ...]
    ) -> tuple[AssessmentItem, ...]:
        async with self._lock:
            self._record("list_usable_items_for_nodes", nodes)
            self._raise_injected("list_usable_items_for_nodes")
            return deepcopy(tuple(
                item
                for node in nodes
                for item in sorted(
                    (
                        value
                        for value in self._items.values()
                        if value.node == node
                        and is_domain_valid_usable_item(value)
                    ),
                    key=lambda value: int(value.item_id),
                )
            ))

    async def load_items_by_ids(
        self, item_ids: tuple[ItemId, ...]
    ) -> tuple[AssessmentItem, ...]:
        async with self._lock:
            self._record("load_items_by_ids", item_ids)
            self._raise_injected("load_items_by_ids")
            if len(item_ids) != len(set(item_ids)):
                raise RepositoryDataError("pool item IDs must be unique")
            return deepcopy(tuple(
                item
                for item_id in item_ids
                if (item := self._items.get(item_id)) is not None
                and is_domain_valid_usable_item(item)
            ))

    async def get_item(self, item_id: ItemId) -> AssessmentItem | None:
        async with self._lock:
            self._record("get_item", item_id)
            self._raise_injected("get_item")
            return deepcopy(self._items.get(item_id))

    async def get_latest_yg_order(self, test_id: TestId) -> YgOrder | None:
        async with self._lock:
            self._record("get_latest_yg_order", test_id)
            self._raise_injected("get_latest_yg_order")
            orders = self._yg_orders.get(test_id, ())
            return deepcopy(orders[-1]) if orders else None

    async def create_yg_order_if_no_pending(self, order: YgOrder) -> YgOrder:
        async with self._lock:
            self._record("create_yg_order_if_no_pending", order)
            self._raise_injected("create_yg_order_if_no_pending")
            orders = self._yg_orders.setdefault(order.test_id, [])
            pending = next(
                (
                    existing
                    for existing in reversed(orders)
                    if existing.status in (YgStatus.PENDING, YgStatus.PROCESSING)
                ),
                None,
            )
            if pending is not None:
                return deepcopy(pending)
            stored = replace(
                order,
                order_id=(
                    order.order_id
                    if order.order_id is not None
                    else YgOrderId(self._next_order_id)
                ),
            )
            stored_order_id = stored.order_id
            if stored_order_id is None:
                raise AssertionError("stored YG order must have an ID")
            self._next_order_id = max(self._next_order_id, int(stored_order_id) + 1)
            orders.append(deepcopy(stored))
            return deepcopy(stored)

    async def commit_answer(
        self,
        expected_submission_id: SubmissionId,
        answer: AnswerRecord,
        transition: AnswerTransition,
    ) -> AnswerCommitResult:
        async with self._lock:
            self._record("commit_answer", expected_submission_id, answer, transition)
            self._raise_injected("commit_answer")
            if answer.submission_id != expected_submission_id:
                raise RepositoryDataError(
                    "answer submission ID must match the expected token"
                )
            session = self._require_session(answer.test_id)
            if not isinstance(session.player_state, PlayerState):
                raise RepositoryDataError("legacy sessions cannot commit answers")
            if session.status not in (
                SessionStatus.ACTIVE,
                SessionStatus.COMPLETED,
            ):
                raise RepositoryDataError(
                    f"cannot commit an answer in status {session.status.value}"
                )
            item = self._items.get(answer.item_id)
            if item is None:
                raise RepositoryDataError(f"unknown item: {answer.item_id}")

            existing = self._answers.get(answer.submission_id)
            if existing is not None and not _same_answer_payload(existing, answer):
                return AnswerCommitResult(
                    outcome=AnswerCommitOutcome.PAYLOAD_CONFLICT,
                    session=deepcopy(session),
                    answer=deepcopy(existing),
                )

            inserted = existing is None
            if inserted:
                stored_answer = deepcopy(answer)
                self._answers[answer.submission_id] = stored_answer
                used_at = answer.answered_at or datetime.now(UTC)
                self._items[item.item_id] = replace(
                    item,
                    usage_count=item.usage_count + 1,
                    last_used_at=used_at,
                )
            else:
                stored_answer = existing

            current = session.player_state.current_question
            if current is not None and current.submission_id == expected_submission_id:
                self._validate_transition(
                    session, expected_submission_id, answer, transition
                )
                advanced = replace(
                    session,
                    player_state=deepcopy(transition.next_player_state),
                    final_profile=deepcopy(transition.final_profile),
                    status=(
                        SessionStatus.COMPLETED
                        if transition.final_profile is not None
                        else SessionStatus.ACTIVE
                    ),
                )
                self._sessions[answer.test_id] = advanced
                return AnswerCommitResult(
                    outcome=(
                        AnswerCommitOutcome.APPLIED
                        if inserted
                        else AnswerCommitOutcome.RECOVERED
                    ),
                    session=deepcopy(advanced),
                    answer=deepcopy(stored_answer),
                )

            accepted = any(
                answered.submission_id == expected_submission_id
                for answered in session.player_state.answered_items
            )
            return AnswerCommitResult(
                outcome=(
                    AnswerCommitOutcome.REPLAYED
                    if accepted
                    else AnswerCommitOutcome.STALE
                ),
                session=deepcopy(session),
                answer=deepcopy(stored_answer),
            )

    async def seed_graph(self, entry: GraphCacheEntry) -> None:
        async with self._lock:
            self._graphs[entry.graph_hash] = deepcopy(entry)

    async def seed_session(self, session: AssessmentSession) -> None:
        async with self._lock:
            self._sessions[session.test_id] = deepcopy(session)

    async def seed_items(self, *items: AssessmentItem) -> None:
        async with self._lock:
            for item in items:
                self._items[item.item_id] = deepcopy(item)

    async def seed_yg_order(self, order: YgOrder) -> None:
        async with self._lock:
            self._yg_orders.setdefault(order.test_id, []).append(deepcopy(order))

    async def set_latest_yg_status(
        self, test_id: TestId, status: YgStatus
    ) -> None:
        async with self._lock:
            orders = self._yg_orders.get(test_id)
            if not orders:
                raise AssertionError("no YG order to update")
            orders[-1] = replace(orders[-1], status=status)

    async def seed_answer(self, answer: AnswerRecord) -> None:
        """Seed an answer insert without its session transition for recovery tests."""

        async with self._lock:
            self._answers[answer.submission_id] = deepcopy(answer)

    def fail_next(self, method: str, error: BaseException | None = None) -> None:
        self._failures[method] = error or RuntimeError(
            f"injected repository failure: {method}"
        )

    @property
    def graph_snapshot(self) -> dict[str, GraphCacheEntry]:
        return deepcopy(self._graphs)

    @property
    def session_snapshot(self) -> dict[TestId, AssessmentSession]:
        return deepcopy(self._sessions)

    @property
    def item_snapshot(self) -> dict[ItemId, AssessmentItem]:
        return deepcopy(self._items)

    @property
    def yg_order_snapshot(self) -> dict[TestId, tuple[YgOrder, ...]]:
        return {
            test_id: deepcopy(tuple(orders))
            for test_id, orders in self._yg_orders.items()
        }

    @property
    def answer_snapshot(self) -> dict[SubmissionId, AnswerRecord]:
        return deepcopy(self._answers)

    @property
    def calls(self) -> tuple[RepositoryCall, ...]:
        return deepcopy(tuple(self._calls))

    def _record(self, method: str, *arguments: object) -> None:
        self._calls.append(RepositoryCall(method=method, arguments=deepcopy(arguments)))

    def _raise_injected(self, method: str) -> None:
        error = self._failures.pop(method, None)
        if error is not None:
            raise error

    def _require_session(self, test_id: TestId) -> AssessmentSession:
        try:
            return self._sessions[test_id]
        except KeyError as error:
            raise RepositoryDataError(f"unknown session: {test_id}") from error

    @staticmethod
    def _validate_new_session(session: AssessmentSession) -> None:
        state = session.player_state
        if not isinstance(state, PlayerState):
            raise RepositoryDataError("new sessions cannot use legacy player state")
        if session.status is SessionStatus.PREPARING:
            if state.current_question is not None:
                raise RepositoryDataError(
                    "preparing sessions cannot contain a current question"
                )
            if session.graph_hash is None and state.pending_graph is None:
                raise RepositoryDataError(
                    "preparing sessions require a graph"
                )
        if session.status in (SessionStatus.ACTIVE, SessionStatus.COMPLETED):
            if (
                session.graph_hash is None
                or session.model is None
                or not state.posterior
                or state.pending_graph is not None
            ):
                raise RepositoryDataError(
                    "active and completed sessions require graph, model, "
                    "posterior, and no pending graph"
                )

    @staticmethod
    def _validate_transition(
        session: AssessmentSession,
        submission_id: SubmissionId,
        answer: AnswerRecord,
        transition: AnswerTransition,
    ) -> None:
        next_state = transition.next_player_state
        if next_state.schema_version != PLAYER_STATE_SCHEMA_VERSION:
            raise RepositoryDataError("answer transition must use schema version 2")
        if not isinstance(session.player_state, PlayerState):
            raise RepositoryDataError("legacy sessions cannot transition")
        previous_count = len(session.player_state.answered_items)
        if len(next_state.answered_items) != previous_count + 1:
            raise RepositoryDataError(
                "answer transition must append exactly one answered item"
            )
        if (
            next_state.answered_items[:previous_count]
            != session.player_state.answered_items
        ):
            raise RepositoryDataError("answer transition changed answer history")
        appended: AnsweredItem = next_state.answered_items[-1]
        if (
            appended.submission_id != submission_id
            or appended.item_id != answer.item_id
        ):
            raise RepositoryDataError(
                "answer transition does not contain the committed answer"
            )
        if (
            transition.final_profile is not None
            and next_state.current_question is not None
        ):
            raise RepositoryDataError(
                "a completed answer transition cannot have a current question"
            )
        answered_ids = tuple(item.item_id for item in next_state.answered_items)
        if len(answered_ids) != len(set(answered_ids)):
            raise RepositoryDataError("answer history contains duplicate item IDs")
        if (
            next_state.current_question is not None
            and next_state.current_question.item_id in set(answered_ids)
        ):
            raise RepositoryDataError("current item already appears in answer history")


def _same_answer_payload(left: AnswerRecord, right: AnswerRecord) -> bool:
    return (
        left.submission_id == right.submission_id
        and left.test_id == right.test_id
        and left.item_id == right.item_id
        and left.score == right.score
        and left.selected_answer == right.selected_answer
    )


_protocol_check: AssessmentRepository = InMemoryAssessmentRepository()
