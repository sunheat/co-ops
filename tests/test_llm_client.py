"""Basic tests for the LLM client."""

import pytest

from packages.llm import (
    ChatChoice,
    ChatMessage,
    ChatResponse,
    LLMClient,
    LLMResponse,
    Usage,
    UsageTracker,
)
from packages.llm.errors import APIError


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


def test_usage_tracker_counts_calls_without_usage():
    """calls counts every recorded call, even when usage stats are missing."""
    tracker = UsageTracker()
    tracker.record(Usage(prompt_tokens=10, completion_tokens=20, total_tokens=30))
    tracker.record(None)  # e.g., local endpoint that omits usage
    tracker.record(Usage(prompt_tokens=1, completion_tokens=2, total_tokens=3))

    assert tracker.calls == 3
    assert tracker.total.prompt_tokens == 11
    assert tracker.total.completion_tokens == 22
    assert tracker.total.total_tokens == 33


def test_client_initialization():
    """Test LLMClient initialization."""
    client = LLMClient(api_key="test-key", base_url="https://api.example.com/v1")
    assert client.api_key == "test-key"
    assert client.base_url == "https://api.example.com/v1"
    client.close()


@pytest.mark.parametrize("delay", [float("nan"), float("inf"), float("-inf")])
def test_client_rejects_non_finite_retry_delay(delay):
    with pytest.raises(ValueError, match="finite number"):
        LLMClient(retry_base_delay=delay)


def test_client_context_manager():
    """Test LLMClient as context manager."""
    with LLMClient(api_key="test-key") as client:
        assert client.api_key == "test-key"


def test_client_base_url_trailing_slash():
    """Test that trailing slash is removed from base_url."""
    client = LLMClient(base_url="https://api.example.com/v1/")
    assert client.base_url == "https://api.example.com/v1"
    client.close()


def _client_with_error_response(status_code: int, json_body):
    """Build an LLMClient whose transport always returns the given error."""
    import httpx

    def handler(request):
        return httpx.Response(status_code, json=json_body)

    client = LLMClient(base_url="http://testserver/v1", max_retries=0)
    client._client = httpx.Client(
        base_url="http://testserver/v1", transport=httpx.MockTransport(handler)
    )
    return client


def test_api_error_openai_style_body():
    """OpenAI-style {"error": {"message": ...}} bodies keep working."""
    with (
        _client_with_error_response(
            500, {"error": {"message": "server exploded", "type": "server_error"}}
        ) as client,
        pytest.raises(APIError) as exc_info,
    ):
        client.chat(model="m", messages=[{"role": "user", "content": "hi"}])
    assert "server exploded" in str(exc_info.value)
    assert exc_info.value.status_code == 500


def test_api_error_string_error_body():
    """Ollama-style {"error": "..."} bodies raise APIError, not AttributeError."""
    with (
        _client_with_error_response(
            404, {"error": "model 'nope' not found, try pulling it first"}
        ) as client,
        pytest.raises(APIError) as exc_info,
    ):
        client.chat(model="nope", messages=[{"role": "user", "content": "hi"}])
    assert "model 'nope' not found" in str(exc_info.value)
    assert exc_info.value.status_code == 404
    assert exc_info.value.body == {
        "error": "model 'nope' not found, try pulling it first"
    }


def test_api_error_non_dict_body():
    """A bare-string JSON error body is normalized into APIError.body as a dict."""
    with (
        _client_with_error_response(502, "bad gateway") as client,
        pytest.raises(APIError) as exc_info,
    ):
        client.chat(model="m", messages=[{"role": "user", "content": "hi"}])
    assert "bad gateway" in str(exc_info.value)
    assert exc_info.value.body == {"error": "bad gateway"}


