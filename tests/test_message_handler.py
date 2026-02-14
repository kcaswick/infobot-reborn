"""Tests for message handler orchestrator."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from infobot.db.connection import DatabaseConnection
from infobot.kb import Factoid, FactoidType
from infobot.message_handler import MessageHandler
from infobot.services.llm_service import LlmService


@pytest.mark.asyncio
async def test_message_handler_with_real_openai_client_mock(
    db_conn: DatabaseConnection,
) -> None:
    """Test factoid query with LLM enhancement using real OpenAI client.
    
    Uses actual AsyncOpenAI client with mocked HTTP transport layer to verify
    the full integration path including Pydantic validation.
    """
    from unittest.mock import patch, AsyncMock
    from infobot.kb.store import FactoidStore
    import httpx
    
    # Arrange: Create a factoid in the knowledge base
    store = FactoidStore(db_conn)
    factoid = Factoid(
        key="python",
        value="a high-level programming language",
        factoid_type=FactoidType.IS,
        source="testuser",
    )
    await store.create(factoid)
    
    # Mock the HTTP transport layer (not the OpenAI client itself)
    # This allows real AsyncOpenAI initialization and Pydantic validation
    mock_response = httpx.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 1234567890,
            "model": "gpt-3.5-turbo",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Python is a high-level programming language."
                    },
                    "finish_reason": "stop"
                }
            ]
        }
    )
    
    with patch("httpx.AsyncClient.request", new_callable=AsyncMock) as mock_request:
        mock_request.return_value = mock_response
        
        # Create LLM service with REAL AsyncOpenAI client
        llm_service = LlmService(
            model="gpt-3.5-turbo",
            base_url="http://localhost:11434/v1",
            api_key="test-key",
        )
        
        # Create message handler with LLM enhancement enabled
        handler = MessageHandler(db=db_conn, llm_service=llm_service)
        
        # Act: Query the factoid - this should trigger the bug
        response = await handler.handle_message("what is python?", username="testuser")
        
        # Assert: Should get response (test will fail before this if bug exists)
        assert "high-level programming language" in response.lower()


@pytest.mark.asyncio
async def test_message_handler_factoid_query_with_llm_enhancement(
    db_conn: DatabaseConnection,
    mock_llm_service,
) -> None:
    """Test that factoid queries can be enhanced with LLM service.
    
    This test exercises the full pipeline:
    1. Create a factoid in the knowledge base
    2. Query it with MessageHandler that has LLM service enabled
    3. LLM should enhance the response
    
    This test will FAIL with the bug where ChatMessage is constructed
    incorrectly, causing: "argument 'by_alias': 'NoneType' object cannot 
    be converted to 'PyBool'"
    """
    # Arrange: Create a factoid in the knowledge base
    from infobot.kb.store import FactoidStore
    
    store = FactoidStore(db_conn)
    factoid = Factoid(
        key="python",
        value="a high-level programming language",
        factoid_type=FactoidType.IS,
        source="testuser",
    )
    await store.create(factoid)
    
    # Create LLM service that will return an enhanced response
    llm_service = mock_llm_service(["Python is a high-level programming language known for its simplicity."])
    
    # Create message handler with LLM enhancement enabled
    handler = MessageHandler(db=db_conn, llm_service=llm_service)
    
    # Act: Query the factoid (should trigger LLM enhancement)
    response = await handler.handle_message("what is python?", username="testuser")
    
    # Assert: Should get enhanced response from LLM
    assert "Python" in response
    assert "high-level programming language" in response


@pytest.mark.asyncio
async def test_message_handler_factoid_query_without_llm(
    db_conn: DatabaseConnection,
) -> None:
    """Test that factoid queries work without LLM service."""
    # Arrange: Create a factoid
    from infobot.kb.store import FactoidStore
    
    store = FactoidStore(db_conn)
    factoid = Factoid(
        key="python",
        value="a high-level programming language",
        factoid_type=FactoidType.IS,
        source="testuser",
    )
    await store.create(factoid)
    
    # Create message handler WITHOUT LLM service
    handler = MessageHandler(db=db_conn, llm_service=None)
    
    # Act: Query the factoid
    response = await handler.handle_message("what is python?", username="testuser")
    
    # Assert: Should get basic factoid response
    assert "high-level programming language" in response


@pytest.mark.asyncio
async def test_message_handler_factoid_creation(
    db_conn: DatabaseConnection,
) -> None:
    """Test creating factoids through message handler."""
    handler = MessageHandler(db=db_conn, llm_service=None)
    
    # Act: Teach the bot a new factoid
    response = await handler.handle_message(
        "ruby is a dynamic programming language",
        username="testuser"
    )
    
    # Assert: Should confirm the factoid was saved
    assert "OK" in response or "remember" in response.lower()
    
    # Verify it was actually saved
    from infobot.kb.store import FactoidStore
    store = FactoidStore(db_conn)
    factoid = await store.get("ruby", FactoidType.IS)
    assert factoid is not None
    assert factoid.value == "a dynamic programming language"


@pytest.mark.asyncio
async def test_message_handler_unknown_factoid(
    db_conn: DatabaseConnection,
) -> None:
    """Test querying a factoid that doesn't exist."""
    handler = MessageHandler(db=db_conn, llm_service=None)
    
    # Act: Query non-existent factoid
    response = await handler.handle_message("what is cobol?", username="testuser")
    
    # Assert: Should get "don't know" response
    assert "don't know" in response.lower()
    assert "cobol" in response.lower()
