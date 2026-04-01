import random
from datetime import datetime

from infobot.formatter.response_formatter import FormatContext, format_response


def test_format_response_reply_tag() -> None:
    context = FormatContext(username="alice", now=datetime(2026, 2, 6, 12, 0, 0))

    rendered = format_response("<reply>Hello $who</reply>", context)

    assert rendered == "Hello alice"


def test_format_response_action_tag() -> None:
    context = FormatContext(username="bob", now=datetime(2026, 2, 6, 12, 0, 0))

    rendered = format_response("<action>waves at $who</action>", context)

    assert rendered == "* waves at bob"


def test_format_response_bare_reply_tag() -> None:
    """Legacy bare <reply> tags must not require a closing tag."""
    context = FormatContext(username="alice", now=datetime(2026, 2, 6, 12, 0, 0))

    rendered = format_response("<reply>Hello $who", context)

    assert rendered == "Hello alice"


def test_format_response_bare_action_tag() -> None:
    """Legacy bare <action> tags must not require a closing tag."""
    context = FormatContext(username="bob", now=datetime(2026, 2, 6, 12, 0, 0))

    rendered = format_response("<action>waves at $who", context)

    assert rendered == "* waves at bob"


def test_format_response_pipe_selection() -> None:
    context = FormatContext(username="user", now=datetime(2026, 2, 6, 12, 0, 0))
    rng = random.Random(0)

    rendered = format_response("A|B|C", context, rng=rng)

    assert rendered == "B"


def test_format_response_reply_tag_with_pipes() -> None:
    """Pipe inside <reply> tags must not corrupt tag parsing (bd-35t)."""
    context = FormatContext(username="user", now=datetime(2026, 2, 6, 12, 0, 0))
    rng = random.Random(0)

    rendered = format_response("<reply>a|b|c</reply>", context, rng=rng)

    # Content should be the literal "a|b|c" (no variant selection inside tags)
    assert rendered == "a|b|c"


def test_format_response_action_tag_with_pipes() -> None:
    """Pipe inside <action> tags must not corrupt tag parsing (bd-35t)."""
    context = FormatContext(username="user", now=datetime(2026, 2, 6, 12, 0, 0))

    rendered = format_response("<action>dances|sings</action>", context)

    assert rendered == "* dances|sings"


def test_format_response_date_variable() -> None:
    context = FormatContext(username="user", now=datetime(2026, 2, 6, 8, 30, 5))

    rendered = format_response("Today is $date", context)

    assert rendered == "Today is 2026-02-06 08:30:05"


# ---------------------------------------------------------------------------
# Prefix-tag parsing tests (bd-381)
# _extract_tag uses re.search so a tag anywhere in the string is matched;
# any text before/after the tag is discarded.
# ---------------------------------------------------------------------------


def test_format_response_reply_tag_with_prefix_text() -> None:
    """Text before a <reply> tag must be discarded; tag content is returned."""
    context = FormatContext(username="user", now=datetime(2026, 2, 6, 12, 0, 0))

    rendered = format_response("Factoid: <reply>the value</reply>", context)

    assert rendered == "the value"


def test_format_response_action_tag_with_prefix_text() -> None:
    """Text before an <action> tag must be discarded; action formatting applied."""
    context = FormatContext(username="user", now=datetime(2026, 2, 6, 12, 0, 0))

    rendered = format_response("emote: <action>waves hello</action>", context)

    assert rendered == "* waves hello"


def test_format_response_bare_reply_tag_with_prefix_text() -> None:
    """Text before a bare <reply> tag must be discarded."""
    context = FormatContext(username="user", now=datetime(2026, 2, 6, 12, 0, 0))

    rendered = format_response("Factoid: <reply>the value", context)

    assert rendered == "the value"


def test_format_response_bare_action_tag_with_prefix_text() -> None:
    """Text before a bare <action> tag must be discarded."""
    context = FormatContext(username="user", now=datetime(2026, 2, 6, 12, 0, 0))

    rendered = format_response("emote: <action>waves hello", context)

    assert rendered == "* waves hello"


