"""Pure mapping between Supabase rows and the English domain.

All deployed Estonian table, column, and status vocabulary is confined to this
module. The functions neither import nor call a Supabase client.
"""

from collections.abc import Mapping, Sequence
from datetime import datetime
import math
from typing import TypeAlias, cast
from uuid import UUID

from app.domain.models import *
from app.domain.repository import RepositoryDataError

JsonScalar: TypeAlias = None | bool | int | float | str
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
Row: TypeAlias = Mapping[str, object]
EncodedRow: TypeAlias = dict[str, JsonValue]
FilterValue: TypeAlias = str | int | bool
Filters: TypeAlias = dict[str, FilterValue]

GRAPH_TABLE = "graafid_kst"
SESSION_TABLE = "testisessioonid"
ITEM_TABLE = "ylesandepank"
ANSWER_TABLE = "tulemustepank"
YG_ORDER_TABLE = "yg_tellimused"

GRAPH_COLUMNS = "graaf_hash,graafi_struktuur,teadmusruum_maatriks,loodud"
SESSION_COLUMNS = (
    "test_id,kasutaja_id,rada_id,graaf_hash,staatus,alustatud,"
    "lopp_profiil,testi_loogika,metoodika,tp_seisund,eesmark"
)
ITEM_COLUMNS = (
    "yp_id,graafi_objekt,juhis,tyvi,stiimul,voti,distraktor_1,"
    "distraktor_2,distraktor_3,beeta_error,g_guess,staatus,"
    "kasutamiste_arv,viimane_kasutus"
)
ANSWER_COLUMNS = "vastus_id,test_id,yp_id,skoor,valitud_vastus,vastatud_ajal"
YG_ORDER_COLUMNS = (
    "id,test_id,kursus,graafi_objektid,kognitiivne_tase,maht,staatus,loodud,"
    "ylesande_taotlused,taitmise_tulemus"
)

# Query/update vocabulary used by the concrete adapter. Keeping these names
# here prevents database-language details from leaking into repository logic.
GRAPH_HASH_COLUMN = "graaf_hash"
SESSION_ID_COLUMN = "test_id"
SESSION_STATUS_COLUMN = "staatus"
SESSION_MODEL_COLUMN = "testi_loogika"
SESSION_PLAYER_STATE_COLUMN = "tp_seisund"
SESSION_FINAL_PROFILE_COLUMN = "lopp_profiil"
ITEM_ID_COLUMN = "yp_id"
ITEM_NODE_COLUMN = "graafi_objekt"
ITEM_STATUS_COLUMN = "staatus"
ITEM_USAGE_COUNT_COLUMN = "kasutamiste_arv"
ITEM_LAST_USED_COLUMN = "viimane_kasutus"
ANSWER_ID_COLUMN = "vastus_id"
ANSWER_TEST_ID_COLUMN = "test_id"
CURRENT_SUBMISSION_PATH = "tp_seisund->current_question->>submission_id"
YG_ORDER_ID_COLUMN = "id"
YG_ORDER_STATUS_COLUMN = "staatus"
GRAPH_CONFLICT_COLUMN = GRAPH_HASH_COLUMN
ITEM_ORDER_COLUMN = ITEM_ID_COLUMN
YG_ORDER_ORDER_COLUMN = YG_ORDER_ID_COLUMN

_SESSION_TO_DB = {
    SessionStatus.PREPARING: "planeerimisel",
    SessionStatus.ACTIVE: "aktiivne",
    SessionStatus.COMPLETED: "lõpetatud",
    SessionStatus.FAILED: "katkenud",
}
_SESSION_FROM_DB = {value: key for key, value in _SESSION_TO_DB.items()}
_YG_TO_DB = {
    YgStatus.PENDING: "ootel",
    YgStatus.PROCESSING: "tootmises",
    YgStatus.COMPLETED: "tehtud",
    YgStatus.FAILED: "viga",
}
_YG_FROM_DB = {value: key for key, value in _YG_TO_DB.items()}
IN_FLIGHT_YG_STATUSES = (
    _YG_TO_DB[YgStatus.PENDING],
    _YG_TO_DB[YgStatus.PROCESSING],
)
_ITEM_TO_DB = {
    ItemStatus.DRAFT: "kavand",
    ItemStatus.USABLE: "kasutatav",
    ItemStatus.REVIEW: "läbi vaatamisel",
    ItemStatus.ARCHIVED: "arhiivis",
}
_ITEM_FROM_DB = {value: key for key, value in _ITEM_TO_DB.items()}
USABLE_ITEM_STATUS = _ITEM_TO_DB[ItemStatus.USABLE]
_STOP_TO_DB = {
    StopReason.NATURAL: "loomulik",
    StopReason.SAFETY_CAP: "turvapiir",
    StopReason.ITEM_INVENTORY_EXHAUSTED: "ülesandevaru_ammendunud",
}
_STOP_FROM_DB = {value: key for key, value in _STOP_TO_DB.items()}


