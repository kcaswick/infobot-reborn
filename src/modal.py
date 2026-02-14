"""Modal.com deployment configuration for Infobot Reborn.

Deploys the Discord bot using Discord Interactions API (HTTP webhooks) with:
- FastAPI endpoint for receiving Discord interactions
- Ed25519 signature verification for security
- Deferred responses for longer processing
- Modal app with persistent volume for SQLite database
- Slash command registration
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import Request

import modal

if TYPE_CHECKING:
    from infobot.services.llm_service import LlmService


# Discord Interactions API protocol types
class DiscordInteractionType(Enum):
    """Discord interaction types."""

    PING = 1
    APPLICATION_COMMAND = 2
    MESSAGE_COMPONENT = 3
    APPLICATION_COMMAND_AUTOCOMPLETE = 4
    MODAL_SUBMIT = 5


class DiscordResponseType(Enum):
    """Discord interaction response types."""

    PONG = 1
    CHANNEL_MESSAGE_WITH_SOURCE = 4
    DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE = 5
    DEFERRED_UPDATE_MESSAGE = 6
    UPDATE_MESSAGE = 7


# Modal app definition
app = modal.App(name="infobot-reborn")

# Persistent volume for SQLite database
db_volume = modal.Volume.from_name("infobot-db", create_if_missing=True)

# Image with dependencies from pyproject.toml
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_pyproject(
        pyproject_toml="pyproject.toml",
        # Only install production dependencies, not dev group
        optional_dependencies=[],
    )
    .copy_local_dir("src/infobot", "/root/infobot")
)

# Discord secrets (configure in Modal dashboard)
discord_secret = modal.Secret.from_name(
    "discord-secret",
    required_keys=[
        "DISCORD_BOT_TOKEN",
        "DISCORD_CLIENT_ID",
        "DISCORD_PUBLIC_KEY",
    ],
)

APP_CONFIG_PREFIX = "APP_CONFIG_"
DEFAULT_LLM_BASE_URL = "http://localhost:11434/v1"
DEFAULT_LLM_MODEL = "qwen3:1.7b"
DEFAULT_LOG_LEVEL = "INFO"


@dataclass(frozen=True)
class RuntimeConfig:
    """Runtime settings passed into message processing jobs."""

    llm_base_url: str
    llm_model: str
    log_level: str


def _resolve_config_value(key: str, default: str, env: Mapping[str, str]) -> str:
    """Resolve a config value with secret-first precedence.

    Precedence:
    1) APP_CONFIG_{key} (secret-friendly namespace)
    2) {key} (legacy env variable)
    3) default
    """
    secret_key = f"{APP_CONFIG_PREFIX}{key}"

    secret_value = env.get(secret_key)
    if secret_value and secret_value.strip():
        return secret_value.strip()

    env_value = env.get(key)
    if env_value and env_value.strip():
        return env_value.strip()

    return default


def resolve_runtime_config(env: Mapping[str, str] | None = None) -> RuntimeConfig:
    """Resolve runtime config for Modal interactions with deterministic precedence."""
    runtime_env = os.environ if env is None else env

    llm_base_url = _resolve_config_value(
        "LLM_BASE_URL",
        DEFAULT_LLM_BASE_URL,
        runtime_env,
    )
    llm_model = _resolve_config_value("LLM_MODEL", DEFAULT_LLM_MODEL, runtime_env)
    log_level = _resolve_config_value(
        "LOG_LEVEL",
        DEFAULT_LOG_LEVEL,
        runtime_env,
    ).upper()
    if not hasattr(logging, log_level):
        log_level = DEFAULT_LOG_LEVEL

    return RuntimeConfig(
        llm_base_url=llm_base_url,
        llm_model=llm_model,
        log_level=log_level,
    )


def _configure_logging(log_level: str) -> None:
    """Apply process logging configuration for worker execution."""
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def _build_llm_service(llm_base_url: str, llm_model: str) -> LlmService:
    """Construct an LLM service instance for a specific runtime config."""
    from infobot.services.llm_service import LlmService

    return LlmService(model=llm_model, base_url=llm_base_url)


class RuntimeServiceCache:
    """Container-scoped cache for reusable runtime services.

    This cache is intentionally limited to stateless or safely reusable objects.
    Request-scoped DB handles remain per-request.
    """

    def __init__(
        self,
        llm_factory: Callable[[str, str], LlmService] | None = None,
    ) -> None:
        self._llm_factory = llm_factory or _build_llm_service
        self._llm_services: dict[tuple[str, str], LlmService] = {}

    def get_llm_service(self, llm_base_url: str, llm_model: str) -> LlmService:
        """Get or create a cached LLM service for a runtime tuple."""
        key = (llm_base_url, llm_model)
        service = self._llm_services.get(key)
        if service is None:
            service = self._llm_factory(llm_base_url, llm_model)
            self._llm_services[key] = service
        return service


def authenticate(headers: Mapping[str, str], body: bytes) -> None:
    """Verify Discord request signature using Ed25519.

    Args:
        headers: HTTP request headers.
        body: Raw request body bytes.

    Raises:
        HTTPException: If signature verification fails.
    """
    from fastapi.exceptions import HTTPException
    from nacl.exceptions import BadSignatureError
    from nacl.signing import VerifyKey

    public_key = os.getenv("DISCORD_PUBLIC_KEY")
    if not public_key:
        raise HTTPException(status_code=500, detail="DISCORD_PUBLIC_KEY not configured")

    verify_key = VerifyKey(bytes.fromhex(public_key))

    normalized_headers = {key.lower(): value for key, value in headers.items()}
    signature = normalized_headers.get("x-signature-ed25519")
    timestamp = normalized_headers.get("x-signature-timestamp")

    if not signature or not timestamp:
        raise HTTPException(status_code=401, detail="Missing signature headers")

    message = timestamp.encode() + body

    try:
        verify_key.verify(message, bytes.fromhex(signature))
    except BadSignatureError:
        raise HTTPException(status_code=401, detail="Invalid request signature")


async def send_to_discord(payload: dict, app_id: str, interaction_token: str) -> None:
    """Send response to Discord via interaction webhook.

    Args:
        payload: JSON payload to send.
        app_id: Discord application ID.
        interaction_token: Interaction token from Discord.
    """
    import aiohttp

    interaction_url = (
        f"https://discord.com/api/v10/webhooks/{app_id}/{interaction_token}"
        "/messages/@original"
    )

    async with aiohttp.ClientSession() as session:
        async with session.patch(interaction_url, json=payload) as resp:
            if resp.status >= 400:
                logging.error(f"Discord API error: {await resp.text()}")
            else:
                logging.debug(f"Discord response: {resp.status}")


@app.cls(
    image=image,
    volumes={"/data": db_volume},
    secrets=[discord_secret],
)
class ModalInteractionWorker:
    """Container-scoped worker for deferred Discord interaction processing."""

    def __init__(self) -> None:
        self._services = RuntimeServiceCache()
        self._pre_snapshot_config: RuntimeConfig | None = None

    @modal.enter()
    def initialize_container(self) -> None:
        """Prepare reusable state before request work begins.

        Pre-snapshot responsibilities:
        - resolve runtime config
        - configure logging
        - instantiate a baseline LLM service so snapshots can capture warm state

        Post-snapshot/per-request responsibilities:
        - open DB connection
        - initialize schema
        - construct request-scoped MessageHandler
        """
        self._pre_snapshot_config = resolve_runtime_config()
        _configure_logging(self._pre_snapshot_config.log_level)
        self._services.get_llm_service(
            self._pre_snapshot_config.llm_base_url,
            self._pre_snapshot_config.llm_model,
        )

    @modal.method()
    async def process_and_reply(
        self,
        content: str,
        username: str,
        app_id: str,
        interaction_token: str,
        llm_base_url: str,
        llm_model: str,
        log_level: str,
    ) -> None:
        """Process message through message handler and reply to Discord."""
        _configure_logging(log_level)

        # Preserve existing env-based expectations used by core modules.
        os.environ["LLM_BASE_URL"] = llm_base_url
        os.environ["LLM_MODEL"] = llm_model
        os.environ["DATABASE_PATH"] = "/data/infobot.db"
        os.environ["LOG_LEVEL"] = log_level

        from infobot.db import DatabaseConnection, initialize_schema
        from infobot.message_handler import MessageHandler

        db: DatabaseConnection | None = None

        try:
            db_path = Path(os.getenv("DATABASE_PATH", "/data/infobot.db"))
            db = DatabaseConnection(db_path)
            await db.connect()
            await initialize_schema(db)

            llm_service = self._services.get_llm_service(llm_base_url, llm_model)
            message_handler = MessageHandler(db, llm_service)
            response = await message_handler.handle_message(content, username=username)

            if response:
                await send_to_discord({"content": response}, app_id, interaction_token)
            else:
                await send_to_discord(
                    {"content": "I couldn't process that request."},
                    app_id,
                    interaction_token,
                )

        except Exception as e:
            logging.error(f"Error processing message: {e}", exc_info=True)
            await send_to_discord(
                {"content": "Sorry, something went wrong processing your request."},
                app_id,
                interaction_token,
            )
        finally:
            if db is not None:
                await db.close()


modal_worker = ModalInteractionWorker()


@app.function(
    secrets=[discord_secret],
    min_containers=1,  # Keep warm for fast responses (Discord 3-second timeout)
)
@modal.asgi_app()
def web_app():
    """FastAPI web application for handling Discord interactions.

    Returns:
        FastAPI app configured for Discord webhooks.
    """
    from fastapi import FastAPI, HTTPException

    web_app = FastAPI(title="Infobot Reborn Discord Bot")

    @web_app.post("/interactions")
    async def handle_interaction(request: Request):
        """Handle incoming Discord interactions.

        Args:
            request: FastAPI request object.

        Returns:
            JSON response for Discord.
        """
        body = await request.body()
        authenticate(request.headers, body)

        data = json.loads(body.decode())
        interaction_type = data.get("type")

        # Handle PING (Discord verification)
        if interaction_type == DiscordInteractionType.PING.value:
            logging.info("Received PING from Discord")
            return {"type": DiscordResponseType.PONG.value}

        # Handle slash commands
        if interaction_type == DiscordInteractionType.APPLICATION_COMMAND.value:
            command_name = data.get("data", {}).get("name")
            logging.info(f"Received command: {command_name}")

            # Get command parameters
            options = data.get("data", {}).get("options", [])
            content = None
            if options:
                content = options[0].get("value")

            if not content:
                return {
                    "type": DiscordResponseType.CHANNEL_MESSAGE_WITH_SOURCE.value,
                    "data": {"content": "Please provide input for this command."},
                }

            # Get user info
            username = (
                data.get("member", {}).get("user", {}).get("username")
                or data.get("user", {}).get("username")
                or "unknown"
            )

            app_id = data["application_id"]
            interaction_token = data["token"]

            runtime_config = resolve_runtime_config()

            # Spawn async processing (deferred response pattern)
            modal_worker.process_and_reply.spawn(
                content=content,
                username=username,
                app_id=app_id,
                interaction_token=interaction_token,
                llm_base_url=runtime_config.llm_base_url,
                llm_model=runtime_config.llm_model,
                log_level=runtime_config.log_level,
            )

            # Return deferred response immediately
            return {
                "type": DiscordResponseType.DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE.value
            }

        logging.warning(f"Unhandled interaction type: {interaction_type}")
        raise HTTPException(status_code=400, detail="Unsupported interaction type")

    return web_app


@app.function(secrets=[discord_secret], image=image)
def register_commands(force: bool = False):
    """Register slash commands with Discord API.

    Args:
        force: If True, recreate commands even if they exist.
    """
    import requests

    bot_token = os.getenv("DISCORD_BOT_TOKEN")
    client_id = os.getenv("DISCORD_CLIENT_ID")

    if not bot_token or not client_id:
        raise ValueError("DISCORD_BOT_TOKEN and DISCORD_CLIENT_ID must be configured")

    # Security: Never log this headers dict - contains bot token
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bot {bot_token}",
    }

    url = f"https://discord.com/api/v10/applications/{client_id}/commands"

    # Define slash commands
    commands = [
        {
            "name": "ask",
            "description": "Ask the bot a question",
            "options": [
                {
                    "name": "question",
                    "description": "Your question",
                    "type": 3,  # STRING type
                    "required": True,
                }
            ],
        },
        {
            "name": "teach",
            "description": "Teach the bot a new factoid",
            "options": [
                {
                    "name": "factoid",
                    "description": "The factoid to teach (format: 'key is value')",
                    "type": 3,  # STRING type
                    "required": True,
                }
            ],
        },
    ]

    # Get existing commands
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    existing_commands = response.json()

    # Register each command
    for command in commands:
        exists = any(cmd.get("name") == command["name"] for cmd in existing_commands)

        if exists and not force:
            print(f"✓ Command '{command['name']}' already exists")
            continue

        # Create or update command
        if exists:
            # Find and update existing command
            existing_id = next(
                cmd["id"] for cmd in existing_commands if cmd["name"] == command["name"]
            )
            update_url = f"{url}/{existing_id}"
            response = requests.patch(
                update_url, headers=headers, json=command, timeout=10
            )
        else:
            response = requests.post(url, headers=headers, json=command, timeout=10)

        response.raise_for_status()
        print(f"✓ Command '{command['name']}' registered")

    print("\n✓ All commands registered successfully!")


@app.local_entrypoint()
def main():
    """Local entrypoint for deploying the bot."""
    print("Infobot Reborn - Modal Deployment")
    print("=" * 50)
    print("\nRegistering slash commands with Discord...")
    register_commands.remote()
    print("\n✓ Bot is ready!")
    print(f"\nWebhook URL: {web_app.web_url}/interactions")
    print("\nConfigure this URL in Discord Developer Portal:")
    print("  1. Go to https://discord.com/developers/applications")
    print("  2. Select your application")
    print("  3. Go to 'General Information' -> 'Interactions Endpoint URL'")
    print(f"  4. Set it to: {web_app.web_url}/interactions")
    print("\n" + "=" * 50)
