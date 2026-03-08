"""Logging utilities for building bounded log previews."""

from __future__ import annotations

import re


def sanitize_message_preview(message: str, max_len: int = 50) -> str:
    """Build a normalized, truncated preview for debug logging.

    Truncates long messages and normalizes whitespace to reduce accidental
    log exposure and prevent multiline log injection while preserving useful
    debugging context. This is not a full PII scrubber and does not
    guarantee that sensitive content is removed from the retained preview.

    Args:
        message: The message content to sanitize.
        max_len: Maximum length of the preview (default 50).

    Returns:
        Normalized, truncated message preview for debug logging.

    Examples:
        >>> sanitize_message_preview("Hello world")
        'Hello world'
        >>> sanitize_message_preview("A" * 100)
        'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA...'
        >>> sanitize_message_preview("line1\\nline2\\nline3")
        'line1 line2 line3'
    """
    # Normalize whitespace to single spaces to avoid multiline log injection.
    sanitized = re.sub(r"\s+", " ", message).strip()

    # Truncate to a bounded preview length. This reduces exposure surface but
    # does not guarantee that sensitive content is removed from the preview.
    if len(sanitized) <= max_len:
        return sanitized

    return sanitized[:max_len] + "..."
