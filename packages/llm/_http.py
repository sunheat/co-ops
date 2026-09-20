"""Shared HTTP response handling and retry policy for provider clients."""

from __future__ import annotations

import time
from collections.abc import Callable
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

MAX_RETRY_AFTER_SECONDS = 60.0
MAX_BACKOFF_SECONDS = 8.0


def post_json_with_retries(
    http: httpx.Client,
    path: str,
    payload: dict,
    *,
    timeout: float,
    max_retries: int,
    retry_base_delay: float,
    on_failure: Callable[[LLMError, float], None],
) -> tuple[dict, float, int]:
    """
    POST a JSON payload, mapping errors and retrying transient failures.

    Returns (response body, latency in milliseconds, attempts). When a call
    ultimately fails, ``on_failure(error, latency_ms)`` runs before the typed
    error is raised, so the caller can write its usage-log failure record.
    """
    started = time.perf_counter()
    max_attempts = max_retries + 1

    for attempt in range(1, max_attempts + 1):
        try:
            response = http.post(path, json=payload)
            error = error_from_response(response)
        except httpx.TimeoutException as exc:
            error = LLMTimeoutError(
                f"Request timed out after {timeout:g} seconds",
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
                time.sleep(retry_delay(retry_base_delay, attempt, error))
                continue
            on_failure(error, elapsed_ms(started))
            raise error

        try:
            data = response.json()
        except ValueError as exc:
            error = InvalidResponseError(
                f"Provider returned invalid JSON: {exc}",
                attempts=attempt,
            )
            on_failure(error, elapsed_ms(started))
            raise error from exc

        if not isinstance(data, dict):
            error = InvalidResponseError(
                "Provider returned a JSON response that is not an object",
                attempts=attempt,
            )
            on_failure(error, elapsed_ms(started))
            raise error

        return data, elapsed_ms(started), attempt

    raise AssertionError("retry loop exited unexpectedly")


def elapsed_ms(started: float) -> float:
    """Milliseconds since a ``time.perf_counter()`` reading."""
    return (time.perf_counter() - started) * 1000


def error_from_response(response: httpx.Response) -> LLMError | None:
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
            retry_after=parse_retry_after(response),
        )

    # Keep the provider's body untouched for observation; normalize a copy
    # to dict so downstream .body handling stays uniform.
    try:
        error_body = response.json()
        raw_body = error_body
    except ValueError:
        error_body = {}
        raw_body = response.text
    error_msg = extract_error_message(error_body) or response.text
    if not isinstance(error_body, dict):
        error_body = {"error": error_body}
    return APIError(
        f"API error: {error_msg}",
        status_code=response.status_code,
        body=error_body,
        raw_body=raw_body,
        retry_after=parse_retry_after(response),
    )


def parse_retry_after(response: httpx.Response) -> float | None:
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


def retry_delay(base_delay: float, attempt: int, error: LLMError) -> float:
    """Return Retry-After or capped exponential backoff for the next try."""
    retry_after = getattr(error, "retry_after", None)
    if retry_after is not None:
        return min(retry_after, MAX_RETRY_AFTER_SECONDS)
    return min(base_delay * (2 ** (attempt - 1)), MAX_BACKOFF_SECONDS)


def extract_error_message(error_body) -> str | None:
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
