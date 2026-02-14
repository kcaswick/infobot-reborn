"""Tests for LLM service abstraction."""

from types import SimpleNamespace

import pytest

from infobot.services.llm_service import LlmRequest, LlmServiceError


@pytest.mark.asyncio
async def test_llm_service_returns_content(mock_llm_client) -> None:
    """Test that LLM service returns content from successful response."""
    from infobot.services.llm_service import LlmService

    service = LlmService(
        model="test-model",
        base_url="http://localhost",
        client=mock_llm_client(
            [
                SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="hello"))]
                )
            ]
        ),
    )

    response = await service.chat(
        LlmRequest(messages=[{"role": "user", "content": "Hi"}])
    )

    assert response.content == "hello"


@pytest.mark.asyncio
async def test_llm_service_raises_on_empty_content(mock_llm_client) -> None:
    """Test that LLM service raises error when response content is empty."""
    from infobot.services.llm_service import LlmService

    service = LlmService(
        model="test-model",
        base_url="http://localhost",
        client=mock_llm_client(
            [
                SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=None))]
                )
            ]
        ),
    )

    with pytest.raises(LlmServiceError):
        await service.chat(LlmRequest(messages=[{"role": "user", "content": "Hi"}]))


@pytest.mark.asyncio
async def test_llm_service_retries_on_timeout(mock_llm_client) -> None:
    """Test that LLM service retries on timeout errors."""
    from infobot.services.llm_service import LlmService

    service = LlmService(
        model="test-model",
        base_url="http://localhost",
        client=mock_llm_client(
            [
                TimeoutError("timeout"),
                SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]
                ),
            ]
        ),
        max_retries=1,
        retry_backoff_seconds=0.0,
    )

    response = await service.chat(
        LlmRequest(messages=[{"role": "user", "content": "Hi"}])
    )

    assert response.content == "ok"
