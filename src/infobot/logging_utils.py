"""Logging utilities for sanitizing sensitive data."""

from __future__ import annotations

import re


def sanitize_message_preview(message: str, max_len: int = 50) -> str:
    """Sanitize a message for safe debug logging.

    Truncates long messages and normalizes whitespace to prevent log
    injection and PII exposure while preserving useful debugging context.

    Args:
        message: The message content to sanitize.
        max_len: Maximum length of the preview (default 50).

    Returns:
        Sanitized message preview safe for debug logging.

    Examples:
        >>> sanitize_message_preview("Hello world")
        'Hello world'
        >>> sanitize_message_preview("A" * 100)
        'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA...'
        >>> sanitize_message_preview("line1\\nline2\\nline3")
        'line1 line2 line3'
    """
    # Normalize whitespace to single spaces (prevents log injection from newlines)
    sanitized = re.sub(r"\s+", " ", message).strip()

    # Truncate if needed
    if len(sanitized) <= max_len:
        return sanitized

    return sanitized[:max_len] + "..."