def item_eligibility_filters(node: str) -> Filters:
    """Filters for usable items; course is deliberately not part of identity."""

    return {"graafi_objekt": node, "staatus": _ITEM_TO_DB[ItemStatus.USABLE]}


def graph_hash_filters(graph_hash: str) -> Filters:
    return {GRAPH_HASH_COLUMN: graph_hash}


def session_id_filters(test_id: TestId) -> Filters:
    return {SESSION_ID_COLUMN: str(test_id)}


def preparing_session_filters(test_id: TestId) -> Filters:
    return {
        SESSION_ID_COLUMN: str(test_id),
        SESSION_STATUS_COLUMN: _SESSION_TO_DB[SessionStatus.PREPARING],
    }


def answer_id_filters(submission_id: SubmissionId) -> Filters:
    return {ANSWER_ID_COLUMN: str(submission_id)}


def answer_test_filters(test_id: TestId) -> Filters:
    return {ANSWER_TEST_ID_COLUMN: str(test_id)}


def item_id_filters(item_id: ItemId) -> Filters:
    return {ITEM_ID_COLUMN: int(item_id)}


def yg_order_test_filters(test_id: TestId) -> Filters:
    return {SESSION_ID_COLUMN: str(test_id)}


def pending_yg_order_filters(test_id: TestId) -> Filters:
    return {"test_id": str(test_id), "staatus": _YG_TO_DB[YgStatus.PENDING]}


def active_answer_session_filters(
    test_id: TestId, submission_id: SubmissionId
) -> Filters:
    return {
        SESSION_ID_COLUMN: str(test_id),
        SESSION_STATUS_COLUMN: _SESSION_TO_DB[SessionStatus.ACTIVE],
        CURRENT_SUBMISSION_PATH: str(submission_id),
    }


def activation_updates(command: ActivationCommand) -> EncodedRow:
    """Atomic preparing-to-active update values for the concrete adapter."""

    return {
        GRAPH_HASH_COLUMN: command.graph_hash,
        SESSION_STATUS_COLUMN: _SESSION_TO_DB[SessionStatus.ACTIVE],
        SESSION_MODEL_COLUMN: encode_kst_model(command.model),
        SESSION_PLAYER_STATE_COLUMN: encode_player_state(
            PlayerState.new(
                posterior=command.model.uniform_prior,
                current_question=command.first_question,
                session_pool=command.session_pool,
            )
        ),
    }


def failed_session_updates() -> EncodedRow:
    return {SESSION_STATUS_COLUMN: _SESSION_TO_DB[SessionStatus.FAILED]}


def preparing_inventory_updates(state: PlayerState) -> EncodedRow:
    if state.current_question is not None or state.session_pool is not None:
        raise RepositoryDataError("preparing inventory state cannot be active")
    return {SESSION_PLAYER_STATE_COLUMN: encode_player_state(state)}


def answer_transition_updates(transition: AnswerTransition) -> EncodedRow:
    completed = transition.final_profile is not None
    return {
        SESSION_STATUS_COLUMN: _SESSION_TO_DB[
            SessionStatus.COMPLETED if completed else SessionStatus.ACTIVE
        ],
        SESSION_PLAYER_STATE_COLUMN: encode_player_state(
            transition.next_player_state
        ),
        SESSION_FINAL_PROFILE_COLUMN: (
            None
            if transition.final_profile is None
            else encode_final_profile(transition.final_profile)
        ),
    }


def item_telemetry_updates(usage_count: int, used_at: datetime) -> EncodedRow:
    return {
        ITEM_USAGE_COUNT_COLUMN: usage_count,
        ITEM_LAST_USED_COLUMN: _encode_datetime(used_at),
    }


def encode_graph_entry(entry: GraphCacheEntry) -> EncodedRow:
    return {
        "graaf_hash": entry.graph_hash,
        "graafi_struktuur": {
            "solmed": list(entry.graph.nodes),
            "seosed": [
                {"eeltingimus": relation.prerequisite, "sõltuv": relation.dependent}
                for relation in entry.graph.relations
            ],
        },
        "teadmusruum_maatriks": [list(state.nodes) for state in entry.knowledge_states],
    }


def decode_graph_entry(row: Row) -> GraphCacheEntry:
    graph_data = _mapping(row, "graafi_struktuur")
    relations_data = _sequence(graph_data, "seosed")
    return GraphCacheEntry(
        graph_hash=_string(row, "graaf_hash"),
        graph=GraphDefinition(
            nodes=_string_tuple(_sequence(graph_data, "solmed"), "solmed"),
            relations=tuple(
                GraphRelation(
                    prerequisite=_string(_as_mapping(value, "seos"), "eeltingimus"),
                    dependent=_string(_as_mapping(value, "seos"), "sõltuv"),
                )
                for value in relations_data
            ),
        ),
        knowledge_states=tuple(
            KnowledgeState(
                _string_tuple(_as_sequence(value, "teadmusseisund"), "teadmusseisund")
            )
            for value in _sequence(row, "teadmusruum_maatriks")
        ),
        created_at=_optional_datetime(row, "loodud"),
    )


