"""Shared pytest fixtures for test infrastructure."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from infobot.db.connection import DatabaseConnection
from infobot.db.schema import initialize_schema
from infobot.kb.store import FactoidStore
from infobot.services.llm_service import LlmService


@pytest.fixture
async def db_conn(tmp_path: Path) -> DatabaseConnection:
    """Provide a connected database with schema initialized.

    This fixture creates a temporary SQLite database for testing,
    initializes the schema, and ensures proper cleanup after tests.

    Args:
        tmp_path: Pytest's temporary directory fixture.

    Yields:
        DatabaseConnection: Connected database instance.
    """
    conn = DatabaseConnection(tmp_path / "test.db")
    await conn.connect()
    await initialize_schema(conn)
    yield conn
    await conn.close()


@pytest.fixture
async def db_conn_uninitialized(tmp_path: Path) -> DatabaseConnection:
    """Provide a connected database WITHOUT schema initialization.

    Useful for testing schema migration and initialization logic.

    Args:
        tmp_path: Pytest's temporary directory fixture.

    Yields:
        DatabaseConnection: Connected database instance without schema.
    """
    conn = DatabaseConnection(tmp_path / "test.db")
    await conn.connect()
    yield conn
    await conn.close()


@pytest.fixture
async def store(db_conn: DatabaseConnection) -> FactoidStore:
    """Provide a factoid store with initialized database.

    Args:
        db_conn: Database connection fixture.

    Returns:
        FactoidStore: Store instance for testing.
    """
    return FactoidStore(db_conn)


class _FakeChatCompletions:
    """Mock OpenAI-compatible chat completions for testing."""

    def __init__(self, responses: list[object]) -> None:
        self._responses = responses
        self.calls = 0

    async def create(self, **_kwargs: object) -> SimpleNamespace:
        """Mock create method that returns canned responses.

        Returns:
            SimpleNamespace: Mock response object.

        Raises:
            Exception: If response is an exception object.
        """
        response = self._responses[self.calls]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return response


class _FakeClient:
    """Mock OpenAI-compatible client for testing."""

    def __init__(self, responses: list[object]) -> None:
        self.chat = _FakeChat(responses)


class _FakeChat:
    """Mock chat namespace for OpenAI-compatible client."""

    def __init__(self, responses: list[object]) -> None:
        self.completions = _FakeChatCompletions(responses)


@pytest.fixture
def mock_llm_client():
    """Provide a factory for creating mock LLM clients.

    Returns:
        Callable: Factory function that creates _FakeClient instances.

    Example:
        def test_something(mock_llm_client):
            client = mock_llm_client([
                SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="hello"))])
            ])
            service = LlmService(model="test", base_url="http://localhost", client=client)
            response = await service.chat(...)
    """

    def _create_client(responses: list[object]) -> _FakeClient:
        return _FakeClient(responses)

    return _create_client


@pytest.fixture
def mock_llm_service(mock_llm_client):
    """Provide a factory for creating mock LLM services with canned responses.

    Returns:
        Callable: Factory function that creates LlmService instances with mock client.

    Example:
        def test_something(mock_llm_service):
            service = mock_llm_service(["response 1", "response 2"])
            result = await service.chat(...)
            assert result.content == "response 1"
    """

    def _create_service(responses: list[str]) -> LlmService:
        """Create LLM service with canned string responses.

        Args:
            responses: List of response strings to return in sequence.

        Returns:
            LlmService: Service instance with mock client.
        """
        mock_responses = [
            SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
            )
            for content in responses
        ]
        client = mock_llm_client(mock_responses)
        return LlmService(
            model="test-model",
            base_url="http://localhost",
            client=client,
        )

    return _create_service
