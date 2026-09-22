"""Universal OpenAI-compatible LLM client."""

import atexit
import os
import threading
from collections.abc import Mapping
from math import isfinite

import httpx

from ._http import post_json_with_retries
from .config import load_settings
from .errors import ConfigError, LLMError
from .schemas import ChatChoice, ChatMessage, ChatResponse, LLMResponse
from .usage import (
    Usage,
    UsageLogEntry,
    UsageLogger,
    append_usage_entry,
    estimate_cost_usd,
)

DEFAULT_CHAT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "gemini": "gemini-flash-latest",
    "deepseek": "deepseek-chat",
    "local": "qwen2.5",  # Ollama default; other local servers vary
}


class LLMClient:
    """
    A universal LLM client that speaks the OpenAI Chat Completions API.

    Works with any OpenAI-compatible endpoint:
    - OpenAI: base_url="https://api.openai.com/v1"
    - Azure OpenAI: base_url="https://<resource>.openai.azure.com/openai/v1"
      (v1 API: the deployment name goes in the model field)
    - OpenRouter: base_url="https://openrouter.ai/api/v1"
    - Gemini: base_url="https://generativelanguage.googleapis.com/v1beta/openai"
    - DeepSeek: base_url="https://api.deepseek.com/v1"
    - Ollama: base_url="http://localhost:11434/v1"

    Example:
        client = LLMClient(api_key="sk-...", base_url="https://api.openai.com/v1")
        response = client.chat(
            model="gpt-4o-mini",
            messages=[ChatMessage(role="user", content="Hello!")],
            temperature=0.7,
        )
        print(response.content)
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 60.0,
        default_headers: dict[str, str] | None = None,
        provider: str = "unknown",
        max_retries: int = 2,
        retry_base_delay: float = 0.5,
        usage_logger: UsageLogger | None = None,
    ):
        """
        Initialize the LLM client.

        Args:
            api_key: API key for authentication. Can be None for local endpoints.
            base_url: Base URL of the OpenAI-compatible API.
            timeout: Request timeout in seconds.
            default_headers: Additional headers to include in every request.
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
        if default_headers:
            headers.update(default_headers)

        self._client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout,
        )

    def chat(
        self,
        model: str,
        messages: list[ChatMessage | dict],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        response_format: str | None = None,
        **kwargs,
    ) -> ChatResponse:
        """
        Send a chat completion request.

        Args:
            model: Model name (e.g., "gpt-4o-mini", "deepseek-chat").
            messages: List of ChatMessage objects or plain dicts
                ({"role": ..., "content": ...}).
            temperature: Sampling temperature (0.0 to 2.0).
            max_tokens: Maximum tokens to generate.
            response_format: Response format ("json" or "text").
            **kwargs: Additional parameters passed to the API.

        Returns:
            ChatResponse object with the completion result.

        Raises:
            AuthenticationError: If API key is invalid (HTTP 401).
            RateLimitError: If rate limit is exceeded (HTTP 429).
            APIError: For other API errors.
        """
        payload = {
            "model": model,
            "messages": [
                msg.to_dict() if isinstance(msg, ChatMessage) else dict(msg)
                for msg in messages
            ],
            "temperature": temperature,
        }

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        if response_format:
            if response_format.lower() == "json":
                payload["response_format"] = {"type": "json_object"}
            elif response_format.lower() == "text":
                payload["response_format"] = {"type": "text"}

        payload.update(kwargs)

        data, latency_ms, attempts = post_json_with_retries(
            self._client,
            "/chat/completions",
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
        parsed = self._parse_response(
            data,
            latency_ms=latency_ms,
            attempts=attempts,
        )
        if not parsed.model:
            parsed.model = model
        parsed.estimated_cost_usd = estimate_cost_usd(
            self.provider,
            parsed.model,
            parsed.usage,
        )
        self._record_success(parsed)
        return parsed

    def _record_success(self, response: ChatResponse) -> None:
        """Write one success record without allowing logging to break a call."""
        if self.usage_logger is None or response.latency_ms is None:
            return
        entry = UsageLogEntry.success(
            provider=self.provider,
            model=response.model,
            usage=response.usage,
            latency_ms=response.latency_ms,
            estimated_cost_usd=response.estimated_cost_usd,
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

    def _parse_response(
        self,
        data: dict,
        latency_ms: float | None = None,
        attempts: int = 1,
    ) -> ChatResponse:
        """Parse the raw API response into a ChatResponse object."""
        choices = []
        for choice_data in data.get("choices", []):
            message_data = choice_data.get("message", {})
            content = message_data.get("content")
            message = ChatMessage(
                role=message_data.get("role", "assistant"),
                content=content if content is not None else "",
            )
            choices.append(
                ChatChoice(
                    index=choice_data.get("index", 0),
                    message=message,
                    finish_reason=choice_data.get("finish_reason"),
                )
            )

        usage = None
        if data.get("usage"):
            usage_data = data["usage"]
            usage = Usage(
                prompt_tokens=usage_data.get("prompt_tokens", 0),
                completion_tokens=usage_data.get("completion_tokens", 0),
                total_tokens=usage_data.get("total_tokens", 0),
            )

        return ChatResponse(
            id=data.get("id", ""),
            model=data.get("model", ""),
            choices=choices,
            usage=usage,
            latency_ms=latency_ms,
            attempts=attempts,
            raw=data,
        )

    def close(self):
        """Close the underlying HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


def chat_client_from_env(
    env: Mapping[str, str] | None = None,
) -> tuple[LLMClient, str]:
    """
    Build a chat client and model name from environment settings.

    Provider resolution: LLM_PROVIDER, then "openai".
    Model resolution: LLM_MODEL, then a built-in default per provider, then the
    Azure OpenAI deployment name.

    Example:
        client, model = chat_client_from_env()
        with client:
            response = client.chat(model=model, messages=[{"role": "user", "content": "Hi"}])
        print(response.content)
    """
    if env is None:
        env = os.environ

    settings = load_settings(env)
    provider = (env.get("LLM_PROVIDER") or "openai").strip().lower()

    config = settings.get(provider)
    if not config.is_configured:
        raise ConfigError(
            f"Provider '{provider}' is not configured; "
            "set its API key / base URL in the environment (see .env.example)"
        )

    model = (env.get("LLM_MODEL") or DEFAULT_CHAT_MODELS.get(provider, "")).strip()
    if not model:
        # Azure v1 API: the model field carries the deployment name.
        model = (config.deployment or "").strip()
    if not model:
        raise ConfigError(
            f"No default chat model for provider '{provider}'; "
            "set LLM_MODEL in the environment (see .env.example)"
        )

    client = LLMClient(
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


_default_router = None
_default_router_lock = threading.Lock()


def _get_default_router():
    """Return the shared ModelRouter, creating it on first use (thread-safe)."""
    global _default_router
    if _default_router is None:
        with _default_router_lock:
            if _default_router is None:
                from .router import ModelRouter

                _default_router = ModelRouter()
    return _default_router


def close_default_router() -> None:
    """Close the shared router (and its clients) and reset it.

    Registered via atexit; safe to call manually and multiple times.
    The next llm.chat() call will lazily create a fresh router.
    """
    global _default_router
    with _default_router_lock:
        if _default_router is not None:
            _default_router.close()
            _default_router = None


atexit.register(close_default_router)


def chat(
    messages: list[ChatMessage | dict],
    provider: str,
    model: str,
    temperature: float = 0.7,
    **kwargs,
) -> LLMResponse:
    """
    Unified chat interface: pick a provider by name and return a flat LLMResponse.

    Example:
        from packages import llm

        response = llm.chat(
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Explain RAG in one paragraph."},
            ],
            provider="openai",
            model="gpt-4o-mini",
            temperature=0.2,
        )
        print(response.content, response.total_tokens, response.latency_ms)
    """
    response = _get_default_router().chat(
        f"{provider}/{model}", messages, temperature=temperature, **kwargs
    )
    return LLMResponse.from_chat_response(response, provider=provider.lower())