def encode_item(item: AssessmentItem) -> EncodedRow:
    distractors = (*item.distractors, None, None, None)
    return {
        "yp_id": int(item.item_id),
        "graafi_objekt": item.node,
        "juhis": item.instruction,
        "tyvi": item.prompt,
        "stiimul": item.stimulus,
        "voti": item.answer_key,
        "distraktor_1": distractors[0],
        "distraktor_2": distractors[1],
        "distraktor_3": distractors[2],
        "beeta_error": item.beta,
        "g_guess": item.eta,
        "staatus": _ITEM_TO_DB[item.status],
        "kasutamiste_arv": item.usage_count,
        "viimane_kasutus": _encode_datetime(item.last_used_at),
    }


def decode_item(row: Row) -> AssessmentItem:
    distractors = tuple(
        value
        for key in ("distraktor_1", "distraktor_2", "distraktor_3")
        if (value := _optional_string(row, key)) is not None
    )
    return AssessmentItem(
        item_id=ItemId(_integer(row, "yp_id")),
        node=_nonblank_string(row, "graafi_objekt"),
        instruction=_nonblank_string(row, "juhis"),
        prompt=_nonblank_string(row, "tyvi"),
        stimulus=_optional_string(row, "stiimul"),
        answer_key=_nonblank_string(row, "voti"),
        distractors=distractors,
        beta=_probability(row, "beeta_error"),
        eta=_probability(row, "g_guess"),
        status=_enum_value(_ITEM_FROM_DB, row, "staatus"),
        usage_count=_integer(row, "kasutamiste_arv"),
        last_used_at=_optional_datetime(row, "viimane_kasutus"),
    )


def encode_answer(answer: AnswerRecord) -> EncodedRow:
    """Encode an insert and always write the caller's UUID explicitly."""

    return {
        "vastus_id": str(answer.submission_id),
        "test_id": str(answer.test_id),
        "yp_id": int(answer.item_id),
        "skoor": answer.score,
        "valitud_vastus": answer.selected_answer,
        "vastatud_ajal": _encode_datetime(answer.answered_at),
    }


def decode_answer(row: Row) -> AnswerRecord:
    return AnswerRecord(
        submission_id=SubmissionId(_uuid(row, "vastus_id")),
        test_id=TestId(_uuid(row, "test_id")),
        item_id=ItemId(_integer(row, "yp_id")),
        score=_integer(row, "skoor"),
        selected_answer=_string(row, "valitud_vastus"),
        answered_at=_optional_datetime(row, "vastatud_ajal"),
    )


def encode_yg_order(order: YgOrder) -> EncodedRow:
    row: EncodedRow = {
        "test_id": str(order.test_id),
        "kursus": order.course,
        "graafi_objektid": list(order.nodes),
        "kognitiivne_tase": order.cognitive_level,
        "maht": order.volume,
        "staatus": _YG_TO_DB[order.status],
        "ylesande_taotlused": [
            {"node": request.node, "amount": request.amount}
            for request in order.item_requests
        ],
    }
    if order.order_id is not None:
        row["id"] = int(order.order_id)
    return row


def decode_yg_order(row: Row) -> YgOrder:
    raw_id = row.get("id")
    request_values = _optional_sequence(row, "ylesande_taotlused")
    requests = tuple(
        _decode_inventory_request(_as_mapping(value, "ylesande_taotlus"))
        for value in request_values
    )
    result_values = _optional_sequence(row, "taitmise_tulemus")
    results = tuple(
        _decode_inventory_result(_as_mapping(value, "taitmise_tulemus"))
        for value in result_values
    )
    legacy_nodes = _string_tuple(
        _sequence(row, "graafi_objektid"), "graafi_objektid"
    )
    legacy_volume = _integer(row, "maht")
    if not requests:
        requests = tuple(
            InventoryRequest(node=node, amount=legacy_volume)
            for node in legacy_nodes
        )
        effective_nodes = legacy_nodes
        effective_volume = legacy_volume
    else:
        request_nodes = tuple(request.node for request in requests)
        if len(request_nodes) != len(set(request_nodes)):
            raise RepositoryDataError(
                "ylesande_taotlused must not contain duplicate nodes"
            )
        effective_nodes = request_nodes
        effective_volume = max(request.amount for request in requests)
    return YgOrder(
        order_id=None if raw_id is None else YgOrderId(_expect_int(raw_id, "id")),
        test_id=TestId(_uuid(row, "test_id")),
        course=_string(row, "kursus"),
        nodes=effective_nodes,
        cognitive_level=_optional_string(row, "kognitiivne_tase"),
        volume=effective_volume,
        status=_enum_value(_YG_FROM_DB, row, "staatus"),
        created_at=_optional_datetime(row, "loodud"),
        item_requests=requests,
        fulfillment_results=results,
    )


