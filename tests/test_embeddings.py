"""Tests for the OpenAI-compatible embedding client."""

import json

import httpx
import pytest

from packages.llm import EmbeddingClient, UsageLogger, embedding_client_from_env
from packages.llm.errors import AuthenticationError, ConfigError, InvalidResponseError


def _success_response(count: int = 2, dimension: int = 3) -> dict:
    return {
        "object": "list",
        "model": "text-embedding-3-small",
        "data": [
            {
                "object": "embedding",
                "index": index,
                "embedding": [float(index + 1)] * dimension,
            }
            for index in range(count)
        ],
        "usage": {"prompt_tokens": 7, "total_tokens": 7},
    }


def _replace_transport(client: EmbeddingClient, handler) -> None:
    client._client.close()
    client._client = httpx.Client(
        base_url=client.base_url,
        transport=httpx.MockTransport(handler),
        timeout=client.timeout,
    )


def test_embed_returns_vectors_usage_and_dimension():
    """A successful embed() returns vectors, usage, and the vector dimension."""
    with EmbeddingClient(base_url="http://testserver/v1", provider="openai") as client:
        _replace_transport(
            client, lambda request: httpx.Response(200, json=_success_response())
        )
        response = client.embed(
            ["first text", "second text"], model="text-embedding-3-small"
        )

    assert response.embeddings == [[1.0, 1.0, 1.0], [2.0, 2.0, 2.0]]
    assert response.dimension == 3
    assert response.model == "text-embedding-3-small"
    assert response.usage is not None
    assert response.usage.total_tokens == 7
    assert response.latency_ms is not None
    assert response.attempts == 1


def test_embed_serializes_single_text_and_list_inputs():
    """A single string and a list are both sent as an input array."""
    observed_payloads = []

    def handler(request):
        payload = json.loads(request.content)
        observed_payloads.append(payload)
        return httpx.Response(200, json=_success_response(count=len(payload["input"])))

    with EmbeddingClient(base_url="http://testserver/v1") as client:
        _replace_transport(client, handler)
        client.embed("one text", model="text-embedding-3-small")
        client.embed(["a", "b"], model="text-embedding-3-small")

    assert observed_payloads[0]["input"] == ["one text"]
    assert observed_payloads[1]["input"] == ["a", "b"]
    assert observed_payloads[0]["model"] == "text-embedding-3-small"


def test_embed_rejects_empty_input():
    """An empty input list fails before any HTTP request is made."""
    with (
        EmbeddingClient(base_url="http://testserver/v1") as client,
        pytest.raises(ValueError, match="at least one string"),
    ):
        client.embed([], model="text-embedding-3-small")


def test_embed_retries_transient_5xx_then_logs_one_success(tmp_path):
    """A transient 5xx is retried and one success record is written."""
    calls = 0
    log_path = tmp_path / "usage.jsonl"

    def handler(request):
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(503, json={"error": {"message": "try later"}})
        return httpx.Response(200, json=_success_response(count=1))

    with EmbeddingClient(
        base_url="http://testserver/v1",
        provider="openai",
        max_retries=2,
        retry_base_delay=0,
        usage_logger=UsageLogger(log_path),
    ) as client:
        _replace_transport(client, handler)
        response = client.embed("hello", model="text-embedding-3-small")

    assert calls == 3
    assert response.attempts == 3

    records = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert len(records) == 1
    assert records[0]["status"] == "success"
    assert records[0]["attempts"] == 3
    assert records[0]["prompt_tokens"] == 7


def test_embed_raises_auth_error_without_retry_and_logs_failure(tmp_path):
    """A 401 raises AuthenticationError immediately and logs one failure."""
    calls = 0
    log_path = tmp_path / "usage.jsonl"

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    with EmbeddingClient(
        base_url="http://testserver/v1",
        provider="openai",
        max_retries=2,
        retry_base_delay=0,
        usage_logger=UsageLogger(log_path),
    ) as client:
        _replace_transport(client, handler)
        with pytest.raises(AuthenticationError):
            client.embed("hello", model="text-embedding-3-small")

    assert calls == 1

    records = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert len(records) == 1
    assert records[0]["status"] == "error"
    assert records[0]["error_type"] == "AuthenticationError"


def test_embed_rejects_response_without_embedding_data():
    """A 200 response without data raises InvalidResponseError."""

    with EmbeddingClient(base_url="http://testserver/v1") as client:
        _replace_transport(client, lambda request: httpx.Response(200, json={}))
        with pytest.raises(InvalidResponseError, match="without embedding data"):
            client.embed("hello", model="text-embedding-3-small")


