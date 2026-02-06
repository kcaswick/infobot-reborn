"""Configuration management for Infobot Reborn.

Loads settings from environment variables with sensible defaults.
Supports .env files via python-dotenv.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    """Application configuration loaded from environment variables."""

    discord_bot_token: str
    llm_base_url: str
    llm_model: str
    database_path: Path
    log_level: str

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "Config":
        """Load configuration from environment variables.

        Args:
            env_file: Optional path to .env file. If None, searches for .env
                     in current directory and parent directories.

        Returns:
            Config instance with values from environment.

        Raises:
            ValueError: If required environment variables are missing.
        """
        # Load .env file if it exists
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()  # Auto-searches for .env

        # Required vars
        discord_token = os.getenv("DISCORD_BOT_TOKEN")
        if not discord_token:
            raise ValueError(
                "DISCORD_BOT_TOKEN environment variable is required. "
                "Get one at https://discord.com/developers/applications"
            )

        # Optional vars with defaults
        llm_base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
        llm_model = os.getenv("LLM_MODEL", "qwen3:1.7b")
        database_path = Path(os.getenv("DATABASE_PATH", "data/infobot.db"))
        log_level = os.getenv("LOG_LEVEL", "INFO").upper()

        # Validate log level
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if log_level not in valid_levels:
            raise ValueError(
                f"Invalid LOG_LEVEL: {log_level}. Must be one of {valid_levels}"
            )

        return cls(
            discord_bot_token=discord_token,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
            database_path=database_path,
            log_level=log_level,
        )
