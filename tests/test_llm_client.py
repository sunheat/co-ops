"""Basic tests for the LLM client."""

import pytest
from packages.llm import (
    LLMClient,
    ChatMessage,
    ChatResponse,
    ChatChoice,
    LLMResponse,
    Usage,
)
from packages.llm.errors import AuthenticationError, RateLimitError, APIError


def test_chat_message_to_dict():
    """Test ChatMessage serialization."""
    msg = ChatMessage(role="user", content="Hello")
    assert msg.to_dict() == {"role": "user", "content": "Hello"}


def test_chat_response_content_accessor():
    """Test ChatResponse.content convenience property."""
    response = ChatResponse(
        id="test-123",
        model="gpt-4",
        choices=[
            ChatChoice(
                index=0,
                message=ChatMessage(role="assistant", content="Hi there!"),
                finish_reason="stop",
            )
        ],
    )
    assert response.content == "Hi there!"
    assert response.message.role == "assistant"


def test_chat_response_empty_choices():
    """Test ChatResponse with no choices."""
    response = ChatResponse(id="test-123", model="gpt-4", choices=[])
    assert response.content == ""
    assert response.message.role == "assistant"


def test_usage_dataclass():
    """Test Usage dataclass."""
    usage = Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30)
    assert usage.prompt_tokens == 10
    assert usage.completion_tokens == 20
    assert usage.total_tokens == 30


def test_client_initialization():
    """Test LLMClient initialization."""
    client = LLMClient(api_key="test-key", base_url="https://api.example.com/v1")
    assert client.api_key == "test-key"
    assert client.base_url == "https://api.example.com/v1"
    client.close()


def test_client_context_manager():
    """Test LLMClient as context manager."""
    with LLMClient(api_key="test-key") as client:
        assert client.api_key == "test-key"


def test_client_base_url_trailing_slash():
    """Test that trailing slash is removed from base_url."""
    client = LLMClient(base_url="https://api.example.com/v1/")
    assert client.base_url == "https://api.example.com/v1"
    client.close()


def test_llm_response_from_chat_response():
    """LLMResponse flattens content, usage, and latency from a ChatResponse."""
    chat_response = ChatResponse(
        id="test-123",
        model="gpt-4o-mini",
        choices=[
            ChatChoice(
                index=0,
                message=ChatMessage(role="assistant", content="RAG is ..."),
                finish_reason="stop",
            )
        ],
        usage=Usage(prompt_tokens=12, completion_tokens=34, total_tokens=46),
        latency_ms=123.4,
        raw={"id": "test-123"},
    )
    response = LLMResponse.from_chat_response(chat_response, provider="openai")
    assert response.content == "RAG is ..."
    assert response.provider == "openai"
    assert response.model == "gpt-4o-mini"
    assert response.prompt_tokens == 12
    assert response.completion_tokens == 34
    assert response.total_tokens == 46
    assert response.latency_ms == 123.4
    assert response.raw == {"id": "test-123"}


def test_llm_response_without_usage():
    """Missing usage defaults token counts to zero."""
    chat_response = ChatResponse(id="x", model="m", choices=[])
    response = LLMResponse.from_chat_response(chat_response, provider="local")
    assert response.prompt_tokens == 0
    assert response.completion_tokens == 0
    assert response.total_tokens == 0
    assert response.latency_ms is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
