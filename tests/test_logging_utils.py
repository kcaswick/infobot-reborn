"""Tests for logging utility functions."""

from __future__ import annotations

from infobot.logging_utils import sanitize_message_preview


class TestSanitizeMessagePreview:
    """Tests for sanitize_message_preview function."""

    def test_short_message_unchanged(self) -> None:
        """Short messages should pass through unchanged."""
        assert sanitize_message_preview("Hello world") == "Hello world"

    def test_exact_max_length_unchanged(self) -> None:
        """Messages at exactly max_len should not be truncated."""
        msg = "A" * 50
        assert sanitize_message_preview(msg) == msg

    def test_long_message_truncated(self) -> None:
        """Long messages should be truncated with ellipsis."""
        msg = "A" * 100
        result = sanitize_message_preview(msg)
        assert result == "A" * 50 + "..."
        assert len(result) == 53

    def test_custom_max_len(self) -> None:
        """Custom max_len should be respected."""
        msg = "Hello world"
        result = sanitize_message_preview(msg, max_len=5)
        assert result == "Hello..."

    def test_newline_normalization(self) -> None:
        """Newlines should be replaced with spaces."""
        msg = "line1\nline2\nline3"
        result = sanitize_message_preview(msg)
        assert result == "line1 line2 line3"

    def test_multiple_whitespace_normalized(self) -> None:
        """Multiple spaces/tabs should become single spaces."""
        msg = "hello   world\t\ttest"
        result = sanitize_message_preview(msg)
        assert result == "hello world test"

    def test_leading_trailing_whitespace_stripped(self) -> None:
        """Leading/trailing whitespace should be stripped."""
        msg = "  hello world  "
        result = sanitize_message_preview(msg)
        assert result == "hello world"

    def test_empty_message(self) -> None:
        """Empty message should return empty string."""
        assert sanitize_message_preview("") == ""

    def test_whitespace_only_message(self) -> None:
        """Whitespace-only message should return empty string."""
        assert sanitize_message_preview("   \n\t  ") == ""

    def test_real_world_factoid_query(self) -> None:
        """Test with realistic factoid query."""
        msg = "What is the meaning of life?"
        result = sanitize_message_preview(msg, max_len=30)
        assert result == "What is the meaning of life?"

    def test_long_factoid_teach(self) -> None:
        """Test with realistic long teach command."""
        msg = (
            "Python is a programming language created by "
            "Guido van Rossum and first released in 1991"
        )
        result = sanitize_message_preview(msg, max_len=40)
        assert result == "Python is a programming language created..."
        assert result.endswith("...")
