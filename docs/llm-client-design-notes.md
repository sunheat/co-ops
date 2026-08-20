# LLM Client Design Notes

This document records the reasoning behind `packages/llm` and answers the
questions every gateway design has to face.

## Why build an LLM gateway at all?

Every downstream capability in this project (RAG, agents, and evaluation)
calls models. Doing that without a gateway means each caller re-implements
endpoint quirks, auth, error mapping, timeouts, retries, and usage accounting —
and does so inconsistently.
The gateway is the single place where those cross-cutting concerns live, so:

- callers write `llm.chat(messages, provider=..., model=...)` and nothing else;
- swapping providers (or falling back between them) is a config change;
- every call is observable in one JSONL log with tokens, latency, cost, and
  retry counts.

## Why not call the official OpenAI SDK directly?

1. **One dependency instead of N.** OpenAI, DeepSeek, Gemini, OpenRouter, and
   Ollama all expose OpenAI-compatible endpoints. Speaking plain HTTP via
   `httpx` covers all of them without stacking vendor SDKs (and their
   conflicting dependency pins).
2. **The SDK hides exactly what this project needs to observe.** Provider
   compatibility differences (error body shapes, missing fields, header
   behavior) are a first-class compatibility concern here; `APIError.raw_body`
   keeps each provider's response byte-for-byte for diagnostics, which SDKs
   normalize away.
3. **Control over the reliability policy.** Retry classification, backoff
   caps, `Retry-After` parsing, and failure logging are project-specific
   decisions; owning the HTTP layer makes them explicit and testable with
   `httpx.MockTransport` — no network, no mocks of a vendor SDK's internals.
4. **Protocol transparency.** The HTTP layer makes the request contract and
   its well-known failure modes explicit and testable.

## What is the boundary with LiteLLM?

LiteLLM is a production-grade proxy/SDK that already does routing, retries,
budgets, and 100+ provider translations. This gateway is intentionally not a
LiteLLM replacement:

| Concern | This gateway | LiteLLM |
| --- | --- | --- |
| Providers | OpenAI-compatible endpoints only | 100+ providers, protocol translation |
| Scope | One process, in-repo library | Standalone proxy server, key management, budgets |
| Naming | `provider/model` (same convention) | `provider/model` |
| Goal | Minimal, auditable code with a controlled scope | Production feature coverage |

The rule of thumb: features are added here only when they fit the project's
scope and acceptance criteria. If the project ever needs non-OpenAI-compatible
providers, enterprise key management, or org-level budgets, the right move is
to put LiteLLM (or a similar proxy) behind the same `llm.chat()` facade rather
than rebuild it.

## The OpenAI-compatible API in a nutshell

Everything the gateway does is built on one HTTP contract:

- **Request**: `POST {base_url}/chat/completions` with a Bearer token and a
  JSON body of `{"model": ..., "messages": [{"role": "system|user|assistant",
  "content": ...}], "temperature": ..., ...}`. Optional knobs like
  `max_tokens` and `response_format` ride in the same body.
- **Success response**: `{"id", "model", "choices": [{"index", "message":
  {"role", "content"}, "finish_reason"}], "usage": {"prompt_tokens",
  "completion_tokens", "total_tokens"}}`. The answer lives at
  `choices[0].message.content`.
- **Error response**: a non-2xx status plus (usually) an OpenAI-style body
  `{"error": {"message", "type", "code"}}`.

"OpenAI-compatible" means a provider accepts this request shape and returns
approximately these shapes — approximately, because observed deviations are
real: Ollama returns `{"error": "..."}` as a bare string, Gemini can return a
top-level JSON array for errors, some providers omit `usage`, and reasoning
models may return `content: null`. The client normalizes all of these
(`_extract_error_message`, `APIError.raw_body`, usage defaults) so callers see
one consistent surface.

## Azure OpenAI: what differs

