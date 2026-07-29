"""Tests for ProviderConfig, LLMSettings, and load_settings()."""

import pytest

from packages.llm import LLMSettings, ProviderConfig, load_settings
from packages.llm.errors import ConfigError, UnknownProviderError
from packages.llm.providers import get_provider


def test_config_loads_from_env(monkeypatch):
    """All supported environment variables are picked up by load_settings()."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://proxy.example.com/v1")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "azure-key")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://myres.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-key")
    monkeypatch.setenv("LOCAL_LLM_BASE_URL", "http://localhost:11434/v1")

    settings = load_settings()

    openai = settings.get("openai")
    assert openai.api_key == "sk-openai"
    assert openai.base_url == "https://proxy.example.com/v1"

    azure = settings.get("azure")
    assert azure.api_key == "azure-key"
    assert azure.base_url == "https://myres.openai.azure.com"
    assert azure.deployment == "gpt-4o"

    assert settings.get("gemini").api_key == "gemini-key"
    assert settings.get("openrouter").api_key == "or-key"
    assert settings.get("deepseek").api_key == "ds-key"
    assert settings.get("local").base_url == "http://localhost:11434/v1"

    assert sorted(settings.configured_providers()) == [
        "azure",
        "deepseek",
        "gemini",
        "local",
        "openai",
        "openrouter",
    ]


def test_load_settings_from_mapping():
    """An explicit env mapping can be injected instead of os.environ."""
    settings = load_settings(env={"DEEPSEEK_API_KEY": "ds-key"})
    assert settings.get("deepseek").api_key == "ds-key"
    assert settings.get("openai").api_key is None
    assert settings.configured_providers() == ["deepseek"]


def test_api_key_not_in_repr():
    """API keys must never appear in repr/str (log safety)."""
    secret = "sk-super-secret"
    config = ProviderConfig(
        name="openai", api_key=secret, base_url="https://api.openai.com/v1"
    )
    assert secret not in repr(config)
    assert secret not in str(config)
    settings = LLMSettings(providers={"openai": config})
    assert secret not in repr(settings)


def test_openai_base_url_default():
    """OPENAI_BASE_URL falls back to the official endpoint."""
    settings = load_settings(env={"OPENAI_API_KEY": "sk-x"})
    assert settings.get("openai").base_url == "https://api.openai.com/v1"


def test_azure_endpoint_composition():
    """Azure endpoint targets the v1 OpenAI-compatible API (/openai/v1)."""
    settings = load_settings(
        env={
            "AZURE_OPENAI_API_KEY": "k",
            "AZURE_OPENAI_ENDPOINT": "https://myres.openai.azure.com/",
            "AZURE_OPENAI_DEPLOYMENT": "gpt-4o",
        }
    )
    azure = settings.get("azure")
    assert azure.is_configured
    assert azure.endpoint == "https://myres.openai.azure.com/openai/v1"
    assert azure.deployment == "gpt-4o"


def test_azure_endpoint_already_v1_suffixed():
    """An endpoint already ending in /openai/v1 is not double-suffixed."""
    config = ProviderConfig(
        name="azure",
        api_key="k",
        base_url="https://myres.openai.azure.com/openai/v1/",
    )
    assert config.endpoint == "https://myres.openai.azure.com/openai/v1"


def test_azure_incomplete_is_not_configured():
    """Azure requires key + endpoint to be usable (deployment is optional)."""
    settings = load_settings(env={"AZURE_OPENAI_API_KEY": "k"})
    azure = settings.get("azure")
    assert not azure.is_configured
    assert azure.endpoint is None


def test_local_requires_only_base_url():
    """Local provider is configured by base URL alone, without an API key."""
    settings = load_settings(env={"LOCAL_LLM_BASE_URL": "http://localhost:8000/v1"})
    local = settings.get("local")
    assert local.is_configured
    assert local.api_key is None

    empty = load_settings(env={})
    assert not empty.get("local").is_configured


def test_settings_get_unknown_provider():
    """Unknown provider names raise ConfigError."""
    settings = load_settings(env={})
    with pytest.raises(ConfigError):
        settings.get("no-such-provider")


def test_load_settings_bad_timeout():
    """Non-numeric LLM_TIMEOUT raises ConfigError."""
    with pytest.raises(ConfigError):
        load_settings(env={"LLM_TIMEOUT": "not-a-number"})


def test_load_reliability_and_logging_settings():
    settings = load_settings(
        env={
            "LLM_TIMEOUT": "12.5",
            "LLM_MAX_RETRIES": "4",
            "LLM_RETRY_BASE_DELAY": "0.25",
            "LLM_USAGE_LOG": "custom/usage.jsonl",
        }
    )
    assert settings.timeout == 12.5
    assert settings.max_retries == 4
    assert settings.retry_base_delay == 0.25
    assert settings.usage_log_path == "custom/usage.jsonl"


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("LLM_TIMEOUT", "0"),
        ("LLM_MAX_RETRIES", "-1"),
        ("LLM_MAX_RETRIES", "1.5"),
        ("LLM_RETRY_BASE_DELAY", "-0.1"),
        ("LLM_RETRY_BASE_DELAY", "soon"),
        ("LLM_RETRY_BASE_DELAY", "nan"),
        ("LLM_RETRY_BASE_DELAY", "inf"),
    ],
)
def test_invalid_reliability_settings(name, value):
    with pytest.raises(ConfigError):
        load_settings(env={name: value})


def test_blank_usage_log_path_disables_logging():
    assert load_settings(env={"LLM_USAGE_LOG": ""}).usage_log_path is None


def test_get_provider_preset():
    """Provider presets still resolve base URLs (used as defaults)."""
    assert get_provider("openai").base_url == "https://api.openai.com/v1"
    with pytest.raises(UnknownProviderError):
        get_provider("no-such-provider")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