def test_embed_rejects_mismatched_embedding_count():
    """Fewer vectors than inputs raises InvalidResponseError."""

    def handler(request):
        return httpx.Response(200, json=_success_response(count=1))

    with EmbeddingClient(base_url="http://testserver/v1") as client:
        _replace_transport(client, handler)
        with pytest.raises(InvalidResponseError, match="1 embeddings for 2 inputs"):
            client.embed(["a", "b"], model="text-embedding-3-small")


def test_embed_aligns_vectors_with_input_order_using_index():
    """Out-of-order provider items are reordered by their index values."""

    def handler(request):
        response = _success_response(count=2)
        response["data"] = list(reversed(response["data"]))
        return httpx.Response(200, json=response)

    with EmbeddingClient(base_url="http://testserver/v1") as client:
        _replace_transport(client, handler)
        response = client.embed(["first", "second"], model="text-embedding-3-small")

    assert response.embeddings == [[1.0, 1.0, 1.0], [2.0, 2.0, 2.0]]


@pytest.mark.parametrize(
    "indexes",
    [
        [0, 0],
        [-1, 0],
        [0, 2],
        [0, "1"],
        [False, 1],
    ],
)
def test_embed_rejects_invalid_embedding_indexes(indexes):
    """Duplicate, invalid, and out-of-range indexes are rejected."""

    def handler(request):
        response = _success_response()
        for item, index in zip(response["data"], indexes):
            item["index"] = index
        return httpx.Response(200, json=response)

    with EmbeddingClient(base_url="http://testserver/v1") as client:
        _replace_transport(client, handler)
        with pytest.raises(InvalidResponseError, match="invalid embedding indexes"):
            client.embed(["first", "second"], model="text-embedding-3-small")


def test_embed_rejects_missing_embedding_index():
    """An embedding response must include an index for every vector."""

    def handler(request):
        response = _success_response()
        del response["data"][1]["index"]
        return httpx.Response(200, json=response)

    with EmbeddingClient(base_url="http://testserver/v1") as client:
        _replace_transport(client, handler)
        with pytest.raises(InvalidResponseError, match="invalid embedding indexes"):
            client.embed(["first", "second"], model="text-embedding-3-small")


def test_embed_tolerates_non_dict_usage():
    """A non-object usage field is ignored instead of raising."""

    def handler(request):
        response = _success_response(count=1)
        response["usage"] = "not-a-dict"
        return httpx.Response(200, json=response)

    with EmbeddingClient(base_url="http://testserver/v1") as client:
        _replace_transport(client, handler)
        response = client.embed("hello", model="text-embedding-3-small")

    assert response.usage is None


def test_embedding_client_from_env_resolves_provider_and_default_model():
    """EMBEDDING_PROVIDER selects the provider and its default model."""
    client, model = embedding_client_from_env(
        {
            "EMBEDDING_PROVIDER": "openai",
            "OPENAI_API_KEY": "test-key",
        }
    )
    with client:
        assert client.provider == "openai"
        assert client.base_url == "https://api.openai.com/v1"
        assert client.api_key == "test-key"
    assert model == "text-embedding-3-small"


def test_embedding_client_from_env_falls_back_to_llm_provider():
    """Without EMBEDDING_PROVIDER, LLM_PROVIDER is used."""
    client, model = embedding_client_from_env(
        {
            "LLM_PROVIDER": "local",
            "LOCAL_LLM_BASE_URL": "http://localhost:11434/v1",
        }
    )
    with client:
        assert client.provider == "local"
        assert client.base_url == "http://localhost:11434/v1"
    assert model == "nomic-embed-text"


def test_embedding_client_from_env_requires_model_for_unknown_default():
    """A provider without a default model needs an explicit EMBEDDING_MODEL."""
    with pytest.raises(ConfigError, match="No default embedding model"):
        embedding_client_from_env(
            {
                "EMBEDDING_PROVIDER": "openrouter",
                "OPENROUTER_API_KEY": "test-key",
            }
        )


def test_embedding_client_from_env_rejects_unconfigured_provider():
    """A provider that lacks credentials is rejected with a clear error."""
    with pytest.raises(ConfigError, match="not configured"):
        embedding_client_from_env({"EMBEDDING_PROVIDER": "gemini"})
