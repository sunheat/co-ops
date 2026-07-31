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
    "load_settings",
]
