"""Configuration loading for all supported LLM providers.

Settings are read from environment variables (or an injected mapping for tests):

    OPENAI_API_KEY / OPENAI_BASE_URL
    AZURE_OPENAI_API_KEY / AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_DEPLOYMENT
    GEMINI_API_KEY
    OPENROUTER_API_KEY
    DEEPSEEK_API_KEY
    LOCAL_LLM_BASE_URL

API keys are excluded from repr/str (repr=False) so they never leak into logs.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

from .errors import ConfigError
from .providers import get_provider


@dataclass
class ProviderConfig:
    """Configuration for a single LLM provider.

    The api_key field is excluded from repr so instances are safe to log.
    """

    name: str
    api_key: str | None = field(default=None, repr=False)
    base_url: str | None = None
    deployment: str | None = None  # Azure OpenAI deployment name

    @property
    def is_configured(self) -> bool:
        """Whether this provider has enough settings to be used."""
        if self.name == "local":
            return bool(self.base_url)
        if self.name == "azure":
            return bool(self.api_key and self.base_url and self.deployment)
        return bool(self.api_key)

    @property
    def endpoint(self) -> str | None:
        """Final base URL to send requests to (Azure composes the deployment path)."""
        if self.name == "azure":
            if not (self.base_url and self.deployment):
                return None
            return f"{self.base_url.rstrip('/')}/openai/deployments/{self.deployment}"
        return self.base_url


@dataclass
class LLMSettings:
    """All provider configurations resolved from the environment."""

    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    timeout: float = 60.0

    def get(self, name: str) -> ProviderConfig:
        """Return the config for a provider, raising ConfigError if unknown."""
        key = name.lower()
        if key not in self.providers:
            known = ", ".join(sorted(self.providers))
            raise ConfigError(f"Unknown provider '{name}'. Known providers: {known}")
        return self.providers[key]

    def configured_providers(self) -> list[str]:
        """Names of providers that have enough settings to be used."""
        return [name for name, p in self.providers.items() if p.is_configured]


def load_settings(env: Mapping[str, str] | None = None) -> LLMSettings:
    """
    Load settings for all supported providers.

    Args:
        env: Environment mapping to read from. Defaults to os.environ;
            pass a dict in tests to avoid touching the real environment.
    """
    if env is None:
        env = os.environ

    timeout_raw = env.get("LLM_TIMEOUT", "60")
    try:
        timeout = float(timeout_raw)
    except ValueError as e:
        raise ConfigError(f"LLM_TIMEOUT must be a number, got {timeout_raw!r}") from e

    providers = {
        "openai": ProviderConfig(
            name="openai",
            api_key=env.get("OPENAI_API_KEY"),
            base_url=env.get("OPENAI_BASE_URL", get_provider("openai").base_url),
        ),
        "azure": ProviderConfig(
            name="azure",
            api_key=env.get("AZURE_OPENAI_API_KEY"),
            base_url=env.get("AZURE_OPENAI_ENDPOINT"),
            deployment=env.get("AZURE_OPENAI_DEPLOYMENT"),
        ),
        "gemini": ProviderConfig(
            name="gemini",
            api_key=env.get("GEMINI_API_KEY"),
            base_url=get_provider("gemini").base_url,
        ),
        "openrouter": ProviderConfig(
            name="openrouter",
            api_key=env.get("OPENROUTER_API_KEY"),
            base_url=get_provider("openrouter").base_url,
        ),
        "deepseek": ProviderConfig(
            name="deepseek",
            api_key=env.get("DEEPSEEK_API_KEY"),
            base_url=get_provider("deepseek").base_url,
        ),
        "local": ProviderConfig(
            name="local",
            api_key=None,  # local endpoints don't need a key
            base_url=env.get("LOCAL_LLM_BASE_URL"),
        ),
    }
    return LLMSettings(providers=providers, timeout=timeout)