def encode_session(session: AssessmentSession) -> EncodedRow:
    if not isinstance(session.player_state, PlayerState):
        raise RepositoryDataError("legacy player state cannot be written")
    if session.player_state.schema_version != PLAYER_STATE_SCHEMA_VERSION:
        raise RepositoryDataError(
            f"unsupported player state schema version: {session.player_state.schema_version}"
        )
    return {
        "test_id": str(session.test_id),
        "kasutaja_id": session.user_id,
        "rada_id": str(session.learning_path_id),
        "graaf_hash": session.graph_hash,
        "staatus": _SESSION_TO_DB[session.status],
        "alustatud": _encode_datetime(session.started_at),
        "lopp_profiil": (
            None
            if session.final_profile is None
            else encode_final_profile(session.final_profile)
        ),
        "testi_loogika": (
            None
            if session.model is None
            else encode_kst_model(_require_v2_model(session.model))
        ),
        "metoodika": session.method.value,
        "tp_seisund": encode_player_state(session.player_state),
        "eesmark": session.goal,
    }


def decode_session(row: Row) -> AssessmentSession:
    raw_state = _mapping(row, "tp_seisund")
    raw_model = row.get("testi_loogika")
    raw_profile = row.get("lopp_profiil")
    method_text = _string(row, "metoodika")
    try:
        method = AssessmentMethod(method_text)
    except ValueError as error:
        raise RepositoryDataError(
            f"unknown assessment method: {method_text!r}"
        ) from error
    return AssessmentSession(
        test_id=TestId(_uuid(row, "test_id")),
        user_id=_string(row, "kasutaja_id"),
        learning_path_id=LearningPathId(_string(row, "rada_id")),
        graph_hash=_optional_string(row, "graaf_hash"),
        status=_enum_value(_SESSION_FROM_DB, row, "staatus"),
        started_at=_datetime(row, "alustatud"),
        method=method,
        player_state=decode_player_state(raw_state),
        model=(
            None
            if raw_model is None or _is_empty_mapping(raw_model)
            else decode_kst_model(_as_mapping(raw_model, "testi_loogika"))
        ),
        final_profile=(
            None
            if raw_profile is None
            else decode_final_profile(_as_mapping(raw_profile, "lopp_profiil"))
        ),
        goal=_optional_string(row, "eesmark"),
    )


def encode_player_state(state: PlayerState) -> dict[str, JsonValue]:
    if state.schema_version != PLAYER_STATE_SCHEMA_VERSION:
        raise RepositoryDataError(
            f"unsupported player state schema version: {state.schema_version}"
        )
    _validate_player_state_invariants(state)
    return {
        "schema_version": state.schema_version,
        "posterior": list(state.posterior),
        "answered_items": [
            {
                "submission_id": str(answer.submission_id),
                "item_id": int(answer.item_id),
                "node": answer.node,
                "response_correct": answer.response_correct,
            }
            for answer in state.answered_items
        ],
        "current_question": (
            None
            if state.current_question is None
            else _encode_current_question(state.current_question)
        ),
        "pending_graph": (
            None
            if state.pending_graph is None
            else _encode_pending_graph(state.pending_graph)
        ),
        "session_pool": (
            None
            if state.session_pool is None
            else {
                "candidates": [
                    _encode_candidate(candidate)
                    for candidate in state.session_pool.candidates
                ]
            }
        ),
        "inventory_plan": (
            None
            if state.inventory_plan is None
            else {
                "required_per_node": state.inventory_plan.required_per_node,
                "requests": [
                    {"node": request.node, "amount": request.amount}
                    for request in state.inventory_plan.requests
                ],
            }
        ),
    }


