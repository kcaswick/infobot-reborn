"""Logging utilities for building bounded log previews."""

from __future__ import annotations

import re


def sanitize_message_preview(message: str, max_len: int = 50) -> str:
    """Build a bounded, injection-safe log preview string.

    Collapses whitespace and truncates to a fixed length. The sole purposes
    are preventing multiline log injection and keeping log entries concise.
    This function performs no PII detection or removal; the retained preview
    may still contain sensitive content. Do not use this for data privacy,
    PII scrubbing, or any security boundary.

    Args:
        message: The message content to preview.
        max_len: Maximum length of the preview (default 50).

    Returns:
        Whitespace-collapsed, truncated string suitable for debug logging.

    Examples:
        >>> sanitize_message_preview("Hello world")
        'Hello world'
        >>> sanitize_message_preview("A" * 100)
        'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA...'
        >>> sanitize_message_preview("line1\\nline2\\nline3")
        'line1 line2 line3'
    """
    # Collapse whitespace to prevent multiline log injection.
    sanitized = re.sub(r"\s+", " ", message).strip()

    # Truncate for log conciseness. Content is not inspected or redacted;
    # sensitive data may still appear in the retained prefix.
    if len(sanitized) <= max_len:
        return sanitized

    return sanitized[:max_len] + "..."
