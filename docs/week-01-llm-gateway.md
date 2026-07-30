# Week 01 — LLM Gateway

Goal of the week: build a universal LLM gateway layer (`packages/llm`) that talks
to any OpenAI-compatible model service through one unified interface.

## Why an LLM Gateway?

Everything built later in this project (RAG, agents, evals) needs to call models.
Without a gateway, every module would duplicate the same concerns: endpoint
differences, authentication, error handling, timeouts, retries, and cost
tracking. The gateway centralizes those concerns once, so upper layers only
depend on a single call — `llm.chat(messages, provider=..., model=...)` — and
switching providers becomes a configuration change instead of a code change.

## Module Structure

| File | Responsibility |
| --- | --- |
| `client.py` | `LLMClient`: HTTP client for the OpenAI Chat Completions API, with retry/backoff; module-level `chat()` as the unified high-level entry point |
| `config.py` | `ProviderConfig` / `LLMSettings` / `load_settings()`: load per-provider configuration from environment variables (including Azure and local endpoints) |
| `providers.py` | Presets for well-known providers (OpenAI, OpenRouter, DeepSeek, Gemini, Ollama) |
| `schemas.py` | Request/response dataclasses (`ChatMessage`, `ChatChoice`, `ChatResponse`, flat `LLMResponse`) |
| `usage.py` | `Usage` stats, `UsageTracker` accumulation, `UsageLogger` JSONL logging, `estimate_cost_usd()` |
| `errors.py` | Unified exception hierarchy (`LLMError` and subclasses, with per-type `retryable` flags) |
| `router.py` | `ModelRouter`: routes `provider/model` names to lazily created, reused clients |

## Supported Providers

Any OpenAI-compatible `/chat/completions` endpoint works. Configured presets:

| Provider | Notes |
| --- | --- |
| OpenAI | `OPENAI_API_KEY`, default base URL `https://api.openai.com/v1` |
| Azure OpenAI | v1 GA API (`https://<resource>.openai.azure.com/openai/v1`); the deployment name goes in the model field |
| Google Gemini | OpenAI-compatibility endpoint (`.../v1beta/openai`) |
| OpenRouter | Free-tier models available; unified multi-vendor access |
| DeepSeek | `https://api.deepseek.com/v1` |
| Local | Any local endpoint (Ollama, vLLM, ...); base URL only, no API key required |

## Quick Start

```bash
# 1. Copy the environment template and fill in your keys
cp .env.example .env

# 2. Run the tests
uv run pytest tests/ -v

# 3. Run the examples (-m keeps the repo root on sys.path, --env-file loads .env)
uv run --env-file .env python -m examples.chat_basic
uv run --env-file .env python -m examples.compare_models
```

## Deliverables

- [x] Universal `LLMClient` (httpx, works with any OpenAI-compatible endpoint)
- [x] Unified error handling (401/403, 429, other 4xx/5xx, timeout, connection, invalid-response — all typed)
- [x] Provider presets and environment-based configuration (OpenAI / Azure / Gemini / OpenRouter / DeepSeek / local)
- [x] API keys never appear in repr or logs (dataclass `repr=False`)
- [x] Simple routing with `provider/model` names, plus a shared default router behind `llm.chat()`
- [x] Retry with exponential backoff, `Retry-After` support, per-error-type retry decisions
- [x] Usage tracking: JSONL request log, token accounting, cost estimation for known models
- [x] Unit tests (client, config, reliability, usage, model comparison)

## Known Limitations

- No streaming (SSE) support
- No tool calling (function calling) schema
- Synchronous client only (no `AsyncLLMClient` yet)
- Price table is small and hand-maintained; unknown models get `estimated_cost_usd = None`
- `response_format="json"` requests JSON mode but the output is not schema-validated

## Next Steps

- Structured output: layer JSON-schema-validated responses on top of
  `response_format` (see `docs/llm-client-design-notes.md` for the plan)
- Streaming (SSE) support
- `AsyncLLMClient` for the future web service (`apps/api`)
