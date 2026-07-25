"""Token usage statistics and accumulation helpers."""

from dataclasses import dataclass


@dataclass
class Usage:
    """Token usage statistics for a completion."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


class UsageTracker:
    """Accumulates usage across multiple completions (e.g., per session)."""

    def __init__(self):
        self.total = Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
        self.calls = 0

    def record(self, usage: Usage | None) -> None:
        """Record usage from a single completion. None values are ignored."""
        if usage is None:
            return
        self.total = self.total + usage
        self.calls += 1