Azure is the one "OpenAI-compatible" provider with real structural quirks
(full write-up in Chinese: `docs/openai-vs-azure.md`). With the v1 GA API the
client needs no Azure-specific code; the differences collapse into config:

- **Deployment name, not model name.** Azure's `model` field carries the
  *deployment name* you chose when deploying a model, not a public model name.
  Sending `gpt-4o-mini` to Azure yields 404 `DeploymentNotFound` unless a
  deployment with that exact name exists. `ModelRouter` falls back to
  `AZURE_OPENAI_DEPLOYMENT` when the model part of `azure/<model>` is empty.
- **Base URL prefix.** The v1 endpoint is
  `https://<resource>.openai.azure.com/openai/v1`; `ProviderConfig.endpoint`
  appends `/openai/v1` to `AZURE_OPENAI_ENDPOINT` idempotently. (httpx
  preserves path segments in `base_url` — a regression test guards this.)
- **What the v1 GA API removed.** The legacy API needed
  `/openai/deployments/<name>/...` URLs, an `api-version` query parameter, and
  an `api-key` header; v1 GA uses OpenAI-identical paths and standard Bearer
  auth, which is why one client covers both vendors.
- **Operational differences remain**: per-region model availability, quota
  attached to deployments, default content filtering (a `content_filter`
  finish reason OpenAI never sends), and the response echoing the underlying
  model name rather than the deployment name.

## Design principles

1. **Depend on the HTTP protocol, not on official SDKs.**
   All target services (OpenAI, Azure OpenAI, DeepSeek, Gemini, OpenRouter,
   Ollama) offer OpenAI-compatible endpoints, so calling `/chat/completions`
   with `httpx` covers every case.

2. **Dataclasses, not bare dicts.**
   Accessors like `ChatResponse.content` / `.message` free callers from
   `choices[0]["message"]["content"]` nesting; the `raw` field keeps the
   original payload for debugging. `LLMResponse` additionally flattens
   content, tokens, latency, cost, and attempts into one object for the
   high-level `llm.chat()` API.

3. **Configuration is separate from the client.**
   `load_settings()` reads every provider's `ProviderConfig` from the
   environment in one pass (aggregated into `LLMSettings`); `LLMClient` only
   knows how to send requests. Both are independently testable
   (`load_settings(env=...)` accepts an injected mapping).
   Each provider follows the same env-var scheme: a key variable
   (`OPENAI_API_KEY`, `AZURE_OPENAI_API_KEY`, `GEMINI_API_KEY`, ...) plus an
   optional base-URL override, with defaults coming from the presets in
   `providers.py`; `local` needs only `LOCAL_LLM_BASE_URL` and no key.
   Cross-provider behavior (`LLM_TIMEOUT`, `LLM_MAX_RETRIES`,
   `LLM_RETRY_BASE_DELAY`, `LLM_USAGE_LOG`) is configured once. A provider is
   usable only when `is_configured` is true; `ModelRouter` fails fast with a
   `ConfigError` pointing at `.env.example` otherwise, and observation scripts
   use the same flag to skip unconfigured providers instead of crashing.

4. **API keys never reach logs.**
   `ProviderConfig.api_key` is declared with `field(repr=False)`; nothing in
   the package prints a key, and failure log records contain no prompt or
   response content either.

5. **Typed errors instead of raw HTTPError, with retryability built in.**
   - `AuthenticationError` (401/403): key problem, retrying is pointless
   - `RateLimitError` (429): retryable, honors `Retry-After`
   - `LLMTimeoutError` / `LLMConnectionError`: retryable transport failures
   - `APIError` (other 4xx/5xx): retryable only for 408/409/429/5xx; carries
     `status_code`, normalized `body`, and untouched `raw_body`
   - `InvalidResponseError`: HTTP 200 but unparseable payload — never retried
   - `ConfigError` / `UnknownProviderError`: startup-time misconfiguration,
     fail fast

## Key decisions

### Why `provider/model` names?

