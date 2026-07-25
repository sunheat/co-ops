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
uv run python examples/chat_basic.py
```