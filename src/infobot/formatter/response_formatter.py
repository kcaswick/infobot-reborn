"""Format infobot responses with legacy tags and variables."""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Protocol, Sequence


_REPLY_RE = re.compile(r"<reply>(?P<content>.*?)</reply>", re.IGNORECASE | re.DOTALL)
_ACTION_RE = re.compile(r"<action>(?P<content>.*?)</action>", re.IGNORECASE | re.DOTALL)


@dataclass(frozen=True)
class FormatContext:
    """Context for formatting responses."""

    username: str
    now: datetime


class SupportsChoice(Protocol):
    """Minimal RNG protocol for selecting a random variant."""

    def choice(self, seq: Sequence[str]) -> str:
        """Pick one element from a non-empty sequence."""


def format_response(
    template: str,
    context: FormatContext,
    rng: Optional[SupportsChoice] = None,
) -> str:
    """Format a response template into a message.

    Args:
        template: Raw response template.
        context: Formatting context (user info, timestamps).
        rng: Optional random generator for deterministic selection.

    Returns:
        Formatted response string ready to send.
    """

    rng = rng or random
    selected = _select_variant(template, rng)
    mode, content = _extract_tag(selected)
    rendered = _substitute_variables(content, context).strip()

    if mode == "action":
        return f"* {rendered}".strip()

    return rendered


def _select_variant(template: str, rng: SupportsChoice) -> str:
    if "|" not in template:
        return template

    parts = [part.strip() for part in template.split("|") if part.strip()]
    if not parts:
        return template

    return rng.choice(parts)


def _extract_tag(template: str) -> tuple[Optional[str], str]:
    reply_match = _REPLY_RE.search(template)
    if reply_match:
        return "reply", reply_match.group("content").strip()

    action_match = _ACTION_RE.search(template)
    if action_match:
        return "action", action_match.group("content").strip()

    return None, template


def _substitute_variables(template: str, context: FormatContext) -> str:
    rendered = template.replace("$who", context.username)
    rendered = rendered.replace("$date", _format_datetime(context.now))
    return rendered


def _format_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")
