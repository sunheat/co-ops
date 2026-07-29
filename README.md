# Co-Ops

A production-style enterprise GenAI system for codebase-aware RAG,
agentic workflow, MCP tools, evaluation, observability, and cost-aware model routing.

## Project Structure

```
co-ops/
  packages/
    llm/                  # Universal LLM gateway (OpenAI-compatible)
      client.py           # LLMClient: HTTP client for /chat/completions
      config.py           # ProviderConfig / LLMSettings / load_settings()
      providers.py        # Provider presets (OpenAI, DeepSeek, Ollama, ...)
      schemas.py          # Request/response dataclasses
      usage.py            # Token usage tracking
      errors.py           # Exception hierarchy
      router.py           # ModelRouter: provider/model routing
  tests/                  # Unit tests
  examples/               # Runnable examples
  docs/                   # Weekly notes and design docs
```

## Quick Start

```bash
cp .env.example .env      # fill in your API keys
uv run pytest tests/ -v   # run tests
uv run --env-file .env python -m examples.chat_basic
```

## Reliability and usage logs

The shared client applies timeout + retry settings and appends one JSON record
per completed call to `logs/usage.jsonl` by default:

```dotenv
LLM_TIMEOUT=60
LLM_MAX_RETRIES=2
LLM_RETRY_BASE_DELAY=0.5
LLM_USAGE_LOG=logs/usage.jsonl
```

See [Day 06 notes](docs/day-06-reliability-and-usage.md) and the
[usage log example](examples/usage_log.jsonl).
