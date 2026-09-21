"""OpenAI-compatible embedding client, kept separate from the chat client.

Embeddings use a different endpoint (``/embeddings``), request shape, and
response contract than chat completions, so they get their own client instead
of overloading ``LLMClient``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from math import isfinite
from typing import Self

import httpx

from ._http import post_json_with_retries
from .config import load_settings
from .errors import (
    ConfigError,
    InvalidResponseError,
    LLMError,
)
from .usage import (
    Usage,
    UsageLogEntry,
    UsageLogger,
    append_usage_entry,
    estimate_cost_usd,
)

DEFAULT_EMBEDDING_MODELS: dict[str, str] = {
    "openai": "text-embedding-3-small",
    "gemini": "gemini-embedding-001",
    "local": "nomic-embed-text",  # Ollama default; other local servers vary
}


@dataclass
class EmbeddingResponse:
    """Vectors returned by the provider for one request."""

    embeddings: list[list[float]]
    model: str = ""
    usage: Usage | None = None
    latency_ms: float | None = None
    attempts: int = 1
    raw: dict = field(default_factory=dict)

    @property
    def dimension(self) -> int:
        """Vector size reported by the provider (0 when no vectors)."""
        return len(self.embeddings[0]) if self.embeddings else 0


class EmbeddingClient:
    """
    A synchronous client for the OpenAI-compatible ``/embeddings`` endpoint.

    Works with any OpenAI-compatible embedding provider:
    - OpenAI: base_url="https://api.openai.com/v1"
    - Azure OpenAI: base_url="https://<resource>.openai.azure.com/openai/v1"
      (v1 API: the deployment name goes in the model field)
    - Gemini: base_url="https://generativelanguage.googleapis.com/v1beta/openai"
    - Ollama: base_url="http://localhost:11434/v1"

    Example:
        client = EmbeddingClient(api_key="sk-...", base_url="https://api.openai.com/v1")
        response = client.embed("Hello world", model="text-embedding-3-small")
        print(response.dimension, response.embeddings[0][:3])
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
        provider: str = "unknown",
        max_retries: int = 2,
        retry_base_delay: float = 0.5,
        usage_logger: UsageLogger | None = None,
    ):
        """
        Initialize the embedding client.

        Args:
            api_key: API key for authentication. Can be None for local endpoints.
            base_url: Base URL of the OpenAI-compatible API.
            timeout: Request timeout in seconds.
            provider: Provider name written to usage logs and used for pricing.
            max_retries: Retries after the first attempt for transient failures.
            retry_base_delay: Initial exponential-backoff delay in seconds.
            usage_logger: Optional JSONL logger for completed calls.
        """
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        if max_retries < 0:
            raise ValueError("max_retries must be zero or greater")
        if not isfinite(retry_base_delay) or retry_base_delay < 0:
            raise ValueError(
                "retry_base_delay must be a finite number that is zero or greater"
            )

        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.provider = provider.lower()
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.usage_logger = usage_logger

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout,
        )

    def embed(
        self,
        texts: str | Sequence[str],
        model: str,
    ) -> EmbeddingResponse:
        """
        Embed one text or a batch of texts.

        Args:
            texts: A single string or a list of strings to embed.
            model: Embedding model name (Azure: the embedding deployment name).

        Returns:
            EmbeddingResponse with one vector per input text, in input order.
        """
        inputs = [texts] if isinstance(texts, str) else list(texts)
        if not inputs:
            raise ValueError("texts must contain at least one string")

        payload = {"model": model, "input": inputs}

        data, latency_ms, attempts = post_json_with_retries(
            self._client,
            "/embeddings",
            payload,
            timeout=self.timeout,
            max_retries=self.max_retries,
            retry_base_delay=self.retry_base_delay,
            on_failure=lambda error, latency_ms: self._record_failure(
                model=model,
                error=error,
                latency_ms=latency_ms,
            ),
        )
        try:
            parsed = self._parse_response(
                data,
                latency_ms=latency_ms,
                attempts=attempts,
            )
            if len(parsed.embeddings) != len(inputs):
                raise InvalidResponseError(
                    f"Provider returned {len(parsed.embeddings)} embeddings "
                    f"for {len(inputs)} inputs",
                    attempts=attempts,
                )
        except InvalidResponseError as parse_error:
            self._record_failure(
                model=model,
                error=parse_error,
                latency_ms=latency_ms,
            )
            raise

        if not parsed.model:
            parsed.model = model
        self._record_success(parsed)
        return parsed

    @staticmethod
    def _parse_response(
        data: dict,
        latency_ms: float | None = None,
        attempts: int = 1,
    ) -> EmbeddingResponse:
        """Parse the raw API response into an EmbeddingResponse object."""
        items = data.get("data")
        if not isinstance(items, list) or not items:
            raise InvalidResponseError(
                "Provider returned a response without embedding data",
                attempts=attempts,
            )
        # Providers may return items out of order; the index field keeps each
        # vector aligned with its input position.
        indexes = [
            item.get("index") if isinstance(item, dict) else None for item in items
        ]
        if any(type(index) is not int for index in indexes) or sorted(indexes) != list(
            range(len(items))
        ):
            raise InvalidResponseError(
                "Provider returned invalid embedding indexes",
                attempts=attempts,
            )
        items = sorted(items, key=lambda item: item["index"])

        embeddings: list[list[float]] = []
        for item in items:
            vector = item.get("embedding") if isinstance(item, dict) else None
            if not isinstance(vector, list) or not vector:
                raise InvalidResponseError(
                    "Provider returned an embedding that is not a non-empty list",
                    attempts=attempts,
                )
            try:
                embedding = [float(value) for value in vector]
            except (TypeError, ValueError, OverflowError) as exc:
                raise InvalidResponseError(
                    "Provider returned non-numeric embedding values",
                    attempts=attempts,
                ) from exc
            if any(not isfinite(value) for value in embedding):
                raise InvalidResponseError(
                    "Provider returned a non-finite embedding coordinate",
                    attempts=attempts,
                )
            embeddings.append(embedding)

        if any(len(embedding) != len(embeddings[0]) for embedding in embeddings[1:]):
            raise InvalidResponseError(
                "Provider returned embeddings with inconsistent dimensions",
                attempts=attempts,
            )

        usage = None
        usage_data = data.get("usage")
        if isinstance(usage_data, dict):
            usage = Usage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )

        return EmbeddingResponse(
            embeddings=embeddings,
            model=data.get("model", ""),
            usage=usage,
            latency_ms=latency_ms,
            attempts=attempts,
            raw=data,
        )

    def _record_success(self, response: EmbeddingResponse) -> None:
        """Write one success record without allowing logging to break a call."""
        if self.usage_logger is None or response.latency_ms is None:
            return
        entry = UsageLogEntry.success(
            provider=self.provider,
            model=response.model,
            usage=response.usage,
            latency_ms=response.latency_ms,
            estimated_cost_usd=estimate_cost_usd(
                self.provider,
                response.model,
                response.usage,
            ),
            attempts=response.attempts,
        )
        append_usage_entry(self.usage_logger, entry)

    def _record_failure(
        self,
        *,
        model: str,
        error: LLMError,
        latency_ms: float,
    ) -> None:
        """Attach total latency to an error and write one failure record."""
        error.latency_ms = latency_ms
        if self.usage_logger is None:
            return
        entry = UsageLogEntry.failure(
            provider=self.provider,
            model=model,
            latency_ms=latency_ms,
            attempts=error.attempts,
            error_type=type(error).__name__,
        )
        append_usage_entry(self.usage_logger, entry)

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> bool:
        self.close()
        return False


