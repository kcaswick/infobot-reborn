"""Modal.com deployment configuration for Infobot Reborn.

Deploys the Discord bot as a long-running Modal function with:
- Modal app definition and configuration
- Volume for SQLite database persistence
- Discord bot as a Modal function
- Support for both `modal serve` (dev) and `modal deploy` (prod)
"""

import logging

import modal

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Modal app definition
app = modal.App(name="infobot-reborn")

# Define a persistent volume for SQLite database
db_volume = modal.Volume.from_name("infobot-db", create_if_missing=True)

# Define the image with required dependencies
image = (
    modal.Image.debian_slim()
    .pip_install(
        "discord.py>=2.3.0",
        "aiosqlite>=0.20.0",
        "openai>=1.0.0",
        "python-dotenv>=1.0.0",
    )
    .copy_local_file("src/infobot", "/root/infobot")
    .copy_local_file("src/main.py", "/root/main.py")
    .env({"PYTHONPATH": "/root"})
)


@app.function(
    image=image,
    volumes={"/data": db_volume},
    keep_warm=1,  # Keep one instance warm for responsiveness
    timeout=86400,  # 24 hour timeout for long-running process
    allow_concurrent_calls=False,  # Only one instance needed
)
def run_discord_bot(
    discord_token: str,
    llm_base_url: str = "http://localhost:11434/v1",
    llm_model: str = "qwen3:1.7b",
    database_path: str = "/data/infobot.db",
) -> None:
    """Run the Infobot Discord bot as a Modal function.

    Args:
        discord_token: Discord bot token from environment.
        llm_base_url: LLM API base URL (can use external service).
        llm_model: LLM model name to use.
        database_path: Path to SQLite database (persisted to volume).
    """
    import asyncio
    import os

    # Set environment variables for the bot to consume
    os.environ["DISCORD_BOT_TOKEN"] = discord_token
    os.environ["LLM_BASE_URL"] = llm_base_url
    os.environ["LLM_MODEL"] = llm_model
    os.environ["DATABASE_PATH"] = database_path
    os.environ["LOG_LEVEL"] = "INFO"

    logger.info("Starting Infobot Discord bot on Modal...")
    logger.info(f"Using LLM: {llm_model} at {llm_base_url}")
    logger.info(f"Database path: {database_path}")

    # Import and run the bot
    from infobot.config import Config
    from infobot.discord import InfobotBot

    try:
        config = Config.from_env()
        bot = InfobotBot(config)
        asyncio.run(bot.run_bot())
    except KeyboardInterrupt:
        logger.info("Bot interrupted")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        raise


@app.local_entrypoint()
def main(
    discord_token: str | None = None,
    llm_base_url: str = "http://localhost:11434/v1",
    llm_model: str = "qwen3:1.7b",
) -> None:
    """Local entrypoint for running the bot.

    Args:
        discord_token: Discord bot token (can also use DISCORD_BOT_TOKEN env var).
        llm_base_url: LLM API base URL.
        llm_model: LLM model name to use.
    """
    import os

    # Use provided token or environment variable
    token = discord_token or os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise ValueError(
            "DISCORD_BOT_TOKEN not provided. "
            "Pass it as argument or set environment variable."
        )

    logger.info("Deploying Infobot to Modal...")
    run_discord_bot.remote(
        discord_token=token,
        llm_base_url=llm_base_url,
        llm_model=llm_model,
    )
