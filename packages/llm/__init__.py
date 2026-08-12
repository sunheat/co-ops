"""Universal LLM client package."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

from .client import LLMClient, chat, close_default_router
from .config import LLMSettings, ProviderConfig, load_settings
from .errors import (
    APIError,
    AuthenticationError,
    ConfigError,
    InvalidResponseError,
    LLMConnectionError,
    LLMError,
    LLMTimeoutError,
    RateLimitError,
    UnknownProviderError,
)
from .providers import PROVIDERS, Provider, get_provider
from .router import ModelRouter
from .schemas import ChatChoice, ChatMessage, ChatResponse, LLMResponse
from .usage import (
    PRICE_TABLE,
    ModelPrice,
    Usage,
    UsageLogEntry,
    UsageLogger,
    UsageTracker,
    estimate_cost_usd,
)

if TYPE_CHECKING:
    from packages.context import (
        BuiltContext,
        ContextBuilder,
        RetrievedChunk,
        RetrievedContext,
    )
    from packages.prompt import ContextBlock, MessageBuilder, PromptTemplate
    from packages.structured_output import (
        InvestigationPlan,
        investigation_plan_correction_instruction,
        investigation_plan_output_instruction,
        parse_investigation_plan,
        request_investigation_plan,
    )


_LAZY_APPLICATION_EXPORTS = {
    "BuiltContext": ("packages.context", "BuiltContext"),
    "ContextBlock": ("packages.prompt", "ContextBlock"),
    "ContextBuilder": ("packages.context", "ContextBuilder"),
    "InvestigationPlan": ("packages.structured_output", "InvestigationPlan"),
    "MessageBuilder": ("packages.prompt", "MessageBuilder"),
    "PromptTemplate": ("packages.prompt", "PromptTemplate"),
    "RetrievedChunk": ("packages.context", "RetrievedChunk"),
    "RetrievedContext": ("packages.context", "RetrievedContext"),
    "investigation_plan_correction_instruction": (
        "packages.structured_output",
        "investigation_plan_correction_instruction",
    ),
    "investigation_plan_output_instruction": (
        "packages.structured_output",
        "investigation_plan_output_instruction",
    ),
    "parse_investigation_plan": (
        "packages.structured_output",
        "parse_investigation_plan",
    ),
    "request_investigation_plan": (
        "packages.structured_output",
        "request_investigation_plan",
    ),
}


def __getattr__(name: str) -> Any:
    """Lazily resolve application exports without creating import cycles."""
    target = _LAZY_APPLICATION_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


__all__ = [
    "PRICE_TABLE",
    "PROVIDERS",
    "APIError",
    "AuthenticationError",
    "BuiltContext",
    "ChatChoice",
    "ChatMessage",
    "ChatResponse",
    "ConfigError",
    "ContextBlock",
    "ContextBuilder",
    "InvalidResponseError",
    "InvestigationPlan",
    "LLMClient",
    "LLMConnectionError",
    "LLMError",
    "LLMResponse",
    "LLMSettings",
    "LLMTimeoutError",
    "MessageBuilder",
    "ModelPrice",
    "ModelRouter",
    "PromptTemplate",
    "Provider",
    "ProviderConfig",
    "RateLimitError",
    "RetrievedChunk",
    "RetrievedContext",
    "UnknownProviderError",
    "Usage",
    "UsageLogEntry",
    "UsageLogger",
    "UsageTracker",
    "chat",
    "close_default_router",
    "estimate_cost_usd",
    "get_provider",
    "investigation_plan_correction_instruction",
    "investigation_plan_output_instruction",
    "load_settings",
    "parse_investigation_plan",
    "request_investigation_plan",
]
