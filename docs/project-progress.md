# Project Status

This page summarizes the repository's current capabilities, known limits, and
planned engineering work. Design rationale and detailed comparisons are
covered by the other documents in this directory.

## Implemented capabilities

### LLM gateway

The repository provides a synchronous, OpenAI-compatible gateway in
`packages/llm`:

- A unified `llm.chat()` entry point backed by `LLMClient` (httpx), with
  provider presets and environment-based configuration for OpenAI, Azure
  OpenAI (v1 GA), Google Gemini (OpenAI-compatible endpoint), OpenRouter,
  DeepSeek, and local endpoints such as Ollama and vLLM.
- Typed errors for authentication failures, rate limits, other HTTP errors,
  timeouts, connection errors, and invalid responses, each with an explicit
  retry decision.
- Exponential backoff with `Retry-After` support, configurable timeouts and
  retry limits, token accounting, and cost estimation for known models.
- `ModelRouter` for `provider/model` routing with lazily created and reused
  clients, plus a shared default router behind `llm.chat()`.
- Unit tests covering client behavior, configuration, reliability, usage
  logging, and model comparison.

The gateway also includes provider compatibility probes. Observed differences
in error payloads, authentication requirements, usage fields, and model naming
drive the multi-format error parsing and provider-specific configuration.

### Prompt, context, and structured output

- `packages.prompt` provides `PromptTemplate`, `ContextBlock`, and
  `MessageBuilder` for normalized `system`/`user` messages.
- `packages.context` provides a four-layer `ContextBuilder` for system,
  retrieved evidence, memory, and task context.
- `packages.structured_output` generates JSON Schema instructions, parses and
  validates responses with Pydantic, and sends one correction request when
  parsing or schema validation fails.
- `examples.context_engineering_compare` provides a versioned prompt-quality
  benchmark with typed scoring for format constraints, citations, and
  stability.
- `examples.litellm_spike` compares the LiteLLM SDK with the local gateway;
  the resulting layering recommendation is documented in
  [LiteLLM Comparison](litellm-comparison.md).

## Current limitations

- The gateway is synchronous and buffered: streaming (SSE) and typed
  tool-calling schemas are not implemented.
- Retrieved context is currently mocked; production retrieval and citation
  validation are planned for the RAG service.
- Cost estimation covers a small, hand-maintained price table; unknown models
  report `estimated_cost_usd = None`.
- `apps/api` and `apps/web` are placeholders for the service layer.

## Planned engineering work

- Add document loading, embeddings, parsing, and chunking for the enterprise
  corpus.
- Add vector, keyword, and hybrid retrieval with query rewriting, reranking,
  citation, and evaluation.
- Add streaming support and an asynchronous client for the web service.
- Expose the retrieval pipeline through the planned API and web applications.
