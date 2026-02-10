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
from enum import Enum

import modal


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


def authenticate(headers: dict, body: bytes) -> None:
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

    signature = headers.get("X-Signature-Ed25519")
    timestamp = headers.get("X-Signature-Timestamp")

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


@app.function(
    image=image,
    volumes={"/data": db_volume},
)
async def process_and_reply(
    content: str,
    username: str,
    app_id: str,
    interaction_token: str,
    llm_base_url: str,
    llm_model: str,
    log_level: str,
) -> None:
    """Process message through message handler and reply to Discord.

    Args:
        content: Message content to process.
        username: Username of the person who sent the interaction.
        app_id: Discord application ID.
        interaction_token: Interaction token for replying.
        llm_base_url: LLM API base URL.
        llm_model: LLM model name.
        log_level: Logging level.
    """
    # Configure logging
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Set environment variables
    os.environ["LLM_BASE_URL"] = llm_base_url
    os.environ["LLM_MODEL"] = llm_model
    os.environ["DATABASE_PATH"] = "/data/infobot.db"
    os.environ["LOG_LEVEL"] = log_level

    from infobot.config import Config
    from infobot.db import DatabaseConnection, initialize_schema
    from infobot.message_handler import MessageHandler
    from infobot.services.llm_service import LlmService

    try:
        # Initialize services
        config = Config.from_env()
        db = DatabaseConnection(config.database_path)
        await db.connect()
        await initialize_schema(db)

        llm_service = LlmService.from_config(config)
        message_handler = MessageHandler(db, llm_service)

        # Process message
        response = await message_handler.handle_message(content, username=username)

        # Send response to Discord
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
        await db.close()


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
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware

    web_app = FastAPI(title="Infobot Reborn Discord Bot")

    # CORS middleware
    web_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @web_app.post("/interactions")
    async def handle_interaction(request: Request):
        """Handle incoming Discord interactions.

        Args:
            request: FastAPI request object.

        Returns:
            JSON response for Discord.
        """
        body = await request.body()
        authenticate(dict(request.headers), body)

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

            # Get environment config
            llm_base_url = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
            llm_model = os.getenv("LLM_MODEL", "qwen3:1.7b")
            log_level = os.getenv("LOG_LEVEL", "INFO")

            # Spawn async processing (deferred response pattern)
            process_and_reply.spawn(
                content=content,
                username=username,
                app_id=app_id,
                interaction_token=interaction_token,
                llm_base_url=llm_base_url,
                llm_model=llm_model,
                log_level=log_level,
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