def embedding_client_from_env(
    env: Mapping[str, str] | None = None,
) -> tuple[EmbeddingClient, str]:
    """
    Build an embedding client and model name from environment settings.

    Provider resolution: EMBEDDING_PROVIDER, then LLM_PROVIDER, then "openai".
    Model resolution: EMBEDDING_MODEL, then a built-in default per provider.

    Example:
        client, model = embedding_client_from_env()
        with client:
            response = client.embed("Where is margin calculated?", model=model)
        print(response.dimension)
    """
    if env is None:
        env = os.environ

    settings = load_settings(env)
    provider = (
        env.get("EMBEDDING_PROVIDER") or env.get("LLM_PROVIDER") or "openai"
    ).strip()
    provider = provider.lower()
    model = (
        env.get("EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODELS.get(provider) or ""
    ).strip()
    if not model:
        raise ConfigError(
            f"No default embedding model for provider '{provider}'; "
            "set EMBEDDING_MODEL in the environment (see .env.example)"
        )

    config = settings.get(provider)
    if not config.is_configured:
        raise ConfigError(
            f"Provider '{provider}' is not configured; "
            "set its API key / base URL in the environment (see .env.example)"
        )

    client = EmbeddingClient(
        api_key=config.api_key,
        base_url=config.endpoint,
        timeout=settings.timeout,
        provider=provider,
        max_retries=settings.max_retries,
        retry_base_delay=settings.retry_base_delay,
        usage_logger=(
            UsageLogger(settings.usage_log_path) if settings.usage_log_path else None
        ),
    )
    return client, model
