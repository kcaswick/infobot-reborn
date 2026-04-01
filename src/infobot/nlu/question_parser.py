"""Question parsing utilities for Infobot NLU."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from infobot.nlu.intents import FactoidQueryIntent

_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class _PatternRule:
    name: str
    pattern: re.Pattern[str]
    question_word_group: str | None


_QUESTION_RULES: tuple[_PatternRule, ...] = (
    _PatternRule(
        name="wh_is",
        pattern=re.compile(
            r"^\s*(?P<qword>what|where|who)(?:\s+(?:is|are|was|were))?\s+(?P<key>.+?)\s*\??\s*$",
            re.IGNORECASE,
        ),
        question_word_group="qword",
    ),
    _PatternRule(
        name="tell_me_about",
        pattern=re.compile(
            r"^\s*tell\s+me\s+about\s+(?P<key>.+?)\s*[?.!]?\s*$",
            re.IGNORECASE,
        ),
        question_word_group=None,
    ),
    _PatternRule(
        name="bare_question_mark",
        pattern=re.compile(r"^\s*(?P<key>[^?]+?)\s*\?\s*$"),
        question_word_group=None,
    ),
)


def parse_question(message: str) -> FactoidQueryIntent | None:
    """Parse a message into a question intent.

    Args:
        message: Incoming user message.

    Returns:
        FactoidQueryIntent if a supported question pattern is found, otherwise None.
    """

    normalized = _normalize_text(message)
    if not normalized:
        return None

    for rule in _QUESTION_RULES:
        match = rule.pattern.match(normalized)
        if not match:
            continue

        key = _normalize_text(match.group("key"))
        if not key:
            continue

        question_word = _extract_question_word(match, rule.question_word_group)
        return FactoidQueryIntent(
            text=message,
            key=key,
            question_word=question_word,
            pattern=rule.name,
        )

    return None


def _normalize_text(value: str) -> str:
    trimmed = value.strip()
    if not trimmed:
        return ""
    return _WHITESPACE_RE.sub(" ", trimmed)


def _extract_question_word(
    match: re.Match[str],
    group: str | None,
) -> str | None:
    if group is None:
        return None

    qword = match.group(group)
    if not qword:
        return None

    return qword.lower()


def candidate_patterns() -> Iterable[str]:
    """Return the names of supported question patterns."""

    return tuple(rule.name for rule in _QUESTION_RULES)
