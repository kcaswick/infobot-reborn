from infobot.nlu.factoid_intent_detector import (
    FactoidCreateIntent,
    ModificationType,
    detect_factoid_create_intent,
)


def test_detect_factoid_set() -> None:
    intent = detect_factoid_create_intent("Python is a language")

    assert intent == FactoidCreateIntent(
        text="Python is a language",
        key="Python",
        value="a language",
        is_plural=False,
        modification_type=ModificationType.SET,
    )


def test_detect_factoid_plural() -> None:
    intent = detect_factoid_create_intent("Dogs are animals")

    assert intent == FactoidCreateIntent(
        text="Dogs are animals",
        key="Dogs",
        value="animals",
        is_plural=True,
        modification_type=ModificationType.SET,
    )


def test_detect_factoid_replace() -> None:
    intent = detect_factoid_create_intent("no, Python is a snake")

    assert intent == FactoidCreateIntent(
        text="no, Python is a snake",
        key="Python",
        value="a snake",
        is_plural=False,
        modification_type=ModificationType.REPLACE,
    )


def test_detect_factoid_append() -> None:
    intent = detect_factoid_create_intent("Python is also a comedy group")

    assert intent == FactoidCreateIntent(
        text="Python is also a comedy group",
        key="Python",
        value="a comedy group",
        is_plural=False,
        modification_type=ModificationType.APPEND,
    )


def test_detect_factoid_ignores_questions() -> None:
    assert detect_factoid_create_intent("What is Python?") is None
    assert detect_factoid_create_intent("Python is a snake?") is None


def test_detect_factoid_ignores_commands() -> None:
    assert detect_factoid_create_intent("tell me about Python") is None


def test_detect_factoid_empty() -> None:
    assert detect_factoid_create_intent("   ") is None
