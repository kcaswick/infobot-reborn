from types import SimpleNamespace

import pytest

from infobot.services.llm_service import LlmRequest, LlmService, LlmServiceError


class _FakeChatCompletions:
    def __init__(self, responses: list[object]) -> None:
        self._responses = responses
        self.calls = 0

    async def create(self, **_kwargs: object) -> SimpleNamespace:
        response = self._responses[self.calls]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return response


class _FakeClient:
    def __init__(self, responses: list[object]) -> None:
        self.chat = SimpleNamespace(completions=_FakeChatCompletions(responses))


@pytest.mark.asyncio
async def test_llm_service_returns_content() -> None:
    service = LlmService(
        model="test-model",
        base_url="http://localhost",
        client=_FakeClient(
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
async def test_llm_service_raises_on_empty_content() -> None:
    service = LlmService(
        model="test-model",
        base_url="http://localhost",
        client=_FakeClient(
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
async def test_llm_service_retries_on_timeout() -> None:
    service = LlmService(
        model="test-model",
        base_url="http://localhost",
        client=_FakeClient(
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