def decode_player_state(data: Row) -> PlayerState | LegacyPlayerState:
    version = data.get("schema_version")
    if version is None:
        # The deployed legacy shape used kysitud and had no submission tokens.
        legacy_answers: list[AnsweredItem] = []
        for index, value in enumerate(_optional_sequence(data, "kysitud")):
            answer = _as_mapping(value, "kysitud")
            legacy_answers.append(
                AnsweredItem(
                    submission_id=SubmissionId(
                        UUID(int=index + 1)
                    ),  # stable sentinel; legacy sessions are never resumed
                    item_id=ItemId(_integer(answer, "yp_id")),
                    node=_string(answer, "solm"),
                    response_correct=_boolean(answer, "vastus_oige"),
                )
            )
        return LegacyPlayerState(
            posterior=_number_tuple(_optional_sequence(data, "posterior"), "posterior"),
            answered_items=tuple(legacy_answers),
        )
    if not isinstance(version, int) or isinstance(version, bool):
        raise RepositoryDataError("tp_seisund.schema_version must be an integer")
    if version == 1:
        return LegacyPlayerState(
            posterior=_number_tuple(_sequence(data, "posterior"), "posterior"),
            answered_items=tuple(
                _decode_answered_item(_as_mapping(value, "answered_item"))
                for value in _sequence(data, "answered_items")
            ),
        )
    if version != PLAYER_STATE_SCHEMA_VERSION:
        raise RepositoryDataError(f"unsupported player state schema version: {version}")
    current = data.get("current_question")
    pending = data.get("pending_graph")
    pool = data.get("session_pool")
    inventory = data.get("inventory_plan")
    state = PlayerState(
        schema_version=version,
        posterior=_number_tuple(_sequence(data, "posterior"), "posterior"),
        answered_items=tuple(
            _decode_answered_item(_as_mapping(value, "answered_item"))
            for value in _sequence(data, "answered_items")
        ),
        current_question=(
            None
            if current is None
            else _decode_current_question(_as_mapping(current, "current_question"))
        ),
        pending_graph=(
            None
            if pending is None
            else _decode_pending_graph(_as_mapping(pending, "pending_graph"))
        ),
        session_pool=(
            None
            if pool is None
            else SessionPool(
                candidates=tuple(
                    _decode_candidate(_as_mapping(value, "candidate"))
                    for value in _sequence(
                        _as_mapping(pool, "session_pool"), "candidates"
                    )
                )
            )
        ),
        inventory_plan=(
            None
            if inventory is None
            else _decode_inventory_plan(
                _as_mapping(inventory, "inventory_plan")
            )
        ),
    )
    _validate_player_state_invariants(state)
    return state


def encode_kst_model(model: KstModel) -> dict[str, JsonValue]:
    if model.schema_version != KST_MODEL_SCHEMA_VERSION:
        raise RepositoryDataError(
            f"unsupported KST model schema version: {model.schema_version}"
        )
    return {
        "schema_version": model.schema_version,
        "method": model.method.value,
        "nodes": list(model.nodes),
        "knowledge_states": [list(state.nodes) for state in model.knowledge_states],
        "matrix": [list(row) for row in model.matrix],
        "uniform_prior": list(model.uniform_prior),
        "configuration": _encode_kst_configuration(model.configuration),
        "configuration_hash": model.configuration_hash,
        "reliability_floor": model.derived_limits.reliability_floor,
        "safety_cap": model.derived_limits.safety_cap,
    }


def decode_kst_model(data: Row) -> KstModel | LegacyKstModel:
    version = _integer(data, "schema_version")
    if version not in (1, KST_MODEL_SCHEMA_VERSION):
        raise RepositoryDataError(f"unsupported KST model schema version: {version}")
    method_text = _string(data, "method")
    if method_text != AssessmentMethod.KST.value:
        raise RepositoryDataError(f"unknown KST model method: {method_text!r}")
    nodes = _string_tuple(_sequence(data, "nodes"), "nodes")
    knowledge_states = tuple(
        KnowledgeState(
            _string_tuple(_as_sequence(value, "knowledge_state"), "knowledge_state")
        )
        for value in _sequence(data, "knowledge_states")
    )
    matrix = tuple(
        _integer_tuple(_as_sequence(value, "matrix row"), "matrix row")
        for value in _sequence(data, "matrix")
    )
    uniform_prior = _number_tuple(
        _sequence(data, "uniform_prior"), "uniform_prior"
    )
    configuration = _decode_kst_configuration(_mapping(data, "configuration"))
    configuration_hash = _string(data, "configuration_hash")
    if version == 1:
        return LegacyKstModel(
            schema_version=version,
            method=AssessmentMethod.KST,
            nodes=nodes,
            knowledge_states=knowledge_states,
            matrix=matrix,
            uniform_prior=uniform_prior,
            configuration=configuration,
            configuration_hash=configuration_hash,
            beta=_number_tuple(_sequence(data, "beta"), "beta"),
            eta=_number_tuple(_sequence(data, "eta"), "eta"),
        )
    return KstModel(
        schema_version=version,
        method=AssessmentMethod.KST,
        nodes=nodes,
        knowledge_states=knowledge_states,
        matrix=matrix,
        uniform_prior=uniform_prior,
        configuration=configuration,
        configuration_hash=configuration_hash,
        derived_limits=DerivedLimits(
            reliability_floor=_nonnegative_integer(data, "reliability_floor"),
            safety_cap=_nonnegative_integer(data, "safety_cap"),
        ),
    )


