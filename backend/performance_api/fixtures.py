"""Load committed R fixtures into deterministic API-only domain inputs."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import (
    AssessmentItem,
    AssessmentMethod,
    DerivedLimits,
    GraphDefinition,
    GraphRelation,
    ItemId,
    KnowledgeState,
    KstConfiguration,
    KstModel,
    ModelBuildResult,
    ReliabilityFloorConfiguration,
    SafetyCapConfiguration,
)
from app.integrations.r_dtos import ModelResponseDto

FixtureShape = Literal["3-chain", "10-chain", "10-independent"]
FIXTURE_SHAPES: tuple[FixtureShape, ...] = (
    "3-chain",
    "10-chain",
    "10-independent",
)


class _FixtureModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class _Relation(_FixtureModel):
    prerequisite: str = Field(alias="from")
    dependent: str = Field(alias="to")


class _Graph(_FixtureModel):
    nodes: tuple[str, ...]
    relations: tuple[_Relation, ...]


class _ModelOperation(_FixtureModel):
    expected_response: ModelResponseDto


class _Operations(_FixtureModel):
    model: _ModelOperation


class _FixtureFile(_FixtureModel):
    shape: FixtureShape
    candidates_per_node: int = Field(ge=3)
    graph: _Graph
    operations: _Operations


@dataclass(frozen=True, slots=True)
class ApiFixture:
    shape: FixtureShape
    graph: GraphDefinition
    model_result: ModelBuildResult
    candidates_per_node: int

    @property
    def answer_count(self) -> int:
        return self.model_result.model.derived_limits.reliability_floor


def fixture_directory() -> Path:
    configured = os.environ.get("PERF_API_FIXTURE_DIR")
    if configured:
        return Path(configured)
    container_path = Path("/performance/fixtures/r")
    if container_path.is_dir():
        return container_path
    return Path(__file__).resolve().parents[2] / "performance" / "fixtures" / "r"


def load_fixtures(directory: Path | None = None) -> dict[FixtureShape, ApiFixture]:
    root = directory or fixture_directory()
    fixtures: dict[FixtureShape, ApiFixture] = {}
    for shape in FIXTURE_SHAPES:
        parsed = _FixtureFile.model_validate_json(
            (root / f"{shape}.json").read_text(encoding="utf-8")
        )
        if parsed.shape != shape:
            raise ValueError(f"fixture shape mismatch in {shape}.json")
        model_response = parsed.operations.model.expected_response
        model = _model_from_response(model_response)
        graph = GraphDefinition(
            nodes=parsed.graph.nodes,
            relations=tuple(
                GraphRelation(value.prerequisite, value.dependent)
                for value in parsed.graph.relations
            ),
        )
        if graph.nodes != model.nodes:
            raise ValueError(f"fixture model nodes do not match graph for {shape}")
        fixtures[shape] = ApiFixture(
            shape=shape,
            graph=graph,
            model_result=ModelBuildResult(
                model=model,
                posterior=model_response.posterior,
            ),
            candidates_per_node=parsed.candidates_per_node,
        )
    return fixtures


def build_item_bank(fixtures: dict[FixtureShape, ApiFixture]) -> tuple[AssessmentItem, ...]:
    nodes = sorted({node for fixture in fixtures.values() for node in fixture.graph.nodes})
    items: list[AssessmentItem] = []
    for node_index, node in enumerate(nodes, start=1):
        for item_index in range(1, 4):
            item_id = ItemId(node_index * 100 + item_index)
            items.append(
                AssessmentItem(
                    item_id=item_id,
                    node=node,
                    instruction="Choose one answer.",
                    prompt=f"Performance fixture {node} item {item_index}",
                    stimulus=None,
                    answer_key="Correct",
                    distractors=("Incorrect A", "Incorrect B", "Incorrect C"),
                    beta=0.05,
                    eta=0.25,
                )
            )
    return tuple(items)


def _model_from_response(response: ModelResponseDto) -> KstModel:
    model = response.model
    return KstModel(
        schema_version=model.schema_version,
        method=AssessmentMethod(model.method),
        nodes=model.nodes,
        knowledge_states=tuple(
            KnowledgeState(nodes=value) for value in model.knowledge_states
        ),
        matrix=model.matrix,
        uniform_prior=model.uniform_prior,
        configuration=KstConfiguration(
            schema_version=model.configuration.schema_version,
            stop_confidence=model.configuration.stop_confidence,
            feedback_credible_mass=model.configuration.feedback_credible_mass,
            reliability_floor=ReliabilityFloorConfiguration(
                minimum=model.configuration.reliability_floor.minimum,
                multiplier=model.configuration.reliability_floor.multiplier,
                maximum=model.configuration.reliability_floor.maximum,
            ),
            safety_cap=SafetyCapConfiguration(
                node_multiplier=model.configuration.safety_cap.node_multiplier,
                responses_above_floor=(
                    model.configuration.safety_cap.minimum_above_floor
                ),
            ),
        ),
        configuration_hash=model.configuration_hash,
        derived_limits=DerivedLimits(
            reliability_floor=model.reliability_floor,
            safety_cap=model.safety_cap,
        ),
    )

