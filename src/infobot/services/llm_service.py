"""LLM service abstraction for chat completions."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from typing import Optional, TypedDict

from openai import APIConnectionError, APIError, APITimeoutError, AsyncOpenAI, RateLimitError

from infobot.config import Config


class ChatMessage(TypedDict):
    """Typed chat message payload for OpenAI-compatible APIs."""

    role: str
    content: str


@dataclass(frozen=True)
class LlmRequest:
    """Request payload for an LLM chat completion."""

    messages: list[ChatMessage]
    temperature: float = 0.2
    max_tokens: Optional[int] = None


@dataclass(frozen=True)
class LlmResponse:
    """Simplified LLM response."""

    content: str


class LlmServiceError(RuntimeError):
    """Raised when the LLM service fails to return a valid response."""


class LlmService:
    """OpenAI-compatible LLM service abstraction."""

    def __init__(
        self,
        model: str,
        base_url: str,
        api_key: Optional[str] = None,
        client: Optional[AsyncOpenAI] = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        retry_backoff_seconds: float = 0.5,
    ) -> None:
        self._model = model
        self._max_retries = max_retries
        self._retry_backoff_seconds = retry_backoff_seconds
        self._client = client or AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or os.getenv("OPENAI_API_KEY", "ollama"),
            timeout=timeout_seconds,
        )

    @classmethod
    def from_config(cls, config: Config) -> "LlmService":
        """Create an LLM service from the application config."""

        return cls(model=config.llm_model, base_url=config.llm_base_url)

    async def chat(self, request: LlmRequest) -> LlmResponse:
        """Execute a chat completion call.

        Args:
            request: LlmRequest containing messages and parameters.

        Returns:
            LlmResponse with the generated content.

        Raises:
            LlmServiceError: If the response is missing content.
        """

        for attempt in range(self._max_retries + 1):
            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=request.messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                )
                message = response.choices[0].message if response.choices else None
                content = message.content if message else None
                if not content:
                    raise LlmServiceError("LLM response contained no message content.")
                return LlmResponse(content=content)
            except (
                APIConnectionError,
                APITimeoutError,
                RateLimitError,
                APIError,
                TimeoutError,
            ) as exc:
                if attempt >= self._max_retries:
                    raise LlmServiceError(
                        f"LLM request failed after {attempt + 1} attempts."
                    ) from exc
                backoff = self._retry_backoff_seconds * (2**attempt)
                if backoff > 0:
                    await asyncio.sleep(backoff)

        raise LlmServiceError("LLM request failed unexpectedly.")