def test_format_response_reply_tag_case_insensitive() -> None:
    """<REPLY> and mixed-case tags must be matched case-insensitively."""
    context = FormatContext(username="user", now=datetime(2026, 2, 6, 12, 0, 0))

    assert format_response("<REPLY>upper</REPLY>", context) == "upper"
    assert format_response("<Reply>mixed</Reply>", context) == "mixed"


def test_format_response_action_tag_case_insensitive() -> None:
    """<ACTION> and mixed-case tags must be matched case-insensitively."""
    context = FormatContext(username="user", now=datetime(2026, 2, 6, 12, 0, 0))

    assert format_response("<ACTION>stomps</ACTION>", context) == "* stomps"
    assert format_response("<Action>bows</Action>", context) == "* bows"


# ---------------------------------------------------------------------------
# Pipe-in-tag interaction tests (bd-381)
# When a tag is present, pipe-variant selection must NOT be applied — the
# content inside the tag is returned verbatim (after variable substitution).
# When no tag is present, pipes ARE used for variant selection.
# ---------------------------------------------------------------------------


def test_format_response_pipe_outside_tag_not_selected() -> None:
    """Pipes outside a <reply> tag are ignored; tag content wins."""
    context = FormatContext(username="user", now=datetime(2026, 2, 6, 12, 0, 0))
    # Even with a seeded rng, pipe-selection should not run when a tag is found.
    rng = random.Random(42)

    rendered = format_response("fallback|<reply>tagged</reply>|other", context, rng=rng)

    assert rendered == "tagged"


def test_format_response_pipe_outside_action_tag_not_selected() -> None:
    """Pipes outside an <action> tag are ignored; tag content wins."""
    context = FormatContext(username="user", now=datetime(2026, 2, 6, 12, 0, 0))
    rng = random.Random(42)

    rendered = format_response("a|b|<action>dances</action>", context, rng=rng)

    assert rendered == "* dances"


def test_format_response_bare_reply_tag_with_pipes() -> None:
    """Pipe inside a bare <reply> tag must not trigger variant selection."""
    context = FormatContext(username="user", now=datetime(2026, 2, 6, 12, 0, 0))
    rng = random.Random(0)

    rendered = format_response("<reply>a|b|c", context, rng=rng)

    assert rendered == "a|b|c"


def test_format_response_pipe_outside_bare_reply_tag_not_selected() -> None:
    """Pipes outside a bare <reply> tag are ignored; bare tag content wins."""
    context = FormatContext(username="user", now=datetime(2026, 2, 6, 12, 0, 0))
    rng = random.Random(42)

    rendered = format_response("fallback|<reply>tagged", context, rng=rng)

    assert rendered == "tagged"


def test_format_response_pipe_selection_no_tag() -> None:
    """Pipe-variant selection fires only when no tag is present."""
    context = FormatContext(username="user", now=datetime(2026, 2, 6, 12, 0, 0))
    # random.Random(0).choice(["X", "Y", "Z"]) → "Y"
    rng = random.Random(0)

    rendered = format_response("X|Y|Z", context, rng=rng)

    assert rendered in {"X", "Y", "Z"}


def test_format_response_empty_pipe_parts_skipped() -> None:
    """Empty parts produced by consecutive pipes must be filtered out."""
    context = FormatContext(username="user", now=datetime(2026, 2, 6, 12, 0, 0))
    # "A||B" splits to ["A", "", "B"]; empty string filtered → ["A", "B"]
    rng = random.Random(0)

    rendered = format_response("A||B", context, rng=rng)

    assert rendered in {"A", "B"}


def test_format_response_whitespace_pipe_parts_stripped() -> None:
    """Whitespace-only pipe parts must be filtered out."""
    context = FormatContext(username="user", now=datetime(2026, 2, 6, 12, 0, 0))
    rng = random.Random(0)

    rendered = format_response(" Hello | World ", context, rng=rng)

    assert rendered in {"Hello", "World"}


def test_format_response_no_tag_no_pipe_passthrough() -> None:
    """A plain string with no tag and no pipe is returned as-is (stripped)."""
    context = FormatContext(username="carol", now=datetime(2026, 2, 6, 12, 0, 0))

    rendered = format_response("  plain response  ", context)

    assert rendered == "plain response"
