"""Typed errors for reliable LLM calls and retry decisions."""

from __future__ import annotations


class LLMError(Exception):
    """Base exception for all LLM client errors."""

    retryable = False

    def __init__(self, message: str, *, attempts: int = 1):
        super().__init__(message)
        self.attempts = attempts
        self.latency_ms: float | None = None


class AuthenticationError(LLMError):
    """API key is missing or invalid (HTTP 401/403); never retry."""


class RateLimitError(LLMError):
    """The provider rejected the request due to rate limiting (HTTP 429)."""

    retryable = True

    def __init__(
        self,
        message: str,
        *,
        retry_after: float | None = None,
        attempts: int = 1,
    ):
        super().__init__(message, attempts=attempts)
        self.status_code = 429
        self.retry_after = retry_after


class LLMTimeoutError(LLMError):
    """The request exceeded its configured timeout."""

    retryable = True


class LLMConnectionError(LLMError):
    """The provider could not be reached due to a transport failure."""

    retryable = True


class InvalidResponseError(LLMError):
    """The provider returned a successful HTTP response that was not valid JSON."""


class APIError(LLMError):
    """The provider returned an unexpected HTTP error response.

    `body` is normalized to a dict for uniform handling; `raw_body` keeps the
    provider's response exactly as parsed (e.g. Gemini's top-level array).
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        body: dict | None = None,
        raw_body=None,
        *,
        retryable: bool | None = None,
        attempts: int = 1,
    ):
        super().__init__(message, attempts=attempts)
        self.status_code = status_code
        self.body = body or {}
        self.raw_body = raw_body if raw_body is not None else self.body
        if retryable is None:
            self.retryable = status_code in {408, 409, 429} or (
                status_code is not None and status_code >= 500
            )
        else:
            self.retryable = retryable


class ConfigError(LLMError):
    """The client configuration is invalid or incomplete."""


class UnknownProviderError(LLMError):
    """A provider name cannot be resolved."""
