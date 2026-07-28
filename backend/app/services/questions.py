"""Validated, non-leaking construction of persisted multiple-choice questions."""

from collections.abc import Callable
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from random import Random
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict

from app.domain.models import *


class InvalidQuestion(ValueError):
    """An item cannot produce a safe multiple-choice question."""


class RandomSource(Protocol):
    def shuffle(self, values: list[str]) -> None: ...


class QuestionOptionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    text: str


class QuestionOutput(BaseModel):
    """The exact player-safe question shape."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    submission_id: UUID
    item_id: int
    instruction: str
    prompt: str
    stimulus: str | None
    options: tuple[QuestionOptionOutput, ...]


def build_question(
    item: AssessmentItem,
    *,
    candidate: ItemCandidate | None = None,
    random_source: RandomSource | None = None,
    uuid_factory: Callable[[], UUID] = uuid4,
) -> CurrentQuestion:
    """Build one persisted question with fresh opaque identifiers."""

    if not item.answer_key.strip():
        raise InvalidQuestion("answer key must be non-empty")

    choices = _distinct_choices(item.answer_key, item.distractors)
    if len(choices) < 2:
        raise InvalidQuestion("question must have at least two distinct options")

    comparable: list[float] = []
    for choice in choices:
        value = _comparable_value(choice)
        if value is None:
            comparable = []
            break
        comparable.append(value)
    if comparable:
        ordered = [
            pair[1]
            for pair in sorted(
                zip(comparable, choices, strict=True),
                key=lambda pair: pair[0],
                reverse=True,
            )
        ]
    else:
        ordered = list(choices)
        (random_source or Random()).shuffle(ordered)

    persisted_options = tuple(
        QuestionOption(option_id=OptionId(str(uuid_factory())), text=text)
        for text in ordered
    )
    selected_candidate = candidate or ItemCandidate(
        candidate_id=CandidateId(f"yp:{int(item.item_id)}"),
        item_id=item.item_id,
        node=item.node,
        beta=item.beta,
        eta=item.eta,
    )
    correct_option = next(
        option.option_id
        for option in persisted_options
        if option.text == item.answer_key
    )
    return CurrentQuestion(
        submission_id=SubmissionId(uuid_factory()),
        item_id=item.item_id,
        node=item.node,
        instruction=item.instruction,
        prompt=item.prompt,
        stimulus=item.stimulus,
        options=persisted_options,
        candidate_id=selected_candidate.candidate_id,
        beta=selected_candidate.beta,
        eta=selected_candidate.eta,
        correct_option_id=correct_option,
    )


def to_question_output(question: CurrentQuestion) -> QuestionOutput:
    """Remove server-only node identity while preserving persisted option order."""

    return QuestionOutput(
        submission_id=UUID(str(question.submission_id)),
        item_id=int(question.item_id),
        instruction=question.instruction,
        prompt=question.prompt,
        stimulus=question.stimulus,
        options=tuple(
            QuestionOptionOutput(id=str(option.option_id), text=option.text)
            for option in question.options
        ),
    )


def _distinct_choices(answer_key: str, distractors: tuple[str, ...]) -> tuple[str, ...]:
    choices: list[str] = [answer_key]
    seen = {answer_key}
    for distractor in distractors:
        if not distractor.strip() or distractor in seen:
            continue
        seen.add(distractor)
        choices.append(distractor)
    return tuple(choices)


def _comparable_value(value: str) -> float | None:
    text = value.strip()
    try:
        return float(Decimal(text))
    except InvalidOperation:
        pass

    normalized = text.replace(".", ":", 1) if ":" not in text else text
    try:
        parsed_time = time.fromisoformat(normalized)
    except ValueError:
        parsed_time = None
    if parsed_time is not None:
        return (
            parsed_time.hour * 3600
            + parsed_time.minute * 60
            + parsed_time.second
            + parsed_time.microsecond / 1_000_000
        )

    try:
        parsed_datetime = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed_datetime.toordinal() * 86_400 + (
        parsed_datetime.hour * 3600
        + parsed_datetime.minute * 60
        + parsed_datetime.second
        + parsed_datetime.microsecond / 1_000_000
    )