def encode_final_profile(profile: FinalProfile) -> dict[str, JsonValue]:
    return {
        "omandatud": list(profile.mastered),
        "valmis_oppima": list(profile.ready_to_learn),
        "ebamaarane_edasi": list(profile.uncertain_ahead),
        "ebamaarane_tagasi": list(profile.uncertain_prerequisite),
        "veel_mitte": list(profile.not_yet),
        "kokkuvote": profile.summary,
        "peatumise_pohjus": _STOP_TO_DB[profile.stop_reason],
        "kindlus_parim_olek": profile.best_state_confidence,
        "kindlus_C_hulgas": profile.credible_mass,
        "n_usutavaid_olekuid": profile.credible_state_count,
    }


def decode_final_profile(data: Row) -> FinalProfile:
    return FinalProfile(
        mastered=_string_tuple(_sequence(data, "omandatud"), "omandatud"),
        ready_to_learn=_string_tuple(_sequence(data, "valmis_oppima"), "valmis_oppima"),
        uncertain_ahead=_string_tuple(
            _sequence(data, "ebamaarane_edasi"), "ebamaarane_edasi"
        ),
        uncertain_prerequisite=_string_tuple(
            _sequence(data, "ebamaarane_tagasi"), "ebamaarane_tagasi"
        ),
        not_yet=_string_tuple(_sequence(data, "veel_mitte"), "veel_mitte"),
        summary=_optional_string(data, "kokkuvote"),
        stop_reason=_enum_value(_STOP_FROM_DB, data, "peatumise_pohjus"),
        best_state_confidence=_number(data, "kindlus_parim_olek"),
        credible_mass=_number(data, "kindlus_C_hulgas"),
        credible_state_count=_integer(data, "n_usutavaid_olekuid"),
    )


def _encode_kst_configuration(configuration: KstConfiguration) -> dict[str, JsonValue]:
    if configuration.schema_version != KST_CONFIGURATION_SCHEMA_VERSION:
        raise RepositoryDataError(
            "unsupported KST configuration schema version: "
            f"{configuration.schema_version}"
        )
    return {
        "schema_version": configuration.schema_version,
        "stop_confidence": configuration.stop_confidence,
        "feedback_credible_mass": configuration.feedback_credible_mass,
        "reliability_floor": {
            "minimum": configuration.reliability_floor.minimum,
            "multiplier": configuration.reliability_floor.multiplier,
            "maximum": configuration.reliability_floor.maximum,
        },
        "safety_cap": {
            "node_multiplier": configuration.safety_cap.node_multiplier,
            "responses_above_floor": configuration.safety_cap.responses_above_floor,
        },
    }


def _decode_kst_configuration(data: Row) -> KstConfiguration:
    version = _integer(data, "schema_version")
    if version != KST_CONFIGURATION_SCHEMA_VERSION:
        raise RepositoryDataError(
            f"unsupported KST configuration schema version: {version}"
        )
    floor = _mapping(data, "reliability_floor")
    cap = _mapping(data, "safety_cap")
    return KstConfiguration(
        schema_version=version,
        stop_confidence=_number(data, "stop_confidence"),
        feedback_credible_mass=_number(data, "feedback_credible_mass"),
        reliability_floor=ReliabilityFloorConfiguration(
            minimum=_integer(floor, "minimum"),
            multiplier=_number(floor, "multiplier"),
            maximum=_integer(floor, "maximum"),
        ),
        safety_cap=SafetyCapConfiguration(
            node_multiplier=_number(cap, "node_multiplier"),
            responses_above_floor=_integer(cap, "responses_above_floor"),
        ),
    )


def _encode_current_question(question: CurrentQuestion) -> dict[str, JsonValue]:
    return {
        "submission_id": str(question.submission_id),
        "item_id": int(question.item_id),
        "node": question.node,
        "instruction": question.instruction,
        "prompt": question.prompt,
        "stimulus": question.stimulus,
        "options": [
            {"id": str(option.option_id), "text": option.text}
            for option in question.options
        ],
        "candidate_id": str(question.candidate_id),
        "beta": question.beta,
        "eta": question.eta,
        "correct_option_id": str(question.correct_option_id),
    }


def _decode_current_question(data: Row) -> CurrentQuestion:
    return CurrentQuestion(
        submission_id=SubmissionId(_uuid(data, "submission_id")),
        item_id=ItemId(_integer(data, "item_id")),
        node=_string(data, "node"),
        instruction=_string(data, "instruction"),
        prompt=_string(data, "prompt"),
        stimulus=_optional_string(data, "stimulus"),
        options=tuple(
            QuestionOption(
                option_id=OptionId(_string(_as_mapping(value, "option"), "id")),
                text=_string(_as_mapping(value, "option"), "text"),
            )
            for value in _sequence(data, "options")
        ),
        candidate_id=CandidateId(_string(data, "candidate_id")),
        beta=_probability(data, "beta"),
        eta=_probability(data, "eta"),
        correct_option_id=OptionId(_string(data, "correct_option_id")),
    )


