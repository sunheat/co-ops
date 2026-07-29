"""Tests for timeout, retry, error handling, and request logging."""

import json

import httpx
import pytest

from packages.llm import LLMClient, UsageLogger
from packages.llm.errors import (
    AuthenticationError,
    InvalidResponseError,
    LLMTimeoutError,
)


def _success_response() -> dict:
    return {
        "id": "chatcmpl-test",
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "hello"},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 123,
            "completion_tokens": 45,
            "total_tokens": 168,
        },
    }


def _replace_transport(client: LLMClient, handler) -> None:
    client._client.close()
    client._client = httpx.Client(
        base_url=client.base_url,
        transport=httpx.MockTransport(handler),
        timeout=client.timeout,
    )


def test_retries_transient_5xx_then_logs_one_success(tmp_path):
    calls = 0
    log_path = tmp_path / "usage.jsonl"

    def handler(request):
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(503, json={"error": {"message": "try later"}})
        return httpx.Response(200, json=_success_response())

    with LLMClient(
        base_url="http://testserver/v1",
        provider="openai",
        max_retries=2,
        retry_base_delay=0,
        usage_logger=UsageLogger(log_path),
    ) as client:
        _replace_transport(client, handler)
        response = client.chat(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
        )

    assert calls == 3
    assert response.attempts == 3
    assert response.estimated_cost_usd == 0.00004545

    records = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert len(records) == 1
    assert records[0]["status"] == "success"
    assert records[0]["attempts"] == 3
    assert records[0]["prompt_tokens"] == 123


def test_timeout_retries_then_raises_typed_error_and_logs_failure(tmp_path):
    calls = 0
    log_path = tmp_path / "usage.jsonl"

    def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("too slow", request=request)

    with LLMClient(
        base_url="http://testserver/v1",
        timeout=0.1,
        provider="openai",
        max_retries=2,
        retry_base_delay=0,
        usage_logger=UsageLogger(log_path),
    ) as client:
        _replace_transport(client, handler)
        with pytest.raises(LLMTimeoutError) as exc_info:
            client.chat(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": "hi"}],
            )

    assert calls == 3
    assert exc_info.value.attempts == 3
    assert exc_info.value.latency_ms is not None

    record = json.loads(log_path.read_text())
    assert record["status"] == "error"
    assert record["attempts"] == 3
    assert record["error_type"] == "LLMTimeoutError"
    assert record["prompt_tokens"] == 0


def test_authentication_error_is_not_retried():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"error": {"message": "bad key"}})

    with LLMClient(
        base_url="http://testserver/v1",
        max_retries=5,
        retry_base_delay=0,
    ) as client:
        _replace_transport(client, handler)
        with pytest.raises(AuthenticationError) as exc_info:
            client.chat(model="m", messages=[{"role": "user", "content": "hi"}])

    assert calls == 1
    assert exc_info.value.attempts == 1


def test_invalid_success_response_is_typed_and_not_retried():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, text="<html>not json</html>")

    with LLMClient(
        base_url="http://testserver/v1",
        max_retries=5,
        retry_base_delay=0,
    ) as client:
        _replace_transport(client, handler)
        with pytest.raises(InvalidResponseError) as exc_info:
            client.chat(model="m", messages=[{"role": "user", "content": "hi"}])

    assert calls == 1
    assert exc_info.value.attempts == 1
    assert exc_info.value.latency_ms is not None


def test_retry_after_header_is_used():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "0"},
                json={"error": {"message": "slow down"}},
            )
        return httpx.Response(200, json=_success_response())

    with LLMClient(
        base_url="http://testserver/v1",
        max_retries=1,
        retry_base_delay=10,
    ) as client:
        _replace_transport(client, handler)
        response = client.chat(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
        )

    assert calls == 2
    assert response.attempts == 2


@pytest.mark.parametrize("status_code", [408, 409, 503])
def test_retryable_http_errors_honor_retry_after(status_code):
    calls = 0
    observed_retry_after = []

    def handler(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(
                status_code,
                headers={"Retry-After": "7"},
                json={"error": {"message": "try later"}},
            )
        return httpx.Response(200, json=_success_response())

    with LLMClient(
        base_url="http://testserver/v1",
        max_retries=1,
        retry_base_delay=0,
    ) as client:
        _replace_transport(client, handler)

        def observe_delay(attempt, error):
            observed_retry_after.append(error.retry_after)
            return 0

        client._retry_delay = observe_delay
        response = client.chat(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
        )

    assert calls == 2
    assert response.attempts == 2
    assert observed_retry_after == [7.0]
