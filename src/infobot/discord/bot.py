"""Discord bot implementation using discord.py."""

from __future__ import annotations

import logging
import re

import discord
from discord.ext import commands

from infobot.config import Config
from infobot.db import DatabaseConnection, initialize_schema
from infobot.message_handler import MessageHandler
from infobot.services.llm_service import LlmService

logger = logging.getLogger(__name__)


class InfobotBot(commands.Bot):
    """Infobot Discord bot using discord.py.

    Handles messages and slash commands, routing them through the message
    handler pipeline to process factoid creation/queries and return responses.
    """

    def __init__(self, config: Config) -> None:
        """Initialize the Discord bot with configuration.

        Args:
            config: Application configuration including Discord token and LLM settings.
        """
        # Initialize discord.py bot with intents
        intents = discord.Intents.default()
        intents.message_content = True  # Enable reading message content
        intents.dm_messages = True  # Enable DMs
        intents.guild_messages = True  # Enable server messages

        super().__init__(
            command_prefix=commands.when_mentioned_or("!"),
            intents=intents,
        )

        self.config = config
        self.db: DatabaseConnection | None = None
        self.message_handler: MessageHandler | None = None
        self.llm_service: LlmService | None = None

    async def setup_hook(self) -> None:
        """Initialize bot services before connecting to Discord.

        Sets up database and message handler.
        """
        try:
            # Initialize database
            self.db = DatabaseConnection(self.config.database_path)
            await self.db.connect()
            await initialize_schema(self.db)
            logger.info("Database initialized successfully")

            # Initialize LLM service
            self.llm_service = LlmService.from_config(self.config)
            logger.info("LLM service initialized")

            # Initialize message handler
            if self.db is None:
                raise RuntimeError("Database not initialized")
            self.message_handler = MessageHandler(self.db, self.llm_service)
            logger.info("Message handler initialized")

            # Sync slash commands
            synced = await self.tree.sync()
            logger.info("Synced %s slash command(s)", len(synced))

        except Exception as e:
            logger.error(f"Failed to initialize bot services: {e}")
            raise

    async def close(self) -> None:
        """Clean up resources before shutting down."""
        if self.db is not None:
            await self.db.close()
            logger.info("Database connection closed")
        await super().close()

    async def on_ready(self) -> None:
        """Called when the bot has successfully connected to Discord."""
        logger.info(f"Bot logged in as {self.user}")
        logger.info(f"Connected to {len(self.guilds)} guild(s)")

    async def on_message(self, message: discord.Message) -> None:
        """Handle regular messages from users.

        Ignores bot messages and processes user messages through the handler.

        Args:
            message: The message that was sent.
        """
        # Ignore messages from bots
        if message.author.bot:
            return

        # Ignore messages without content
        if not message.content or not message.content.strip():
            return

        ctx = await self.get_context(message)
        if ctx.command is not None:
            await self.process_commands(message)
            return

        if not self._should_respond(message):
            return

        # Log message context
        if message.guild is None:
            context_info = f"DM from {message.author}"
        else:
            context_info = f"#{message.channel.name} in {message.guild.name}"
        # Security: Do not log full message content in production - use INFO level or sanitize for DEBUG
        logger.debug(
            f"Message from {message.author} ({context_info}): {message.content}"
        )

        try:
            content = self._clean_message_content(message)
            response = await self._process_message(
                content,
                username=self._get_display_name(message.author),
            )
            if response:
                await self._send_response(message, response)
        except Exception as e:
            logger.error(
                f"Error processing message from {message.author} ({context_info}): {e}",
                exc_info=True,
            )
            await self._send_error_response(message)

    @commands.hybrid_command(name="ask")
    async def ask_command(self, ctx: commands.Context, *, question: str) -> None:
        """Slash/text command to ask the bot a question.

        Args:
            ctx: Command context.
            question: The question to ask.
        """
        if not question or not question.strip():
            await ctx.send("Please provide a question!")
            return

        logger.debug(f"Command from {ctx.author}: {question}")

        try:
            response = await self._process_command_input(ctx, question)
            if response:
                await ctx.send(response)
        except Exception as e:
            logger.error(
                f"Error processing command from {ctx.author}: {e}", exc_info=True
            )
            await ctx.send(
                "Sorry, something went wrong while processing your question."
            )

    @commands.hybrid_command(name="teach")
    async def teach_command(self, ctx: commands.Context, *, factoid: str) -> None:
        """Slash/text command to teach the bot a new factoid.

        Args:
            ctx: Command context.
            factoid: The factoid to teach (format: "key is value").
        """
        if not factoid or not factoid.strip():
            await ctx.send("Please provide a factoid (format: 'key is value')!")
            return

        logger.debug(f"Teach command from {ctx.author}: {factoid}")

        try:
            response = await self._process_command_input(ctx, factoid)
            if response:
                await ctx.send(response)
        except Exception as e:
            logger.error(
                f"Error processing teach command from {ctx.author}: {e}",
                exc_info=True,
            )
            await ctx.send("Sorry, something went wrong while saving that factoid.")

    async def _process_message(self, content: str, username: str) -> str | None:
        """Process a regular message through the message handler.

        Args:
            content: Message content to process.
            username: Username of the message author.

        Returns:
            Response string, or None if no response.
        """
        if self.message_handler is None:
            logger.error("Message handler not initialized")
            return None

        response = await self.message_handler.handle_message(
            content,
            username=username,
        )
        return response

    async def _process_command_input(
        self, ctx: commands.Context, text: str
    ) -> str | None:
        """Process command input through the message handler.

        Args:
            ctx: Command context.
            text: The command input text.

        Returns:
            Response string, or None if no response.
        """
        if self.message_handler is None:
            logger.error("Message handler not initialized")
            return None

        response = await self.message_handler.handle_message(
            text, username=self._get_display_name(ctx.author)
        )
        return response

    async def _send_response(self, message: discord.Message, response: str) -> None:
        """Send a response to a regular message.

        Respects message channel context and handles long responses.

        Args:
            message: Original message to respond to.
            response: Response text to send.
        """
        # Split response if it's too long (Discord's 2000 character limit)
        if len(response) > 2000:
            chunks = [response[i : i + 2000] for i in range(0, len(response), 2000)]
            for chunk in chunks:
                await message.reply(chunk, mention_author=False)
        else:
            await message.reply(response, mention_author=False)

        logger.debug(f"Response sent to {message.author}")

    async def _send_error_response(self, message: discord.Message) -> None:
        """Send an error response to a message.

        Args:
            message: Original message that caused the error.
        """
        error_msg = (
            "Sorry, something went wrong processing your message. Please try again."
        )
        try:
            await message.reply(error_msg, mention_author=False)
        except discord.DiscordException as e:
            logger.error(f"Failed to send error response: {e}")

    async def run_bot(self) -> None:
        """Start the bot and connect to Discord.

        Uses the Discord token from config.
        """
        await self.start(self.config.discord_bot_token)

    def _should_respond(self, message: discord.Message) -> bool:
        """Determine if the bot should respond to a message.

        Responds to DMs or messages that explicitly mention the bot.
        """
        if message.guild is None:
            return True

        if self.user is None:
            return False

        return self.user in message.mentions

    def _clean_message_content(self, message: discord.Message) -> str:
        """Remove bot mentions and trim whitespace from a message.

        Args:
            message: Discord message.

        Returns:
            Cleaned message content.
        """
        content = message.content
        if self.user is None or message.guild is None:
            return content.strip()

        mention_pattern = re.compile(rf"<@!?{self.user.id}>")
        cleaned = mention_pattern.sub("", content).strip()
        return cleaned.lstrip(" ,:;")

    @staticmethod
    def _get_display_name(author: discord.abc.User) -> str:
        """Return the best display name for a Discord user."""
        return getattr(author, "display_name", str(author))
