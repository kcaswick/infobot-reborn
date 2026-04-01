"""Detect factoid creation intents from user input."""

from __future__ import annotations

import re

from infobot.nlu.intents import FactoidCreateIntent, ModificationType

_WHITESPACE_RE = re.compile(r"\s+")


_REPLACE_RE = re.compile(
    r"""
    ^no,?\s+        # Optional 'no' with optional comma
    (?P<key>.+?)    # The topic
    \s+
    (?P<verb>is|are)# The verb (is/are)
    \s+
    (?P<value>.+)   # The definition
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)

_APPEND_RE = re.compile(
    r"""
    ^
    (?P<key>.+?)    # The topic
    \s+
    (?P<verb>is|are)# The verb (is/are)
    \s+also\s+
    (?P<value>.+)   # The definition
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)

_SET_RE = re.compile(
    r"""
    ^
    (?P<key>.+?)    # The topic
    \s+
    (?P<verb>is|are)# The verb (is/are)
    \s+
    (?P<value>.+)   # The definition
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)

_QUESTION_STARTERS = (
    "what is",
    "what are",
    "where is",
    "where are",
    "who is",
    "who are",
    "is ",
    "are ",
    "why ",
    "how ",
    "tell me about",
)


def detect_factoid_create_intent(message: str) -> FactoidCreateIntent | None:
    """Detect factoid creation/modification intents.

    Args:
        message: User message to evaluate.

    Returns:
        FactoidCreateIntent if the message is a factoid statement, else None.
    """

    normalized = _normalize_text(message)
    if not normalized:
        return None

    lowered = normalized.lower()
    if lowered.endswith("?"):
        return None

    if any(lowered.startswith(starter) for starter in _QUESTION_STARTERS):
        return None

    if match := _REPLACE_RE.match(normalized):
        return _build_intent(match, ModificationType.REPLACE, message)

    if match := _APPEND_RE.match(normalized):
        return _build_intent(match, ModificationType.APPEND, message)

    if match := _SET_RE.match(normalized):
        return _build_intent(match, ModificationType.SET, message)

    return None


def _build_intent(
    match: re.Match[str],
    modification_type: ModificationType,
    original_text: str,
) -> FactoidCreateIntent:
    key = _normalize_text(match.group("key"))
    value = _normalize_text(match.group("value"))
    return FactoidCreateIntent(
        text=original_text,
        key=key,
        value=value,
        is_plural=match.group("verb").lower() == "are",
        modification_type=modification_type,
    )


def _normalize_text(value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        return ""
    return _WHITESPACE_RE.sub(" ", trimmed)