def _encode_pending_graph(graph: PendingGraph) -> dict[str, JsonValue]:
    return {
        "graph_hash": graph.graph_hash,
        "nodes": list(graph.nodes),
        "relations": [
            {"from": relation.prerequisite, "to": relation.dependent}
            for relation in graph.relations
        ],
    }


def _decode_pending_graph(data: Row) -> PendingGraph:
    return PendingGraph(
        graph_hash=_string(data, "graph_hash"),
        nodes=_string_tuple(_sequence(data, "nodes"), "nodes"),
        relations=tuple(
            GraphRelation(
                prerequisite=_string(_as_mapping(value, "relation"), "from"),
                dependent=_string(_as_mapping(value, "relation"), "to"),
            )
            for value in _sequence(data, "relations")
        ),
    )


def _decode_answered_item(data: Row) -> AnsweredItem:
    return AnsweredItem(
        submission_id=SubmissionId(_uuid(data, "submission_id")),
        item_id=ItemId(_integer(data, "item_id")),
        node=_string(data, "node"),
        response_correct=_boolean(data, "response_correct"),
    )


def _encode_candidate(candidate: ItemCandidate) -> dict[str, JsonValue]:
    return {
        "candidate_id": str(candidate.candidate_id),
        "item_id": int(candidate.item_id),
        "node": candidate.node,
        "beta": candidate.beta,
        "eta": candidate.eta,
    }


def _decode_candidate(data: Row) -> ItemCandidate:
    candidate_id = _string(data, "candidate_id")
    if not candidate_id.strip():
        raise RepositoryDataError("candidate_id must not be blank")
    return ItemCandidate(
        candidate_id=CandidateId(candidate_id),
        item_id=ItemId(_integer(data, "item_id")),
        node=_string(data, "node"),
        beta=_probability(data, "beta"),
        eta=_probability(data, "eta"),
    )


def _decode_inventory_plan(data: Row) -> InventoryPlan:
    return InventoryPlan(
        required_per_node=_nonnegative_integer(data, "required_per_node"),
        requests=tuple(
            _decode_inventory_request(
                _as_mapping(value, "inventory_request")
            )
            for value in _sequence(data, "requests")
        ),
    )


def _decode_inventory_request(data: Row) -> InventoryRequest:
    _require_exact_fields(data, {"node", "amount"}, "ylesande_taotlus")
    return InventoryRequest(
        node=_nonblank_string(data, "node"),
        amount=_positive_integer(data, "amount"),
    )


def _decode_inventory_result(data: Row) -> InventoryResult:
    _require_exact_fields(
        data,
        {
            "node",
            "requested",
            "baseline_usable",
            "created",
            "usable_after",
            "remaining",
        },
        "taitmise_tulemus",
    )
    return InventoryResult(
        node=_nonblank_string(data, "node"),
        requested=_nonnegative_integer(data, "requested"),
        baseline_usable=_nonnegative_integer(data, "baseline_usable"),
        created=_nonnegative_integer(data, "created"),
        usable_after=_nonnegative_integer(data, "usable_after"),
        remaining=_nonnegative_integer(data, "remaining"),
    )


def _require_exact_fields(data: Row, expected: set[str], name: str) -> None:
    actual = set(data)
    if actual != expected:
        raise RepositoryDataError(
            f"{name} fields must be exactly {sorted(expected)}"
        )


def _validate_player_state_invariants(state: PlayerState) -> None:
    answered_ids = tuple(answer.item_id for answer in state.answered_items)
    if len(answered_ids) != len(set(answered_ids)):
        raise RepositoryDataError("answered item IDs must be unique")
    if (
        state.current_question is not None
        and state.current_question.item_id in set(answered_ids)
    ):
        raise RepositoryDataError("current item must not appear in answer history")
    if state.current_question is not None:
        option_ids = tuple(
            option.option_id for option in state.current_question.options
        )
        if (
            len(option_ids) != len(set(option_ids))
            or state.current_question.correct_option_id not in option_ids
        ):
            raise RepositoryDataError(
                "current question must have unique options and a valid correct option"
            )
    if state.session_pool is not None:
        candidates = state.session_pool.candidates
        candidate_ids = tuple(candidate.candidate_id for candidate in candidates)
        pool_item_ids = tuple(candidate.item_id for candidate in candidates)
        if (
            len(candidate_ids) != len(set(candidate_ids))
            or len(pool_item_ids) != len(set(pool_item_ids))
        ):
            raise RepositoryDataError("session pool IDs must be unique")
        if any(
            not str(candidate.candidate_id).strip()
            or not candidate.node.strip()
            or not math.isfinite(candidate.beta)
            or not math.isfinite(candidate.eta)
            or not 0 <= candidate.beta <= 1
            or not 0 <= candidate.eta <= 1
            for candidate in candidates
        ):
            raise RepositoryDataError("session pool candidate metadata is invalid")
        if (
            state.current_question is not None
            and not any(
                candidate.candidate_id == state.current_question.candidate_id
                and candidate.item_id == state.current_question.item_id
                and candidate.node == state.current_question.node
                and candidate.beta == state.current_question.beta
                and candidate.eta == state.current_question.eta
                for candidate in candidates
            )
        ):
            raise RepositoryDataError(
                "current question must match one session pool candidate"
            )
    if state.inventory_plan is not None:
        requests = state.inventory_plan.requests
        request_nodes = tuple(request.node for request in requests)
        if (
            state.inventory_plan.required_per_node < 0
            or len(request_nodes) != len(set(request_nodes))
            or any(
                not request.node.strip() or request.amount < 1
                for request in requests
            )
        ):
            raise RepositoryDataError("inventory plan is invalid")


