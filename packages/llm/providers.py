"""Provider presets for well-known OpenAI-compatible endpoints."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    """Static metadata for an OpenAI-compatible provider."""

    name: str
    base_url: str
    api_key_env: str


PROVIDERS: dict[str, Provider] = {
    "openai": Provider(
        name="openai",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
    ),
    "openrouter": Provider(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
    ),
    "deepseek": Provider(
        name="deepseek",
        base_url="https://api.deepseek.com/v1",
        api_key_env="DEEPSEEK_API_KEY",
    ),
    "gemini": Provider(
        name="gemini",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key_env="GEMINI_API_KEY",
    ),
    "ollama": Provider(
        name="ollama",
        base_url="http://localhost:11434/v1",
        api_key_env="OLLAMA_API_KEY",  # usually unset; local endpoints need no key
    ),
}


def get_provider(name: str) -> Provider:
    """Look up a provider preset by name (case-insensitive)."""
    from .errors import UnknownProviderError

    key = name.lower()
    if key not in PROVIDERS:
        known = ", ".join(sorted(PROVIDERS))
        raise UnknownProviderError(f"Unknown provider '{name}'. Known providers: {known}")
    return PROVIDERS[key]
