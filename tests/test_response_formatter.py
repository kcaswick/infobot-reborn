from datetime import datetime
import random

from infobot.formatter.response_formatter import FormatContext, format_response


def test_format_response_reply_tag() -> None:
    context = FormatContext(username="alice", now=datetime(2026, 2, 6, 12, 0, 0))

    rendered = format_response("<reply>Hello $who</reply>", context)

    assert rendered == "Hello alice"


def test_format_response_action_tag() -> None:
    context = FormatContext(username="bob", now=datetime(2026, 2, 6, 12, 0, 0))

    rendered = format_response("<action>waves at $who</action>", context)

    assert rendered == "* waves at bob"


def test_format_response_pipe_selection() -> None:
    context = FormatContext(username="user", now=datetime(2026, 2, 6, 12, 0, 0))
    rng = random.Random(0)

    rendered = format_response("A|B|C", context, rng=rng)

    assert rendered == "B"


def test_format_response_date_variable() -> None:
    context = FormatContext(username="user", now=datetime(2026, 2, 6, 8, 30, 5))

    rendered = format_response("Today is $date", context)

    assert rendered == "Today is 2026-02-06 08:30:05"
