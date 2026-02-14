"""Message handler orchestrator for processing user messages.

Coordinates NLU detection, knowledge base operations, and response formatting.
This is the main message processing pipeline.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING

from infobot.formatter import FormatContext, format_response
from infobot.kb import Factoid, FactoidStore, FactoidType
from infobot.nlu import (
    FactoidCreateIntent,
    FactoidQueryIntent,
    ModificationType,
    detect_factoid_create_intent,
    parse_question,
)
from infobot.prompts import build_main_prompt
from infobot.services.llm_service import (
    LlmRequest,
    LlmService,
    LlmServiceError,
)

if TYPE_CHECKING:
    from infobot.db.connection import DatabaseConnection

logger = logging.getLogger(__name__)


class MessageHandler:
    """Orchestrator for processing user messages through the pipeline.

    Coordinates:
    - NLU (intent detection for factoid creation and queries)
    - Knowledge base (factoid CRUD operations)
    - Response formatting and variable substitution
    - Optional LLM enhancement of responses
    """

    def __init__(
        self,
        db: "DatabaseConnection",  # noqa: UP037
        llm_service: LlmService | None = None,
    ) -> None:
        """Initialize message handler with database and optional LLM service.

        Args:
            db: Database connection for factoid storage.
            llm_service: Optional LLM service for response enhancement.
        """
        self.db = db
        self.llm_service = llm_service
        self.store = FactoidStore(db)

    async def handle_message(
        self,
        message: str,
        username: str = "User",
    ) -> str:
        """Process a user message through the full pipeline.

        The pipeline:
        1. Try to detect a factoid creation/modification intent
        2. If found, handle it (create/update/append factoid)
        3. Otherwise, try to parse a question intent
        4. If found, retrieve and format the factoid
        5. If neither, return a default response

        Args:
            message: User's input message.
            username: Username of the person sending the message.

        Returns:
            Formatted response ready to send back to the user.
        """
        if not message or not message.strip():
            return (
                "I didn't understand that. "
                "Try asking me a question or teaching me a factoid!"
            )

        # Try factoid creation intent first
        create_intent = detect_factoid_create_intent(message)
        if create_intent is not None:
            return await self._handle_factoid_creation(create_intent, username)

        # Try factoid query intent
        query_intent = parse_question(message)
        if query_intent is not None:
            return await self._handle_factoid_query(query_intent, username)

        # No intent matched
        # Security: Do not log full message content in production - use INFO level or sanitize for DEBUG
        logger.debug(f"No intent matched for message: {message}")
        return self._format_response(
            "I don't understand. You can ask me about factoids or teach me new ones!",
            username,
        )

    async def _handle_factoid_creation(
        self,
        intent: FactoidCreateIntent,
        username: str,
    ) -> str:
        """Handle factoid creation/modification intent.

        Supports three modification types:
        - SET: Create or replace the entire factoid
        - APPEND: Add to existing factoid value
        - REPLACE: Replace existing factoid

        Args:
            intent: Parsed factoid creation intent.
            username: Username creating the factoid.

        Returns:
            Confirmation message.
        """
        try:
            factoid_type = FactoidType.ARE if intent.is_plural else FactoidType.IS
            existing = await self.store.get(intent.key, factoid_type)

            if intent.modification_type == ModificationType.APPEND and existing:
                # Append to existing factoid
                existing.value = f"{existing.value} | {intent.value}"
                existing.source = username
                await self.store.update(existing)
                logger.info(
                    f"Appended to factoid '{intent.key}' by {username}: {intent.value}"
                )
                response = (
                    f"OK, I'll remember that {intent.key} {factoid_type.value} also "
                    f"{intent.value}."
                )
                return self._format_response(response, username)

            elif intent.modification_type == ModificationType.REPLACE or (
                intent.modification_type == ModificationType.SET and existing
            ):
                # Replace existing factoid
                existing.value = intent.value
                existing.source = username
                await self.store.update(existing)
                logger.info(
                    f"Updated factoid '{intent.key}' by {username}: {intent.value}"
                )
                response = (
                    f"OK, I'll remember that {intent.key} {factoid_type.value} "
                    f"{intent.value}."
                )
                return self._format_response(response, username)

            else:
                # Create new factoid (SET or first time)
                factoid = Factoid(
                    key=intent.key,
                    value=intent.value,
                    factoid_type=factoid_type,
                    source=username,
                )
                await self.store.create(factoid)
                logger.info(
                    f"Created factoid '{intent.key}' by {username}: {intent.value}"
                )
                response = (
                    f"OK, I'll remember that {intent.key} {factoid_type.value} "
                    f"{intent.value}."
                )
                return self._format_response(response, username)

        except ValueError as e:
            logger.warning(f"Factoid creation error: {e}")
            return self._format_response(
                f"I couldn't save that factoid: {str(e)}",
                username,
            )
        except Exception as e:
            logger.error(f"Unexpected error during factoid creation: {e}")
            return self._format_response(
                "Sorry, something went wrong while saving that factoid.",
                username,
            )

    async def _handle_factoid_query(
        self,
        intent: FactoidQueryIntent,
        username: str,
    ) -> str:
        """Handle factoid query intent.

        Retrieves the factoid from knowledge base, formats it with variable
        substitution, and optionally enhances it with LLM.

        Args:
            intent: Parsed factoid query intent.
            username: Username making the query.

        Returns:
            Formatted factoid response or "I don't know" message.
        """
        try:
            factoid = await self.store.get(intent.key)

            if factoid is None:
                logger.debug(f"Factoid not found: {intent.key}")
                return self._format_response(
                    f"I don't know anything about {intent.key}.",
                    username,
                )

            # Format the factoid response with variable substitution
            formatted = self._format_response(factoid.value, username)

            # Optionally enhance with LLM if available
            if self.llm_service is not None:
                enhanced = await self._enhance_with_llm(
                    formatted,
                    intent.key,
                    username,
                )
                if enhanced is not None:
                    return enhanced

            logger.info(f"Retrieved factoid '{intent.key}' for {username}")
            return formatted

        except Exception as e:
            logger.error(f"Error retrieving factoid '{intent.key}': {e}")
            return self._format_response(
                "Sorry, I had trouble looking that up.",
                username,
            )

    async def _enhance_with_llm(
        self,
        base_response: str,
        topic: str,
        username: str,
    ) -> str | None:
        """Optionally enhance a factoid response with LLM context.

        Uses the main Infobot prompt to keep LLM responses on-brand.

        Args:
            base_response: The base formatted response from the factoid.
            topic: The factoid topic being queried.
            username: Username making the query.

        Returns:
            Enhanced response, or None if LLM service is unavailable or errors.
        """
        if self.llm_service is None:
            return None

        try:
            request = LlmRequest(
                messages=[
                    {"role": "system", "content": build_main_prompt()},
                    {
                        "role": "user",
                        "content": f"Enhance this factoid about '{topic}': {base_response}",
                    },
                ],
                temperature=0.7,
                max_tokens=150,
            )

            response = await self.llm_service.chat(request)
            logger.debug(f"LLM enhancement successful for topic '{topic}'")
            return response.content

        except LlmServiceError as e:
            logger.warning(f"LLM enhancement failed for topic '{topic}': {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during LLM enhancement: {e}")
            return None

    def _format_response(self, template: str, username: str) -> str:
        """Format response using the standard formatter.

        Applies variable substitution and tag processing.

        Args:
            template: Response template (may contain $who, $date, <reply>, <action>).
            username: Username for variable substitution.

        Returns:
            Formatted response ready to send.
        """
        context = FormatContext(username=username, now=datetime.now())
        return format_response(template, context)
