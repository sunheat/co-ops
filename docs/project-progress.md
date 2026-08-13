# Project Progress

This page summarizes what has been built in this repository so far. For
design rationale and detailed comparisons, see the other documents in this
directory.

## Week 1 — LLM Gateway

Delivered a synchronous, OpenAI-compatible LLM gateway in `packages/llm`
(see [LLM Gateway](llm-gateway.md)):

- A unified `llm.chat()` entry point backed by `LLMClient` (httpx), with
  provider presets and environment-based configuration for OpenAI, Azure
  OpenAI (v1 GA), Google Gemini (OpenAI-compatibility endpoint), OpenRouter,
  DeepSeek, and local endpoints (Ollama, vLLM, ...).
- A typed error hierarchy covering auth failures, rate limits, other HTTP
  errors, timeouts, connection errors, and invalid responses, each with a
  per-type retry decision.
- Retry with exponential backoff and `Retry-After` support, plus configurable
  timeout and retry settings.
- Observability: one JSONL record per completed call in `logs/usage.jsonl`,
  token accounting, and cost estimation for known models. API keys are kept
  out of `repr` output and logs.
- `ModelRouter` for `provider/model` routing with lazily created, reused
  clients, and a shared default router behind `llm.chat()`.
- Unit tests for the client, configuration, reliability behavior, usage
  logging, and model comparison.

In addition, the gateway was probed against several live providers to
document how "OpenAI-compatible" different endpoints actually are. The
observed differences (error payload shapes, auth requirements, model naming)
drove the multi-format error parsing and provider-specific configuration in
the client.

## Week 2 — Context Engineering, Structured Output, and Benchmarking

- `packages.prompt`: `PromptTemplate`, `ContextBlock`, and `MessageBuilder`
  produce normalized `system`/`user` messages. Developer instructions are
  folded into `system` so the role contract stays `system | user | assistant`,
  and all inputs are validated before a request is sent.
- `packages.context`: a four-layer `ContextBuilder` (system, retrieved
  evidence, memory, task) that emits a stable JSON-serializable payload.
  Retrieval is mocked at this stage; real retrieval arrives with the RAG
  phase.
- `packages.structured_output`: the same Pydantic schema drives both the
  JSON-schema output instruction and local validation. Invalid JSON, missing
  fields, or bad enum values trigger exactly one correction retry; transport
  retries remain the gateway's responsibility.
- `examples.context_engineering_compare`: a versioned prompt-quality
  benchmark comparing naive, structured, and context-engineered prompts over
  ten fixed evidence cases with typed scoring. See
  [Prompt Quality Benchmark](prompt-quality-benchmark.md). Note that the
  benchmark validates the evaluation process (format constraints, citations,
  stability), not a claim that context engineering always wins.
- `examples.litellm_spike`: a side-by-side look at LiteLLM versus the local
  gateway. The conclusion is a layering decision, documented in
  [LiteLLM Comparison](litellm-comparison.md): LiteLLM is a candidate for the
  transport layer when the project needs many native providers, streaming, or
  centralized spend governance, while prompt/context assembly, output
  contracts, and evaluation stay in the application layer.

## Current limitations

- The gateway is synchronous and buffered: no streaming (SSE) and no
  tool-calling schema yet.
- Retrieved context is mocked; real retrieval and citation validation are
  planned for the RAG phase.
- Cost estimation covers a small, hand-maintained price table; unknown
  models report `estimated_cost_usd = None`.
- `apps/api` and `apps/web` are placeholders for the upcoming service layer.

## Roadmap

- Phase 2 targets production RAG: embeddings, parsing and chunking,
  hybrid search, query rewriting, reranking, citation, and evaluation.
- Planned gateway work: streaming support and an async client for the future
  web service.
