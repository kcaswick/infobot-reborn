from infobot.nlu.intents import FactoidQueryIntent
from infobot.nlu.question_parser import parse_question


def test_parse_question_wh_word() -> None:
    intent = parse_question("What is the capital of France?")

    assert intent == FactoidQueryIntent(
        text="What is the capital of France?",
        key="the capital of France",
        question_word="what",
        pattern="wh_is",
    )


def test_parse_question_where() -> None:
    intent = parse_question("Where is Area 51")

    assert intent == FactoidQueryIntent(
        text="Where is Area 51",
        key="Area 51",
        question_word="where",
        pattern="wh_is",
    )


def test_parse_question_who() -> None:
    intent = parse_question("Who is Ada Lovelace?")

    assert intent == FactoidQueryIntent(
        text="Who is Ada Lovelace?",
        key="Ada Lovelace",
        question_word="who",
        pattern="wh_is",
    )


def test_parse_question_bare_question_mark() -> None:
    intent = parse_question("TCP?")

    assert intent == FactoidQueryIntent(
        text="TCP?",
        key="TCP",
        question_word=None,
        pattern="bare_question_mark",
    )


def test_parse_question_tell_me_about() -> None:
    intent = parse_question("tell me about gravity")

    assert intent == FactoidQueryIntent(
        text="tell me about gravity",
        key="gravity",
        question_word=None,
        pattern="tell_me_about",
    )


def test_parse_question_normalizes_whitespace() -> None:
    intent = parse_question("  What   is   the   Moon   ?  ")

    assert intent == FactoidQueryIntent(
        text="  What   is   the   Moon   ?  ",
        key="the Moon",
        question_word="what",
        pattern="wh_is",
    )


def test_parse_question_non_question() -> None:
    assert parse_question("Hello there") is None


def test_parse_question_blank() -> None:
    assert parse_question("   ") is None


def test_parse_question_wh_are() -> None:
    intent = parse_question("What are dogs?")

    assert intent == FactoidQueryIntent(
        text="What are dogs?",
        key="dogs",
        question_word="what",
        pattern="wh_is",
    )


def test_parse_question_wh_was() -> None:
    intent = parse_question("What was the Cold War?")

    assert intent == FactoidQueryIntent(
        text="What was the Cold War?",
        key="the Cold War",
        question_word="what",
        pattern="wh_is",
    )


def test_parse_question_wh_were() -> None:
    intent = parse_question("Where were the pyramids built?")

    assert intent == FactoidQueryIntent(
        text="Where were the pyramids built?",
        key="the pyramids built",
        question_word="where",
        pattern="wh_is",
    )
