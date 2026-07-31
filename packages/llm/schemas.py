"""Schema definitions (request/response dataclasses) for the LLM client."""

from dataclasses import dataclass, field
from typing import Literal

from .usage import Usage

Role = Literal["system", "user", "assistant"]


@dataclass
class ChatMessage:
    """A single message in a chat conversation."""

    role: Role
    content: str

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class ChatChoice:
    """A single choice in a chat completion response."""

    index: int
    message: ChatMessage
    finish_reason: str | None = None


@dataclass
class ChatResponse:
    """Response from a chat completion request."""

    id: str
    model: str
    choices: list[ChatChoice]
    usage: Usage | None = None
    latency_ms: float | None = None
    estimated_cost_usd: float | None = None
    attempts: int = 1
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def content(self) -> str:
        """Convenience accessor for the first choice's content."""
        if not self.choices:
            return ""
        return self.choices[0].message.content

    @property
    def message(self) -> ChatMessage:
        """Convenience accessor for the first choice's message."""
        if not self.choices:
            return ChatMessage(role="assistant", content="")
        return self.choices[0].message


@dataclass
class LLMResponse:
    """Unified, flat response object returned by the top-level chat() interface."""

    content: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float | None = None
    estimated_cost_usd: float | None = None
    attempts: int = 1
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_chat_response(cls, response: ChatResponse, provider: str) -> "LLMResponse":
        """Flatten a ChatResponse into the unified response shape."""
        usage = response.usage
        return cls(
            content=response.content,
            provider=provider,
            model=response.model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            latency_ms=response.latency_ms,
            estimated_cost_usd=response.estimated_cost_usd,
            attempts=response.attempts,
            raw=response.raw,
        )
