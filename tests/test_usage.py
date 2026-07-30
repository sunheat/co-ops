"""Tests for token-cost estimation and JSONL serialization."""

import json

import httpx

from packages.llm import (
    LLMClient,
    Usage,
    UsageLogEntry,
    UsageLogger,
    estimate_cost_usd,
)


def test_estimate_cost_uses_separate_input_and_output_rates():
    usage = Usage(prompt_tokens=123, completion_tokens=45, total_tokens=168)
    assert estimate_cost_usd("openai", "gpt-4o-mini", usage) == 0.00004545


def test_estimate_cost_returns_none_for_unknown_pricing():
    usage = Usage(prompt_tokens=10, completion_tokens=10, total_tokens=20)
    assert estimate_cost_usd("local", "qwen2.5", usage) is None
    assert estimate_cost_usd("openai", "unknown-model", usage) is None
    assert estimate_cost_usd("openai", "gpt-4o-mini", None) is None


def test_usage_logger_appends_json_lines(tmp_path):
    path = tmp_path / "nested" / "usage.jsonl"
    logger = UsageLogger(path)
    entry = UsageLogEntry.success(
        provider="openai",
        model="gpt-4o-mini",
        usage=Usage(123, 45, 168),
        latency_ms=920.12345,
        estimated_cost_usd=0.00004545,
        attempts=1,
    )

    logger.log(entry)
    logger.log(entry)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    record = json.loads(lines[0])
    assert record == {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "prompt_tokens": 123,
        "completion_tokens": 45,
        "total_tokens": 168,
        "latency_ms": 920.123,
        "estimated_cost_usd": 0.00004545,
        "status": "success",
        "attempts": 1,
        "error_type": None,
    }


def test_usage_is_recorded(tmp_path):
    """A successful chat() call writes one usage record with real token counts."""
    log_path = tmp_path / "usage.jsonl"

    def handler(request):
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "model": "gpt-4o-mini",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "hi"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 123,
                    "completion_tokens": 45,
                    "total_tokens": 168,
                },
            },
        )

    client = LLMClient(
        base_url="http://testserver/v1",
        provider="openai",
        usage_logger=UsageLogger(log_path),
    )
    client._client.close()
    client._client = httpx.Client(
        base_url="http://testserver/v1", transport=httpx.MockTransport(handler)
    )
    with client:
        client.chat(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
        )

    record = json.loads(log_path.read_text(encoding="utf-8"))
    assert record["status"] == "success"
    assert record["provider"] == "openai"
    assert record["model"] == "gpt-4o-mini"
    assert record["prompt_tokens"] == 123
    assert record["completion_tokens"] == 45
    assert record["total_tokens"] == 168
    assert record["estimated_cost_usd"] == 0.00004545
    assert record["attempts"] == 1
