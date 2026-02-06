"""Intent data models for NLU parsing."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ModificationType(Enum):
    """How a factoid should be modified."""

    SET = "set"
    REPLACE = "replace"
    APPEND = "append"


@dataclass(frozen=True)
class FactoidCreateIntent:
    """Structured intent for creating or modifying a factoid.

    Attributes:
        text: Original user message.
        key: The factoid key/topic.
        value: The factoid value/definition.
        is_plural: Whether the factoid uses 'are' (True) or 'is' (False).
        modification_type: How to modify the factoid (SET, REPLACE, APPEND).
    """

    text: str
    key: str
    value: str
    is_plural: bool
    modification_type: ModificationType


@dataclass(frozen=True)
class FactoidQueryIntent:
    """Structured intent for querying a factoid.

    Attributes:
        text: Original user message.
        key: The factoid key being queried.
        question_word: Question word used (what, where, who, etc.), if any.
        pattern: Name of the pattern that matched (e.g., 'wh_is', 'bare_question_mark').
    """

    text: str
    key: str
    question_word: str | None = None
    pattern: str | None = None
