"""Universal LLM client package."""

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
from .prompt import ContextBlock, MessageBuilder, PromptTemplate
from .providers import PROVIDERS, Provider, get_provider
from .router import ModelRouter
from .schemas import ChatChoice, ChatMessage, ChatResponse, LLMResponse
from .structured_output import (
    InvestigationPlan,
    investigation_plan_correction_instruction,
    investigation_plan_output_instruction,
    parse_investigation_plan,
    request_investigation_plan,
)
from .usage import (
    PRICE_TABLE,
    ModelPrice,
    Usage,
    UsageLogEntry,
    UsageLogger,
    UsageTracker,
    estimate_cost_usd,
)

__all__ = [
    "PRICE_TABLE",
    "PROVIDERS",
    "APIError",
    "AuthenticationError",
    "ChatChoice",
    "ChatMessage",
    "ChatResponse",
    "ConfigError",
    "ContextBlock",
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
