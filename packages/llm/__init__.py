"""Universal LLM client package."""

from .client import LLMClient, chat, close_default_router
from .config import ProviderConfig, LLMSettings, load_settings
from .router import ModelRouter
from .schemas import ChatMessage, ChatChoice, ChatResponse, LLMResponse
from .usage import Usage, UsageTracker
from .providers import Provider, PROVIDERS, get_provider
from .errors import (
    LLMError,
    AuthenticationError,
    RateLimitError,
    APIError,
    ConfigError,
    UnknownProviderError,
)

__all__ = [
    "chat",
    "close_default_router",
    "LLMClient",
    "ProviderConfig",
    "LLMSettings",
    "load_settings",
    "ModelRouter",
    "ChatMessage",
    "ChatChoice",
    "ChatResponse",
    "LLMResponse",
    "Usage",
    "UsageTracker",
    "Provider",
    "PROVIDERS",
    "get_provider",
    "LLMError",
    "AuthenticationError",
    "RateLimitError",
    "APIError",
    "ConfigError",
    "UnknownProviderError",
]
