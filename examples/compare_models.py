"""Observe how "OpenAI-compatible" each provider really is (Day-5 learning script).

This is an *observation* script, not a test suite. For every configured provider
it logs three things so you can eyeball the differences yourself:

  1. request schema  -- the exact payload we POST to /chat/completions
                        (does everyone accept the same OpenAI shape?);
  2. response + usage -- the raw response keys and the `usage` object
                        (does the provider return prompt/completion/total tokens?);
  3. error format     -- fires ONE deliberately-bad request and prints the raw
                        error body (is it the OpenAI {"error": {"message", ...}}
                        shape, or something else?).

Streaming and tool calling are intentionally out of scope for today.

Providers with no key / base URL configured are skipped automatically, so the
same script keeps working as you add more providers to .env later. Today only
Gemini is expected to run end-to-end.

Usage:
    uv run --env-file .env python -m examples.compare_models
"""

import json

from packages.llm import (
    APIError,
    ChatMessage,
    LLMError,
    ModelRouter,
    UsageTracker,
    load_settings,
)

# provider -> model. Gemini first (today's target). Others stay listed but are
# skipped when unconfigured, so you can drop in an OpenAI sk-... key or a local
# Ollama endpoint later without editing this file.
MODELS = {
    # gemini-2.5-flash / -lite return 404 "no longer available to new users" on
    # freshly-created keys; gemini-flash-latest always tracks the newest flash.
    "gemini": "gemini-flash-latest",
    # OpenRouter free tier: models with a ":free" suffix. gpt-oss-20b is stable.
    "openrouter": "openai/gpt-oss-20b:free",
    "openai": "gpt-4o-mini",
    "deepseek": "deepseek-chat",
    "local": "qwen2.5",
}

QUESTION = "In two sentences, what are the trade-offs of RAG vs fine-tuning?"

# A model name no provider should recognise -- used to observe error formats.
BAD_MODEL = "definitely-not-a-real-model-xyz"

OPENAI_USAGE_FIELDS = ("prompt_tokens", "completion_tokens", "total_tokens")


def _dump(obj) -> str:
    """Pretty-print any JSON-ish object."""
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str)


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())


def observe_request_schema(model: str) -> None:
    """Print the canonical payload LLMClient.chat() builds and POSTs.

    Every provider receives this identical OpenAI Chat Completions shape; that
    sameness is exactly what "OpenAI-compatible" is supposed to buy us.
    """
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": QUESTION}],
        "temperature": 0.7,
    }
    print("  [request] POST /chat/completions")
    print(_indent(_dump(payload)))


def observe_response(router: ModelRouter, provider: str, model: str, tracker: UsageTracker) -> None:
    """Send a real request and inspect the response / usage fields."""
    messages = [ChatMessage(role="user", content=QUESTION)]
    response = router.chat(f"{provider}/{model}", messages, temperature=0.7)
    tracker.record(response.usage)

    answer = response.content.strip().replace("\n", " ")
    print(f"  [response] answer: {answer[:200]}")
    latency = f"{response.latency_ms:.0f} ms" if response.latency_ms is not None else "n/a"
    print(f"  [response] echoed model: {response.model!r} | latency: {latency}")
    print(f"  [response] top-level keys: {sorted(response.raw.keys())}")

    raw_usage = response.raw.get("usage")
    if not raw_usage:
        print("  [usage] MISSING -- provider omitted the usage object")
        return
    print("  [usage] raw object:")
    print(_indent(_dump(raw_usage)))
    missing = [f for f in OPENAI_USAGE_FIELDS if f not in raw_usage]
    verdict = "all OpenAI fields present" if not missing else f"MISSING: {', '.join(missing)}"
    extra = [k for k in raw_usage if k not in OPENAI_USAGE_FIELDS]
    print(f"  [usage] {verdict}" + (f" | extra keys: {extra}" if extra else ""))


def observe_error(router: ModelRouter, provider: str) -> None:
    """Fire one deliberately-bad request and print the raw error body."""
    print(f"  [error] firing a bad request (model={BAD_MODEL!r}) ...")
    try:
        router.chat(f"{provider}/{BAD_MODEL}", [ChatMessage(role="user", content="hi")])
    except APIError as e:
        print(f"  [error] APIError status={e.status_code}")
        print("  [error] raw body:")
        print(_indent(_dump(e.body)))
    except LLMError as e:
        print(f"  [error] {type(e).__name__}: {e}")
    else:
        print("  [error] no error raised (unexpected)")


def main() -> None:
    settings = load_settings()
    tracker = UsageTracker()

    with ModelRouter(settings) as router:
        for provider, model in MODELS.items():
            print(f"\n{'=' * 64}\n{provider} / {model}\n{'=' * 64}")

            if not settings.get(provider).is_configured:
                print("  [skipped] not configured -- set its key/base_url in .env")
                continue

            observe_request_schema(model)
            try:
                observe_response(router, provider, model, tracker)
            except LLMError as e:
                print(f"  [response] chat failed: {type(e).__name__}: {e}")
            observe_error(router, provider)

    print(f"\n{'=' * 64}")
    print(f"Total: {tracker.calls} calls, {tracker.total.total_tokens} tokens")


if __name__ == "__main__":
    main()