def test_api_error_array_body_preserved_in_raw_body():
    """Gemini-style top-level [...] error bodies survive untouched in raw_body."""
    gemini_body = [
        {"error": {"code": 404, "message": "not found", "status": "NOT_FOUND"}}
    ]
    with (
        _client_with_error_response(404, gemini_body) as client,
        pytest.raises(APIError) as exc_info,
    ):
        client.chat(model="m", messages=[{"role": "user", "content": "hi"}])
    assert exc_info.value.body == {
        "error": gemini_body
    }  # normalized for uniform handling
    assert exc_info.value.raw_body == gemini_body  # provider's shape preserved


def test_api_error_dict_body_raw_body_matches():
    """For already-dict bodies, raw_body and body are the same object."""
    body = {"error": {"message": "nope", "type": "invalid_request_error"}}
    with (
        _client_with_error_response(400, body) as client,
        pytest.raises(APIError) as exc_info,
    ):
        client.chat(model="m", messages=[{"role": "user", "content": "hi"}])
    assert exc_info.value.raw_body == exc_info.value.body == body


def test_api_error_non_json_body_text_preserved_in_raw_body():
    """HTML/plain-text error bodies (e.g. proxy 502 pages) keep their text in raw_body."""
    import httpx

    def handler(request):
        return httpx.Response(502, text="<html>502 Bad Gateway</html>")

    client = LLMClient(base_url="http://testserver/v1")
    client._client = httpx.Client(
        base_url="http://testserver/v1", transport=httpx.MockTransport(handler)
    )
    with client, pytest.raises(APIError) as exc_info:
        client.chat(model="m", messages=[{"role": "user", "content": "hi"}])
    assert "502 Bad Gateway" in str(exc_info.value)
    assert exc_info.value.body == {}  # nothing structured to normalize
    assert exc_info.value.raw_body == "<html>502 Bad Gateway</html>"


def test_rooted_request_path_preserves_base_url_path():
    """A rooted request path must not discard path segments in base_url.

    Regression guard: httpx merges base_url + "/chat/completions" by
    concatenation (unlike urljoin), so pathful base URLs like .../v1 or
    Azure's .../openai/v1 must survive in the final request URL.
    """
    cases = {
        "https://api.example.com/v1": "https://api.example.com/v1/chat/completions",
        "https://myres.openai.azure.com/openai/v1": (
            "https://myres.openai.azure.com/openai/v1/chat/completions"
        ),
        "http://localhost:11434/v1/": "http://localhost:11434/v1/chat/completions",
    }
    for base_url, expected in cases.items():
        with LLMClient(base_url=base_url) as client:
            request = client._client.build_request("POST", "/chat/completions")
            assert str(request.url) == expected


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
    assert response.estimated_cost_usd is None
    assert response.attempts == 1
    assert response.raw == {"id": "test-123"}


def test_llm_response_without_usage():
    """Missing usage defaults token counts to zero."""
    chat_response = ChatResponse(id="x", model="m", choices=[])
    response = LLMResponse.from_chat_response(chat_response, provider="local")
    assert response.prompt_tokens == 0
    assert response.completion_tokens == 0
    assert response.total_tokens == 0
    assert response.latency_ms is None


def test_default_router_lifecycle():
    """The shared router is created once, closed and reset by close_default_router()."""
    from packages.llm import client as client_module
    from packages.llm import close_default_router

    close_default_router()  # start from a clean slate; must not raise when unset
    assert client_module._default_router is None

    router = client_module._get_default_router()
    assert client_module._get_default_router() is router  # cached, single instance

    close_default_router()
    assert client_module._default_router is None
    close_default_router()  # idempotent


def test_default_router_init_is_thread_safe():
    """Concurrent first calls must all observe the same router instance."""
    import threading

    from packages.llm import client as client_module
    from packages.llm import close_default_router

    close_default_router()
    routers = []
    barrier = threading.Barrier(8)

    def grab():
        barrier.wait()
        routers.append(client_module._get_default_router())

    threads = [threading.Thread(target=grab) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(set(map(id, routers))) == 1
    close_default_router()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