def _require_v2_model(model: KstModel | LegacyKstModel) -> KstModel:
    if not isinstance(model, KstModel):
        raise RepositoryDataError("legacy KST models cannot be written")
    return model


def _enum_value[T](values: Mapping[str, T], row: Row, key: str) -> T:
    raw = _string(row, key)
    try:
        return values[raw]
    except KeyError as error:
        raise RepositoryDataError(f"unknown {key}: {raw!r}") from error


def _mapping(row: Row, key: str) -> Row:
    return _as_mapping(_required(row, key), key)


def _as_mapping(value: object, name: str) -> Row:
    if not isinstance(value, Mapping):
        raise RepositoryDataError(f"{name} must be an object")
    return cast(Row, value)


def _is_empty_mapping(value: object) -> bool:
    return isinstance(value, Mapping) and not cast(Row, value)


def _sequence(row: Row, key: str) -> Sequence[object]:
    return _as_sequence(_required(row, key), key)


def _optional_sequence(row: Row, key: str) -> Sequence[object]:
    value = row.get(key)
    return () if value is None else _as_sequence(value, key)


def _as_sequence(value: object, name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise RepositoryDataError(f"{name} must be an array")
    return cast(Sequence[object], value)


def _required(row: Row, key: str) -> object:
    try:
        return row[key]
    except KeyError as error:
        raise RepositoryDataError(f"missing required field: {key}") from error


def _string(row: Row, key: str) -> str:
    value = _required(row, key)
    if not isinstance(value, str):
        raise RepositoryDataError(f"{key} must be a string")
    return value


def _nonblank_string(row: Row, key: str) -> str:
    value = _string(row, key)
    if not value.strip():
        raise RepositoryDataError(f"{key} must not be blank")
    return value


def _optional_string(row: Row, key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise RepositoryDataError(f"{key} must be a string or null")
    return value


def _integer(row: Row, key: str) -> int:
    return _expect_int(_required(row, key), key)


def _expect_int(value: object, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise RepositoryDataError(f"{name} must be an integer")
    return value


def _number(row: Row, key: str) -> float:
    value = _required(row, key)
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise RepositoryDataError(f"{key} must be a number")
    return float(value)


def _probability(row: Row, key: str) -> float:
    value = _number(row, key)
    if not 0 <= value <= 1:
        raise RepositoryDataError(f"{key} must be between 0 and 1")
    return value


def _nonnegative_integer(row: Row, key: str) -> int:
    value = _integer(row, key)
    if value < 0:
        raise RepositoryDataError(f"{key} must be non-negative")
    return value


def _positive_integer(row: Row, key: str) -> int:
    value = _integer(row, key)
    if value < 1:
        raise RepositoryDataError(f"{key} must be positive")
    return value


def _boolean(row: Row, key: str) -> bool:
    value = _required(row, key)
    if not isinstance(value, bool):
        raise RepositoryDataError(f"{key} must be a boolean")
    return value


def _uuid(row: Row, key: str) -> UUID:
    raw = _string(row, key)
    try:
        return UUID(raw)
    except ValueError as error:
        raise RepositoryDataError(f"{key} must be a UUID") from error


def _datetime(row: Row, key: str) -> datetime:
    value = _optional_datetime(row, key)
    if value is None:
        raise RepositoryDataError(f"{key} must be an ISO-8601 timestamp")
    return value


def _optional_datetime(row: Row, key: str) -> datetime | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise RepositoryDataError(f"{key} must be an ISO-8601 timestamp or null")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise RepositoryDataError(f"{key} must be an ISO-8601 timestamp") from error


def _encode_datetime(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _string_tuple(values: Sequence[object], name: str) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise RepositoryDataError(f"{name} entries must be strings")
        result.append(value)
    return tuple(result)


def _integer_tuple(values: Sequence[object], name: str) -> tuple[int, ...]:
    return tuple(_expect_int(value, name) for value in values)


def _number_tuple(values: Sequence[object], name: str) -> tuple[float, ...]:
    result: list[float] = []
    for value in values:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise RepositoryDataError(f"{name} entries must be numbers")
        result.append(float(value))
    return tuple(result)
