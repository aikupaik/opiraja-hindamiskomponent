"""Asynchronous adapter for the candidate-aware internal R v2 service."""

import logging
from time import perf_counter
from typing import Never, Protocol

import httpx
from pydantic import TypeAdapter, ValidationError

from app.domain.models import *
from app.observability import record_r_request

from .r_dtos import *

logger = logging.getLogger(__name__)
_ADVANCE_RESPONSE: TypeAdapter[InProgressResponseDto | CompletedResponseDto] = (
    TypeAdapter(InProgressResponseDto | CompletedResponseDto)
)


class RUnavailable(RuntimeError):
    """The internal KST service was unavailable or violated its contract."""


class KstEngine(Protocol):
    async def build_model(
        self,
        graph: GraphDefinition,
        cached_knowledge_states: tuple[KnowledgeState, ...] | None = None,
    ) -> ModelBuildResult: ...

    async def select(
        self,
        model: KstModel,
        posterior: tuple[float, ...],
        candidates: tuple[ItemCandidate, ...],
    ) -> CandidateSelection: ...

    async def advance(
        self,
        model: KstModel,
        posterior: tuple[float, ...],
        administered: ItemCandidate,
        response_correct: bool,
        response_count: int,
        remaining_candidates: tuple[ItemCandidate, ...],
    ) -> AdvanceResult: ...

    async def is_ready(self) -> bool: ...


class HttpxKstEngine:
    """Typed adapter over one lifespan-managed shared HTTPX client."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def build_model(
        self,
        graph: GraphDefinition,
        cached_knowledge_states: tuple[KnowledgeState, ...] | None = None,
    ) -> ModelBuildResult:
        request = ModelRequestDto(
            nodes=graph.nodes,
            relations=tuple(
                RelationDto.model_validate(
                    {"from": relation.prerequisite, "to": relation.dependent}
                )
                for relation in graph.relations
            ),
            cached_knowledge_states=(
                None
                if cached_knowledge_states is None
                else tuple(state.nodes for state in cached_knowledge_states)
            ),
        )
        response = await self._request(
            "POST",
            "/internal/v2/kst/model",
            json=request.model_dump(mode="json", by_alias=True, exclude_none=True),
        )
        try:
            parsed = ModelResponseDto.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            self._malformed(error)
        return ModelBuildResult(
            model=_model_from_dto(parsed.model),
            posterior=parsed.posterior,
        )

    async def select(
        self,
        model: KstModel,
        posterior: tuple[float, ...],
        candidates: tuple[ItemCandidate, ...],
    ) -> CandidateSelection:
        request = SelectRequestDto(
            model=_model_to_dto(model),
            posterior=posterior,
            candidates=tuple(_candidate_to_dto(value) for value in candidates),
        )
        response = await self._request(
            "POST",
            "/internal/v2/kst/select",
            json=request.model_dump(mode="json"),
        )
        try:
            parsed = SelectedCandidateDto.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            self._malformed(error)
        return CandidateSelection(
            candidate_id=CandidateId(parsed.candidate_id),
            node=parsed.node,
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
        request = AdvanceRequestDto(
            model=_model_to_dto(model),
            posterior=posterior,
            administered=_candidate_to_dto(administered),
            response_correct=response_correct,
            response_count=response_count,
            remaining_candidates=tuple(
                _candidate_to_dto(value) for value in remaining_candidates
            ),
        )
        response = await self._request(
            "POST",
            "/internal/v2/kst/advance",
            json=request.model_dump(mode="json"),
        )
        try:
            parsed = _ADVANCE_RESPONSE.validate_python(response.json())
        except (ValueError, ValidationError) as error:
            self._malformed(error)
        if isinstance(parsed, InProgressResponseDto):
            return AdvanceInProgress(
                posterior=parsed.posterior,
                next_candidate=CandidateSelection(
                    candidate_id=CandidateId(parsed.next_candidate.candidate_id),
                    node=parsed.next_candidate.node,
                ),
            )
        return AdvanceCompleted(
            posterior=parsed.posterior,
            profile=_profile_from_dto(parsed.profile),
        )

    async def is_ready(self) -> bool:
        try:
            response = await self._request("GET", "/health")
            HealthResponseDto.model_validate(response.json())
        except RUnavailable:
            return False
        except (ValueError, ValidationError) as error:
            logger.warning(
                "r_health_contract_failure",
                extra={"diagnostic": type(error).__name__},
            )
            return False
        return True

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: object | None = None,
    ) -> httpx.Response:
        started_at = perf_counter()
        try:
            response = await self._client.request(method, path, json=json)
            response.raise_for_status()
            return response
        except httpx.HTTPStatusError as error:
            logger.warning(
                "r_request_failed",
                extra={
                    "diagnostic": type(error).__name__,
                    "dependency_status": error.response.status_code,
                },
            )
            raise RUnavailable("R service unavailable") from error
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            logger.warning(
                "r_request_failed",
                extra={"diagnostic": type(error).__name__},
            )
            raise RUnavailable("R service unavailable") from error
        finally:
            record_r_request(started_at)

    @staticmethod
    def _malformed(error: ValueError | ValidationError) -> Never:
        logger.warning(
            "r_response_contract_failure",
            extra={"diagnostic": type(error).__name__},
        )
        raise RUnavailable("R service unavailable") from error


def _candidate_to_dto(candidate: ItemCandidate) -> CandidateDto:
    return CandidateDto(
        candidate_id=str(candidate.candidate_id),
        node=candidate.node,
        beta=candidate.beta,
        eta=candidate.eta,
    )


def _model_to_dto(model: KstModel) -> KstModelDto:
    return KstModelDto(
        schema_version=2,
        method="kst",
        nodes=model.nodes,
        knowledge_states=tuple(state.nodes for state in model.knowledge_states),
        matrix=model.matrix,
        uniform_prior=model.uniform_prior,
        configuration=KstConfigurationDto(
            schema_version=1,
            stop_confidence=model.configuration.stop_confidence,
            feedback_credible_mass=model.configuration.feedback_credible_mass,
            reliability_floor=ReliabilityFloorDto(
                minimum=model.configuration.reliability_floor.minimum,
                multiplier=model.configuration.reliability_floor.multiplier,
                maximum=model.configuration.reliability_floor.maximum,
            ),
            safety_cap=SafetyCapDto(
                minimum_above_floor=(
                    model.configuration.safety_cap.responses_above_floor
                ),
                node_multiplier=model.configuration.safety_cap.node_multiplier,
            ),
        ),
        configuration_hash=model.configuration_hash,
        reliability_floor=model.derived_limits.reliability_floor,
        safety_cap=model.derived_limits.safety_cap,
    )


def _model_from_dto(model: KstModelDto) -> KstModel:
    return KstModel(
        schema_version=model.schema_version,
        method=AssessmentMethod(model.method),
        nodes=model.nodes,
        knowledge_states=tuple(
            KnowledgeState(nodes) for nodes in model.knowledge_states
        ),
        matrix=tuple(tuple(value for value in row) for row in model.matrix),
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


def _profile_from_dto(profile: FinalProfileDto) -> FinalProfile:
    return FinalProfile(
        mastered=profile.mastered,
        ready_to_learn=profile.ready_to_learn,
        uncertain_ahead=profile.uncertain_ahead,
        uncertain_prerequisite=profile.uncertain_prerequisite,
        not_yet=profile.not_yet,
        summary=profile.summary,
        stop_reason=StopReason(profile.stop_reason),
        best_state_confidence=profile.best_state_confidence,
        credible_mass=profile.credible_mass,
        credible_state_count=profile.credible_state_count,
    )
