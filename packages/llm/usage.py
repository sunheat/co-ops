"""Token usage, cost estimation, and JSONL usage logging."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Usage:
    """Token usage statistics for a completion."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


@dataclass(frozen=True)
class ModelPrice:
    """USD price per one million input and output text tokens."""

    input_per_million: float
    output_per_million: float


# This deliberately small, hand-written table is easy to audit and update.
# Prices are standard (non-batch) text-token rates checked on 2026-07-29.
# Source: https://developers.openai.com/api/docs/models/gpt-4o-mini
# Unknown provider/model pairs return None rather than a misleading estimate.
PRICE_TABLE: dict[tuple[str, str], ModelPrice] = {
    ("openai", "gpt-4o-mini"): ModelPrice(
        input_per_million=0.15,
        output_per_million=0.60,
    ),
    ("openai", "gpt-4o-mini-2024-07-18"): ModelPrice(
        input_per_million=0.15,
        output_per_million=0.60,
    ),
}


def estimate_cost_usd(
    provider: str,
    model: str,
    usage: Usage | None,
) -> float | None:
    """Estimate a call's token cost, or return None when pricing is unknown."""
    if usage is None:
        return None
    price = PRICE_TABLE.get((provider.lower(), model.lower()))
    if price is None:
        return None
    cost = (
        usage.prompt_tokens * price.input_per_million
        + usage.completion_tokens * price.output_per_million
    ) / 1_000_000
    return round(cost, 12)


@dataclass(frozen=True)
class UsageLogEntry:
    """One completed request, ready to be serialized as a JSONL record."""

    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    latency_ms: float
    estimated_cost_usd: float | None
    status: str
    attempts: int
    error_type: str | None = None

    @classmethod
    def success(
        cls,
        *,
        provider: str,
        model: str,
        usage: Usage | None,
        latency_ms: float,
        estimated_cost_usd: float | None,
        attempts: int,
    ) -> UsageLogEntry:
        """Build a successful-call record, tolerating omitted usage data."""
        usage = usage or Usage(0, 0, 0)
        return cls(
            provider=provider,
            model=model,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            total_tokens=usage.total_tokens,
            latency_ms=round(latency_ms, 3),
            estimated_cost_usd=estimated_cost_usd,
            status="success",
            attempts=attempts,
        )

    @classmethod
    def failure(
        cls,
        *,
        provider: str,
        model: str,
        latency_ms: float,
        attempts: int,
        error_type: str,
    ) -> UsageLogEntry:
        """Build a failed-call record; no prompt or response content is logged."""
        return cls(
            provider=provider,
            model=model,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            latency_ms=round(latency_ms, 3),
            estimated_cost_usd=None,
            status="error",
            attempts=attempts,
            error_type=error_type,
        )

    def to_dict(self) -> dict:
        """Return a JSON-serializable dictionary."""
        return asdict(self)


class UsageLogger:
    """Append usage records to a UTF-8 JSON Lines file."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def log(self, entry: UsageLogEntry) -> None:
        """Append one complete JSON object followed by a newline."""
        line = json.dumps(entry.to_dict(), ensure_ascii=False, separators=(",", ":"))
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as file:
                file.write(line + "\n")


class UsageTracker:
    """Accumulates usage across multiple completions (e.g., per session)."""

    def __init__(self):
        self.total = Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
        self.calls = 0

    def record(self, usage: Usage | None) -> None:
        """Count a call and add its tokens when the provider reports usage."""
        self.calls += 1
        if usage is None:
            return
        self.total = self.total + usage