Consistent with the OpenRouter / LiteLLM convention (e.g.
`deepseek/deepseek-chat`). `ModelRouter` uses the prefix to lazily create and
reuse one client per provider, so callers never manage client instances. The
module-level `llm.chat()` goes one step further and hides the router itself
behind a thread-safe, `atexit`-closed default instance.

### Why does `usage.py` stand alone?

Usage grew from a counter into cost estimation (`PRICE_TABLE`,
`estimate_cost_usd`) and structured JSONL logging (`UsageLogEntry`,
`UsageLogger`) — exactly the responsibility creep that was anticipated.
Keeping it out of `schemas.py` kept both files coherent.

### Timeouts and retries: why they matter, and the policy

LLM calls are slow network calls to busy services, so two failure modes are
routine rather than exceptional: requests that hang (a stuck connection would
otherwise block the caller forever — every request therefore carries a
timeout, default 60 s) and transient rejections (429 rate limits, 5xx
blips, dropped connections) where the retry-vs-fail decision decides whether
users see errors that would have vanished one second later.

Blind retry is as bad as no retry: retrying a 401 wastes time on a key that
cannot heal, and hammering a rate-limited endpoint amplifies the overload.
Hence the typed-error design: at most `max_retries` retries (default 2) after
the first attempt, only for errors whose type says `retryable`. Delay is the
provider's `Retry-After` (capped at 60 s) when present — respecting the
provider's own back-off signal — otherwise exponential backoff from
`retry_base_delay` capped at 8 s. Auth failures and invalid payloads are never
retried; every response and error records `attempts` so retry behavior is
observable in logs and tests.

### How usage and cost are recorded

Three cooperating pieces, all in `usage.py`:

1. **Per-call parsing**: the provider's `usage` object is parsed into a
   `Usage` dataclass on every response; providers that omit it yield `None`
   and token counts default to zero rather than failing.
2. **Cost estimation**: `estimate_cost_usd()` looks up `(provider, model)` in
   the hand-audited `PRICE_TABLE` and multiplies separate input/output rates;
   unknown pairs return `None` instead of a misleading guess.
3. **JSONL logging**: when `LLM_USAGE_LOG` is set (default
   `logs/usage.jsonl`), every completed call — success or failure — appends
   one `UsageLogEntry` record with provider, model, token counts, latency,
   estimated cost, attempts, and status. Failure records carry the error type
   but never prompt or response content. `UsageTracker` additionally
   accumulates in-process totals for scripts and sessions.

### Sync vs async

Only the synchronous `httpx.Client` exists today; it is enough for scripts,
tests, and notebooks. When `apps/api` becomes a real web service, an
`AsyncLLMClient` will be added (httpx supports both transports natively).

## Known limitations

- No streaming (SSE) support
- No tool calling (function calling) schema
- Synchronous client only
- `PRICE_TABLE` is hand-maintained and tiny; unknown provider/model pairs
  yield `estimated_cost_usd = None` instead of a guess
- `ModelRouter` is name-based only — no cost- or health-aware routing
- `response_format="json"` enables the provider's JSON mode but nothing
  validates the shape of what comes back

## Next: structured output plan

The building block already exists: `chat(response_format="json")` sends
`{"type": "json_object"}`. The plan for structured output on top of it:

1. Add a `chat_structured(messages, schema, ...)` helper that accepts a JSON
   Schema (or a dataclass/TypedDict converted to one).
2. Prefer the provider's native `json_schema` response format where supported
   (OpenAI `response_format={"type": "json_schema", ...}`); fall back to JSON
   mode plus a schema-in-prompt instruction elsewhere.
3. Validate the returned payload against the schema; on failure, raise a typed
   `StructuredOutputError` carrying the raw text, and optionally retry once
   with the validation error appended to the conversation.
4. Record validation failures in the usage log so provider compliance is
   measurable — the same observation-first approach used for error bodies.
