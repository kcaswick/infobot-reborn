"""Focused tests for Discord bot command logging."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest

from infobot.config import Config
from infobot.discord.bot import InfobotBot
from infobot.logging_utils import sanitize_message_preview


class _FakeAuthor:
    """Minimal author object with stable string conversion."""

    def __str__(self) -> str:
        return "alice"


class _FakeContext:
    """Minimal command context for hybrid command callback tests."""

    def __init__(self, author: object) -> None:
        self.author = author
        self.sent_messages: list[str] = []

    async def send(self, message: str) -> None:
        """Capture command responses instead of sending them to Discord."""
        self.sent_messages.append(message)


@pytest.fixture
def bot() -> InfobotBot:
    """Build a bot instance with inert configuration for unit tests."""
    config = Config(
        discord_bot_token="token",
        llm_base_url="http://localhost:11434/v1",
        llm_model="qwen3:1.7b",
        database_path=Path("/tmp/test.db"),
        log_level="DEBUG",
    )
    return InfobotBot(config)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("command_name", "keyword", "text"),
    [
        (
            "ask_command",
            "Command from",
            "first line\nsecond line with secret token 1234567890 and more text",
        ),
        (
            "teach_command",
            "Teach command from",
            "python is   a language\twith a hidden suffix that should not appear",
        ),
    ],
)
async def test_command_debug_logging_uses_sanitized_preview(
    bot: InfobotBot,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    command_name: str,
    keyword: str,
    text: str,
) -> None:
    """Hybrid commands should log bounded previews, not raw user input."""
    ctx = _FakeContext(_FakeAuthor())
    captured: dict[str, Any] = {}

    async def fake_process_command_input(passed_ctx: object, passed_text: str) -> str:
        captured["ctx"] = passed_ctx
        captured["text"] = passed_text
        return "Processed"

    monkeypatch.setattr(bot, "_process_command_input", fake_process_command_input)

    command = getattr(bot, command_name)
    preview = sanitize_message_preview(text)
    option_name = "question" if command_name == "ask_command" else "factoid"

    with caplog.at_level(logging.DEBUG, logger="infobot.discord.bot"):
        await command.callback(bot, ctx, **{option_name: text})

    assert captured == {"ctx": ctx, "text": text}
    assert ctx.sent_messages == ["Processed"]

    matching_messages = [
        record.getMessage()
        for record in caplog.records
        if keyword in record.getMessage()
    ]
    assert matching_messages == [f"{keyword} alice: {preview}"]
    assert text not in matching_messages[0]
