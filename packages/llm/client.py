"""Universal OpenAI-compatible LLM client."""

import atexit
import logging
import threading
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

from .errors import (
    APIError,
    AuthenticationError,
    InvalidResponseError,
    LLMConnectionError,
    LLMError,
    LLMTimeoutError,
    RateLimitError,
)
from .schemas import ChatChoice, ChatMessage, ChatResponse, LLMResponse
from .usage import (
    Usage,
    UsageLogEntry,
    UsageLogger,
    estimate_cost_usd,
)

logger = logging.getLogger(__name__)


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
        if retry_base_delay < 0:
            raise ValueError("retry_base_delay must be zero or greater")

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

        started = time.perf_counter()
        max_attempts = self.max_retries + 1

        for attempt in range(1, max_attempts + 1):
            try:
                response = self._client.post("/chat/completions", json=payload)
                error = self._error_from_response(response)
            except httpx.TimeoutException as exc:
                error = LLMTimeoutError(
                    f"Request timed out after {self.timeout:g} seconds",
                    attempts=attempt,
                )
                error.__cause__ = exc
            except httpx.RequestError as exc:
                error = LLMConnectionError(
                    f"Could not reach provider: {exc}",
                    attempts=attempt,
                )
                error.__cause__ = exc

            if error is not None:
                error.attempts = attempt
                if error.retryable and attempt < max_attempts:
                    time.sleep(self._retry_delay(attempt, error))
                    continue
                self._record_failure(
                    model=model,
                    error=error,
                    started=started,
                )
                raise error

            try:
                data = response.json()
            except ValueError as exc:
                error = InvalidResponseError(
                    f"Provider returned invalid JSON: {exc}",
                    attempts=attempt,
                )
                self._record_failure(model=model, error=error, started=started)
                raise error from exc
            if not isinstance(data, dict):
                error = InvalidResponseError(
                    "Provider returned a JSON response that is not an object",
                    attempts=attempt,
                )
                self._record_failure(model=model, error=error, started=started)
                raise error

            latency_ms = (time.perf_counter() - started) * 1000
            parsed = self._parse_response(
                data,
                latency_ms=latency_ms,
                attempts=attempt,
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

        raise AssertionError("retry loop exited unexpectedly")

    def _error_from_response(self, response: httpx.Response) -> LLMError | None:
        """Map an HTTP response to a typed error, or return None for success."""
        if response.status_code < 400:
            return None
        if response.status_code in {401, 403}:
            return AuthenticationError(
                "Invalid API key or unauthorized access",
            )
        if response.status_code == 429:
            return RateLimitError(
                "Rate limit exceeded",
                retry_after=self._parse_retry_after(response),
            )

        # Keep the provider's body untouched for observation; normalize a copy
        # to dict so downstream .body handling stays uniform.
        try:
            error_body = response.json()
            raw_body = error_body
        except ValueError:
            error_body = {}
            raw_body = response.text
        error_msg = self._extract_error_message(error_body) or response.text
        if not isinstance(error_body, dict):
            error_body = {"error": error_body}
        return APIError(
            f"API error: {error_msg}",
            status_code=response.status_code,
            body=error_body,
            raw_body=raw_body,
            retry_after=self._parse_retry_after(response),
        )

    @staticmethod
    def _parse_retry_after(response: httpx.Response) -> float | None:
        """Parse Retry-After seconds or an HTTP date; invalid values use backoff."""
        value = response.headers.get("retry-after")
        if value is None:
            return None
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
            except (TypeError, ValueError):
                return None
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=UTC)
            return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())

    def _retry_delay(self, attempt: int, error: LLMError) -> float:
        """Return Retry-After or capped exponential backoff for the next try."""
        retry_after = getattr(error, "retry_after", None)
        if retry_after is not None:
            return min(retry_after, 60.0)
        return min(self.retry_base_delay * (2 ** (attempt - 1)), 8.0)

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
        self._write_usage_entry(entry)

    def _record_failure(
        self,
        *,
        model: str,
        error: LLMError,
        started: float,
    ) -> None:
        """Attach total latency to an error and write one failure record."""
        latency_ms = (time.perf_counter() - started) * 1000
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
        self._write_usage_entry(entry)

    def _write_usage_entry(self, entry: UsageLogEntry) -> None:
        try:
            self.usage_logger.log(entry)
        except OSError:
            logger.warning(
                "Could not write LLM usage log to %s",
                self.usage_logger.path,
                exc_info=True,
            )

    @staticmethod
    def _extract_error_message(error_body) -> str | None:
        """Pull a human-readable message out of an error payload.

        Handles both OpenAI-style ({"error": {"message": ...}}) and
        Ollama/proxy-style ({"error": "..."}) bodies, plus non-dict payloads.
        """
        if not isinstance(error_body, dict):
            return str(error_body) if error_body else None
        error = error_body.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            return message if isinstance(message, str) and message else None
        if isinstance(error, str) and error:
            return error
        message = error_body.get("message")
        if isinstance(message, str) and message:
            return message
        return None

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
            message = ChatMessage(
                role=message_data.get("role", "assistant"),
                content=message_data.get("content", ""),
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
