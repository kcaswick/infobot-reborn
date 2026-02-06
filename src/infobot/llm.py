"""LLM service abstraction using OpenAI-compatible API.

Works with vLLM, ollama, or any OpenAI-compatible endpoint.
"""

import logging
from collections.abc import AsyncIterator

from openai import AsyncOpenAI, OpenAIError

from infobot.config import Config

logger = logging.getLogger(__name__)


class LLMService:
    """LLM service using OpenAI-compatible API."""

    def __init__(self, config: Config):
        """Initialize LLM service.

        Args:
            config: Application configuration with LLM settings.
        """
        self.config = config
        self.client = AsyncOpenAI(
            base_url=config.llm_base_url,
            api_key="not-needed",  # Local inference doesn't need real API key
        )
        logger.info(
            f"LLM service initialized: {config.llm_base_url} / {config.llm_model}"
        )

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> str:
        """Generate a chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            temperature: Sampling temperature (0.0 to 2.0).
            max_tokens: Maximum tokens to generate.

        Returns:
            Generated response text.

        Raises:
            OpenAIError: If the API call fails.
        """
        try:
            response = await self.client.chat.completions.create(
                model=self.config.llm_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            if content is None:
                logger.warning("LLM returned None content, using empty string")
                return ""
            return content
        except OpenAIError as e:
            logger.error(f"LLM API error: {e}")
            raise

    async def chat_completion_stream(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> AsyncIterator[str]:
        """Generate a streaming chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            temperature: Sampling temperature (0.0 to 2.0).
            max_tokens: Maximum tokens to generate.

        Yields:
            Generated response text chunks.

        Raises:
            OpenAIError: If the API call fails.
        """
        try:
            stream = await self.client.chat.completions.create(
                model=self.config.llm_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except OpenAIError as e:
            logger.error(f"LLM streaming error: {e}")
            raise
