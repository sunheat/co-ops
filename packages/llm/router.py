"""Simple model router: resolves "provider/model" names to configured clients."""

from .client import LLMClient
from .config import LLMSettings, load_settings
from .errors import ConfigError
from .schemas import ChatMessage, ChatResponse
from .usage import UsageLogger


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
        self._usage_logger = (
            UsageLogger(self._settings.usage_log_path)
            if self._settings.usage_log_path
            else None
        )

    def _resolve(self, name: str) -> tuple[LLMClient, str]:
        """Split "provider/model" and return (client, model)."""
        if "/" not in name:
            raise ConfigError(
                f"Model name must be in 'provider/model' format, got {name!r}"
            )
        provider, model = name.split("/", 1)
        provider = provider.lower()

        config = self._settings.get(provider)
        if provider not in self._clients:
            if not config.is_configured:
                raise ConfigError(
                    f"Provider '{provider}' is not configured; "
                    "set its API key / base URL in the environment (see .env.example)"
                )
            self._clients[provider] = LLMClient(
                api_key=config.api_key,
                base_url=config.endpoint,
                timeout=self._settings.timeout,
                provider=provider,
                max_retries=self._settings.max_retries,
                retry_base_delay=self._settings.retry_base_delay,
                usage_logger=self._usage_logger,
            )

        # Azure v1 API: the model field carries the deployment name, so fall
        # back to AZURE_OPENAI_DEPLOYMENT when no model is given.
        if not model and config.deployment:
            model = config.deployment
        return self._clients[provider], model

    def chat(
        self, name: str, messages: list[ChatMessage | dict], **kwargs
    ) -> ChatResponse:
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
