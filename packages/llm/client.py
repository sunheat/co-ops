"""Universal OpenAI-compatible LLM client."""

import atexit
import threading
import time

import httpx
from .schemas import ChatMessage, ChatChoice, ChatResponse, LLMResponse
from .usage import Usage
from .errors import AuthenticationError, RateLimitError, APIError


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
    ):
        """
        Initialize the LLM client.

        Args:
            api_key: API key for authentication. Can be None for local endpoints.
            base_url: Base URL of the OpenAI-compatible API.
            timeout: Request timeout in seconds.
            default_headers: Additional headers to include in every request.
        """
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

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
        try:
            response = self._client.post("/chat/completions", json=payload)
        except httpx.HTTPError as e:
            raise APIError(f"Request failed: {e}") from e
        latency_ms = (time.perf_counter() - started) * 1000

        if response.status_code == 401:
            raise AuthenticationError("Invalid API key or unauthorized access")
        if response.status_code == 429:
            raise RateLimitError("Rate limit exceeded")
        if response.status_code >= 400:
            try:
                error_body = response.json()
            except Exception:
                error_body = {}
            error_msg = self._extract_error_message(error_body) or response.text
            if not isinstance(error_body, dict):
                error_body = {"error": error_body}
            raise APIError(
                f"API error: {error_msg}",
                status_code=response.status_code,
                body=error_body,
            )

        try:
            data = response.json()
        except Exception as e:
            raise APIError(f"Failed to parse response: {e}") from e

        return self._parse_response(data, latency_ms=latency_ms)

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

    def _parse_response(self, data: dict, latency_ms: float | None = None) -> ChatResponse:
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
        if "usage" in data and data["usage"]:
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
