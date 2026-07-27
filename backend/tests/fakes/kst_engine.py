"""Deterministic asynchronous KST engine used by service tests."""

from collections import deque
from copy import deepcopy
from dataclasses import dataclass

from app.domain.models import (
    AdvanceResult,
    GraphDefinition,
    KnowledgeState,
    KstModel,
    ModelBuildResult,
    NodeParameters,
)
from app.integrations.kst_engine import KstEngine


@dataclass(frozen=True, slots=True)
class KstCall:
    method: str
    arguments: tuple[object, ...]


class FakeKstEngine:
    def __init__(
        self,
        *,
        model_results: tuple[ModelBuildResult, ...] = (),
        advance_results: tuple[AdvanceResult, ...] = (),
        ready: bool = True,
    ) -> None:
        self._model_results = deque(model_results)
        self._advance_results = deque(advance_results)
        self._ready = ready
        self._calls: list[KstCall] = []
        self._failures: dict[str, BaseException] = {}

    async def build_model(
        self,
        graph: GraphDefinition,
        node_parameters: tuple[NodeParameters, ...],
        cached_knowledge_states: tuple[KnowledgeState, ...] | None = None,
    ) -> ModelBuildResult:
        self._record("build_model", graph, node_parameters, cached_knowledge_states)
        self._raise_injected("build_model")
        try:
            return deepcopy(self._model_results.popleft())
        except IndexError as error:
            raise AssertionError("no fake model result configured") from error

    async def advance(
        self,
        model: KstModel,
        posterior: tuple[float, ...],
        question_node: str,
        response_correct: bool,
        response_count: int,
    ) -> AdvanceResult:
        self._record(
            "advance",
            model,
            posterior,
            question_node,
            response_correct,
            response_count,
        )
        self._raise_injected("advance")
        try:
            return deepcopy(self._advance_results.popleft())
        except IndexError as error:
            raise AssertionError("no fake advance result configured") from error

    async def is_ready(self) -> bool:
        self._record("is_ready")
        self._raise_injected("is_ready")
        return self._ready

    def fail_next(self, method: str, error: BaseException) -> None:
        self._failures[method] = error

    @property
    def calls(self) -> tuple[KstCall, ...]:
        return deepcopy(tuple(self._calls))

    def _record(self, method: str, *arguments: object) -> None:
        self._calls.append(KstCall(method=method, arguments=deepcopy(arguments)))

    def _raise_injected(self, method: str) -> None:
        error = self._failures.pop(method, None)
        if error is not None:
            raise error


_protocol_check: KstEngine = FakeKstEngine()
