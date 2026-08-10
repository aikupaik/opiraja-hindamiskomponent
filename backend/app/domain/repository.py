"""The asynchronous, domain-focused assessment persistence contract."""

from typing import Protocol

from .models import *


class RepositoryDataError(ValueError):
    """Persisted data cannot be represented by the supported domain schema."""


class RepositoryUnavailable(RuntimeError):
    """The persistence service could not complete a request."""


class AssessmentRepository(Protocol):
    async def get_cached_graph(self, graph_hash: str) -> GraphCacheEntry | None: ...

    async def insert_cached_graph_if_absent(
        self, entry: GraphCacheEntry
    ) -> GraphCacheEntry:
        """Insert an entry or return the canonical entry already stored."""
        ...

    async def create_session(self, session: AssessmentSession) -> AssessmentSession: ...

    async def get_session(self, test_id: TestId) -> AssessmentSession | None: ...

    async def activate_session(self, command: ActivationCommand) -> AssessmentSession:
        """Idempotently activate a non-legacy preparing session."""
        ...

    async def update_preparing_inventory_plan(
        self, test_id: TestId, state: PlayerState
    ) -> AssessmentSession:
        """Persist a recalculated v2 plan while the session remains preparing."""
        ...

    async def mark_session_failed(self, test_id: TestId) -> AssessmentSession: ...

    async def is_ready(self) -> bool:
        """Perform the lightweight storage readiness check used by Step 4."""
        ...

    async def list_usable_items_for_nodes(
        self, nodes: tuple[str, ...]
    ) -> tuple[AssessmentItem, ...]:
        """Return every domain-valid usable item in node then item-ID order."""
        ...

    async def load_items_by_ids(
        self, item_ids: tuple[ItemId, ...]
    ) -> tuple[AssessmentItem, ...]:
        """Load exact usable pool members in the caller's order."""
        ...

    async def get_item(self, item_id: ItemId) -> AssessmentItem | None: ...

    async def list_answers_for_test(
        self, test_id: TestId
    ) -> tuple[AnswerRecord, ...]: ...

    async def get_latest_yg_order(self, test_id: TestId) -> YgOrder | None: ...

    async def create_yg_order_if_no_pending(self, order: YgOrder) -> YgOrder: ...

    async def commit_answer(
        self,
        expected_submission_id: SubmissionId,
        answer: AnswerRecord,
        transition: AnswerTransition,
    ) -> AnswerCommitResult:
        """Commit an answer using sequential, idempotent semantics.

        Implementations must insert ``answer`` with its explicit submission ID,
        increment item telemetry only for a new insert, and then compare-and-set
        the session against ``expected_submission_id``. Identical interrupted
        writes are recovered without another telemetry increment. Accepted
        retries are replayed; never-accepted stale tokens and conflicting
        submission payloads are reported distinctly.
        """
        ...
