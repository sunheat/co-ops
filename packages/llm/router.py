"""Simple model router: resolves "provider/model" names to configured clients."""

from .client import LLMClient
from .config import LLMSettings, load_settings
from .errors import ConfigError
from .schemas import ChatMessage, ChatResponse


class ModelRouter:
    """
    Routes chat requests to the right provider based on a "provider/model" name.

    Clients are created lazily (one per provider) and reused across calls.

    Example:
        router = ModelRouter()
        response = router.chat(
            "deepseek/deepseek-chat",
            [ChatMessage(role="user", content="Hello!")],
        )
    """

    def __init__(self, settings: LLMSettings | None = None):
        self._settings = settings if settings is not None else load_settings()
        self._clients: dict[str, LLMClient] = {}

    def _resolve(self, name: str) -> tuple[LLMClient, str]:
        """Split "provider/model" and return (client, model)."""
        if "/" not in name:
            raise ConfigError(
                f"Model name must be in 'provider/model' format, got {name!r}"
            )
        provider, model = name.split("/", 1)
        provider = provider.lower()

        if provider not in self._clients:
            config = self._settings.get(provider)
            if not config.is_configured:
                raise ConfigError(
                    f"Provider '{provider}' is not configured; "
                    "set its API key / base URL in the environment (see .env.example)"
                )
            self._clients[provider] = LLMClient(
                api_key=config.api_key,
                base_url=config.endpoint,
                timeout=self._settings.timeout,
            )
        return self._clients[provider], model

    def chat(self, name: str, messages: list[ChatMessage | dict], **kwargs) -> ChatResponse:
        """Send a chat request to the provider encoded in the model name."""
        client, model = self._resolve(name)
        return client.chat(model=model, messages=messages, **kwargs)

    def close(self):
        """Close all underlying clients."""
        for client in self._clients.values():
            client.close()
        self._clients.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
