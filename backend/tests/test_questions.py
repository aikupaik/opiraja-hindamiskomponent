"""Question validation, ordering, identifiers, and response redaction."""

from dataclasses import replace
from uuid import UUID

import pytest

from app.domain.models import ItemId
from app.services.questions import InvalidQuestion, build_question, to_question_output
from tests.factories import make_item


class ReverseRandom:
    def shuffle(self, values: list[str]) -> None:
        values.reverse()


class Uuids:
    def __init__(self) -> None:
        self.value = 0

    def __call__(self) -> UUID:
        self.value += 1
        return UUID(int=self.value)


def test_numeric_options_are_descending_and_ids_are_fresh() -> None:
    item = replace(
        make_item(ItemId(7)),
        answer_key="2",
        distractors=("10", "1", "10", " "),
    )
    uuids = Uuids()

    question = build_question(item, uuid_factory=uuids)

    assert [option.text for option in question.options] == ["10", "2", "1"]
    assert len({option.option_id for option in question.options}) == 3
    assert question.submission_id not in {
        option.option_id for option in question.options
    }


def test_dates_and_times_are_descending_while_words_shuffle_once() -> None:
    dates = replace(
        make_item(),
        answer_key="2026-01-02",
        distractors=("2025-12-31", "2026-02-01"),
    )
    words = replace(
        make_item(),
        answer_key="correct",
        distractors=("first", "second"),
    )

    date_question = build_question(dates)
    word_question = build_question(words, random_source=ReverseRandom())

    assert [option.text for option in date_question.options] == [
        "2026-02-01",
        "2026-01-02",
        "2025-12-31",
    ]
    assert [option.text for option in word_question.options] == [
        "second",
        "first",
        "correct",
    ]


@pytest.mark.parametrize(
    ("key", "distractors"),
    [
        (" ", ("A", "B")),
        ("same", ("", " ", "same")),
    ],
)
def test_invalid_choices_are_rejected(key: str, distractors: tuple[str, ...]) -> None:
    with pytest.raises(InvalidQuestion):
        build_question(replace(make_item(), answer_key=key, distractors=distractors))


def test_player_output_has_no_node_or_answer_metadata() -> None:
    question = build_question(make_item(), uuid_factory=Uuids())

    output = to_question_output(question).model_dump(mode="json")

    assert set(output) == {
        "submission_id",
        "item_id",
        "instruction",
        "prompt",
        "stimulus",
        "options",
    }
    assert "node" not in str(output)
    assert "answer_key" not in str(output)
