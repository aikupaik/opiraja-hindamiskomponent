"""Stateless deterministic KST engine for API-only load tests."""

from collections import Counter
from copy import deepcopy

from app.domain.models import (
    AdvanceCompleted,
    AdvanceInProgress,
    AdvanceResult,
    CandidateSelection,
    FinalProfile,
    GraphDefinition,
    ItemCandidate,
    KnowledgeState,
    KstConfiguration,
    KstModel,
    ModelBuildResult,
    StopReason,
)
from app.integrations.kst_engine import KstEngine

from .fixtures import ApiFixture, FixtureShape


class DeterministicKstEngine:
    def __init__(self, fixtures: dict[FixtureShape, ApiFixture]) -> None:
        self._fixtures = fixtures
        self._by_graph = {
            _graph_key(fixture.graph): fixture for fixture in fixtures.values()
        }
        self._call_counts: Counter[str] = Counter()

    async def build_model(
        self,
        graph: GraphDefinition,
        cached_knowledge_states: tuple[KnowledgeState, ...] | None = None,
        configuration: KstConfiguration | None = None,
    ) -> ModelBuildResult:
        self._call_counts["build_model"] += 1
        fixture = self._fixture(graph)
        result = fixture.model_result
        if cached_knowledge_states is not None and (
            cached_knowledge_states != result.model.knowledge_states
        ):
            raise ValueError("cached fixture knowledge states do not match the graph")
        if configuration is not None and configuration != result.model.configuration:
            raise ValueError("performance fixture configuration does not match")
        return deepcopy(result)

    async def select(
        self,
        model: KstModel,
        posterior: tuple[float, ...],
        candidates: tuple[ItemCandidate, ...],
    ) -> CandidateSelection:
        self._call_counts["select"] += 1
        if len(posterior) != len(model.knowledge_states):
            raise ValueError("posterior length does not match the fixture model")
        if not candidates:
            raise ValueError("performance fixture selection requires candidates")
        selected = candidates[0]
        return CandidateSelection(
            candidate_id=selected.candidate_id,
            node=selected.node,
        )

    async def advance(
        self,
        model: KstModel,
        posterior: tuple[float, ...],
        administered: ItemCandidate,
        response_correct: bool,
        response_count: int,
        remaining_candidates: tuple[ItemCandidate, ...],
    ) -> AdvanceResult:
        self._call_counts["advance"] += 1
        del administered, response_correct
        if response_count >= model.derived_limits.reliability_floor:
            mastered_count = max(1, len(model.nodes) // 2)
            return AdvanceCompleted(
                posterior=posterior,
                profile=FinalProfile(
                    mastered=model.nodes[:mastered_count],
                    ready_to_learn=model.nodes[mastered_count : mastered_count + 1],
                    uncertain_ahead=(),
                    uncertain_prerequisite=(),
                    not_yet=model.nodes[mastered_count + 1 :],
                    summary=None,
                    stop_reason=StopReason.NATURAL,
                    best_state_confidence=max(posterior),
                    credible_mass=1.0,
                    credible_state_count=len(posterior),
                ),
            )
        if not remaining_candidates:
            raise ValueError("performance fixture exhausted before reliability floor")
        selected = remaining_candidates[0]
        return AdvanceInProgress(
            posterior=posterior,
            next_candidate=CandidateSelection(
                candidate_id=selected.candidate_id,
                node=selected.node,
            ),
        )

    async def is_ready(self) -> bool:
        self._call_counts["is_ready"] += 1
        return True

    @property
    def call_counts(self) -> dict[str, int]:
        return dict(self._call_counts)

    def _fixture(self, graph: GraphDefinition) -> ApiFixture:
        try:
            return self._by_graph[_graph_key(graph)]
        except KeyError as error:
            raise ValueError("graph is not an API-only performance fixture") from error


def _graph_key(
    graph: GraphDefinition,
) -> tuple[tuple[str, ...], tuple[tuple[str, str], ...]]:
    return (
        graph.nodes,
        tuple(
            (relation.prerequisite, relation.dependent)
            for relation in graph.relations
        ),
    )


_protocol_check: KstEngine = DeterministicKstEngine({})

