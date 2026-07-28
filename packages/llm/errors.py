"""Custom exceptions for the LLM client."""


class LLMError(Exception):
    """Base exception for all LLM client errors."""


class AuthenticationError(LLMError):
    """Raised when the API key is missing or invalid (HTTP 401)."""


class RateLimitError(LLMError):
    """Raised when the API returns a rate-limit response (HTTP 429)."""


class APIError(LLMError):
    """Raised when the API returns an unexpected error response.

    `body` is normalized to a dict for uniform handling; `raw_body` keeps the
    provider's response exactly as parsed (e.g. Gemini's top-level [...] array)
    for observation/debugging.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        body: dict | None = None,
        raw_body=None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.body = body or {}
        self.raw_body = raw_body if raw_body is not None else self.body


class ConfigError(LLMError):
    """Raised when the client configuration is invalid or incomplete."""


class UnknownProviderError(LLMError):
    """Raised when a provider name cannot be resolved."""
