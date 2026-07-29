"""Small deterministic domain factories shared by persistence tests."""

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from app.domain.models import (
    ActivationCommand,
    AnswerRecord,
    AnswerTransition,
    AnsweredItem,
    AssessmentItem,
    AssessmentMethod,
    AssessmentSession,
    CurrentQuestion,
    CandidateId,
    DerivedLimits,
    FinalProfile,
    ItemId,
    KstConfiguration,
    KstModel,
    KnowledgeState,
    LearningPathId,
    OptionId,
    PLAYER_STATE_SCHEMA_VERSION,
    PlayerState,
    QuestionOption,
    SessionPool,
    ItemCandidate,
    InventoryPlan,
    InventoryRequest,
    ReliabilityFloorConfiguration,
    SafetyCapConfiguration,
    SessionStatus,
    StopReason,
    SubmissionId,
    TestId,
)

NOW = datetime(2026, 7, 26, 10, 30, tzinfo=UTC)
TEST_ID = TestId(UUID("10000000-0000-4000-8000-000000000001"))
SUBMISSION_ID = SubmissionId(UUID("20000000-0000-4000-8000-000000000001"))
NEXT_SUBMISSION_ID = SubmissionId(UUID("20000000-0000-4000-8000-000000000002"))
ITEM_ID = ItemId(41)
NEXT_ITEM_ID = ItemId(42)
GRAPH_HASH = (
    "kst-graph-v1:sha256:"
    "abcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcd"
)


def make_item(
    item_id: ItemId = ITEM_ID,
    *,
    node: str = "A",
    usage_count: int = 0,
) -> AssessmentItem:
    return AssessmentItem(
        item_id=item_id,
        node=node,
        instruction="Choose one.",
        prompt="What is A?",
        stimulus=None,
        answer_key="Correct",
        distractors=("Wrong 1", "Wrong 2", "Wrong 3"),
        beta=0.05,
        eta=0.25,
        usage_count=usage_count,
    )


def make_question(
    submission_id: SubmissionId = SUBMISSION_ID,
    item_id: ItemId = ITEM_ID,
    *,
    node: str = "A",
) -> CurrentQuestion:
    return CurrentQuestion(
        submission_id=submission_id,
        item_id=item_id,
        node=node,
        instruction="Choose one.",
        prompt=f"What is {node}?",
        stimulus=None,
        options=(
            QuestionOption(OptionId("option-1"), "Correct"),
            QuestionOption(OptionId("option-2"), "Wrong"),
        ),
        candidate_id=CandidateId(f"yp:{int(item_id)}"),
        beta=0.05,
        eta=0.25,
        correct_option_id=OptionId("option-1"),
    )


def make_model() -> KstModel:
    return KstModel(
        schema_version=2,
        method=AssessmentMethod.KST,
        nodes=("A", "B"),
        knowledge_states=(
            KnowledgeState(()),
            KnowledgeState(("A",)),
            KnowledgeState(("A", "B")),
        ),
        matrix=((0, 0), (1, 0), (1, 1)),
        uniform_prior=(1 / 3, 1 / 3, 1 / 3),
        configuration=KstConfiguration(
            schema_version=1,
            stop_confidence=0.8,
            feedback_credible_mass=0.9,
            reliability_floor=ReliabilityFloorConfiguration(
                minimum=7, multiplier=1.5, maximum=10
            ),
            safety_cap=SafetyCapConfiguration(
                node_multiplier=2, responses_above_floor=1
            ),
        ),
        configuration_hash=(
            "kst-config-v1:sha256:"
            "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
        ),
        derived_limits=DerivedLimits(reliability_floor=7, safety_cap=8),
    )


def make_session(
    *,
    status: SessionStatus = SessionStatus.ACTIVE,
    current_question: CurrentQuestion | None = None,
    answered_items: tuple[AnsweredItem, ...] = (),
    final_profile: FinalProfile | None = None,
) -> AssessmentSession:
    question = make_question() if current_question is None else current_question
    return AssessmentSession(
        test_id=TEST_ID,
        user_id="user-1",
        learning_path_id=LearningPathId("path-1"),
        graph_hash=GRAPH_HASH,
        status=status,
        started_at=NOW,
        method=AssessmentMethod.KST,
        player_state=PlayerState(
            schema_version=PLAYER_STATE_SCHEMA_VERSION,
            posterior=(0.2, 0.3, 0.5),
            answered_items=answered_items,
            current_question=question,
            session_pool=SessionPool(
                candidates=(
                    ItemCandidate(
                        candidate_id=CandidateId(f"yp:{int(question.item_id)}"),
                        item_id=question.item_id,
                        node=question.node,
                        beta=question.beta,
                        eta=question.eta,
                    ),
                )
            ),
        ),
        model=make_model(),
        final_profile=final_profile,
        goal="understanding",
    )


def make_preparing_session() -> AssessmentSession:
    return replace(
        make_session(status=SessionStatus.PREPARING),
        model=make_model(),
        player_state=PlayerState.new(
            posterior=make_model().uniform_prior,
            inventory_plan=InventoryPlan(
                required_per_node=3,
                requests=(InventoryRequest(node="B", amount=3),),
            ),
        ),
    )


def make_answer(
    submission_id: SubmissionId = SUBMISSION_ID,
    item_id: ItemId = ITEM_ID,
    *,
    selected_answer: str = "Correct",
) -> AnswerRecord:
    return AnswerRecord(
        submission_id=submission_id,
        test_id=TEST_ID,
        item_id=item_id,
        score=1,
        selected_answer=selected_answer,
        answered_at=NOW,
    )


def make_transition(
    *,
    previous: tuple[AnsweredItem, ...] = (),
    submission_id: SubmissionId = SUBMISSION_ID,
    item_id: ItemId = ITEM_ID,
    next_question: CurrentQuestion | None = None,
    profile: FinalProfile | None = None,
) -> AnswerTransition:
    answered = AnsweredItem(
        submission_id=submission_id,
        item_id=item_id,
        node="A",
        response_correct=True,
    )
    return AnswerTransition(
        next_player_state=PlayerState(
            schema_version=PLAYER_STATE_SCHEMA_VERSION,
            posterior=(0.1, 0.2, 0.7),
            answered_items=previous + (answered,),
            current_question=(
                make_question(NEXT_SUBMISSION_ID, NEXT_ITEM_ID, node="B")
                if next_question is None and profile is None
                else next_question
            ),
        ),
        final_profile=profile,
    )


def make_profile() -> FinalProfile:
    return FinalProfile(
        mastered=("A",),
        ready_to_learn=("B",),
        uncertain_ahead=(),
        uncertain_prerequisite=(),
        not_yet=("C",),
        summary=None,
        stop_reason=StopReason.NATURAL,
        best_state_confidence=0.81,
        credible_mass=0.95,
        credible_state_count=2,
    )


def make_activation() -> ActivationCommand:
    return ActivationCommand(
        test_id=TEST_ID,
        graph_hash=GRAPH_HASH,
        model=make_model(),
        first_question=make_question(),
        session_pool=SessionPool(
            candidates=(
                ItemCandidate(
                    candidate_id=CandidateId(f"yp:{int(ITEM_ID)}"),
                    item_id=ITEM_ID,
                    node="A",
                    beta=0.05,
                    eta=0.25,
                ),
            )
        ),
    )
