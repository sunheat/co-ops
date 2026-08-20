# LiteLLM Spike: Comparison with This LLM Gateway

## Scope

This comparison evaluates the LiteLLM **Python SDK** against the
in-repository `packages.llm` gateway. It does not run the LiteLLM Proxy. That
distinction matters: the Proxy adds central authentication, virtual keys,
organization budgets, and a dashboard, while the SDK is a dependency used
directly by an application process.

The runnable companion is `examples/litellm_spike.py`. It makes one synchronous
OpenAI completion through LiteLLM:

```python
from litellm import completion

response = completion(
    model="openai/gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello"}],
)
```

Run it with an `OPENAI_API_KEY` in `.env`:

```console
uv run --env-file .env python -m examples.litellm_spike
```

## Comparison

| Dimension | This LLM Gateway | LiteLLM Python SDK | Practical consequence |
| --- | --- | --- | --- |
| Provider support | Six configured OpenAI-compatible presets: OpenAI, Azure OpenAI v1, Gemini, OpenRouter, DeepSeek, and a local endpoint. It sends the same `/chat/completions` request shape to each. | 100+ providers and provider-protocol translation behind an OpenAI-shaped interface. | Keep this gateway when OpenAI compatibility is a deliberate constraint; choose LiteLLM when native provider APIs are required. |
| Application call-site code | `llm.chat()` keeps ordinary calls small, but configuration, routing, and response normalization are owned in this repository. | A basic `completion()` call is three essential lines after import. Provider selection is encoded in `model`, such as `openai/gpt-4o-mini`. | LiteLLM reduces integration code; it does not remove the need to choose models, configure credentials, or set an application policy. |
| Implementation code and dependency | The currently relevant reliability path is 1,018 lines across `client.py`, `router.py`, `config.py`, `providers.py`, `errors.py`, and `usage.py`; every behavior is inspectable and testable here. | The spike adds a 25-line example and delegates provider adapters to the external `litellm` package. | LiteLLM is less code to maintain locally, but its behavior and release compatibility become an external dependency. |
| Streaming | Not implemented; `LLMClient` is synchronous and buffered. | Supported with `completion(..., stream=True)` and OpenAI-shaped chunks. | LiteLLM is the ready choice for token-by-token UI output. |
| Tool calling | No typed tool schema, tool-call parser, or execution loop. Passing raw extra fields is not a supported end-to-end feature. | Supports an OpenAI-compatible response shape that includes tool calls; provider adaptation is part of LiteLLM's purpose. The application still validates arguments and executes tools. | LiteLLM removes much adapter work, not the application's tool safety and orchestration work. |
| Error handling | Explicit typed errors, bounded retries for timeout/connection/408/409/429/5xx failures, `Retry-After` support, and raw provider error preservation. The exact retry policy is local and unit-tested. | Maps provider failures to OpenAI-compatible exception types. Its Router can add retries and fallbacks across deployments. | The gateway offers maximum policy control and observability of unusual payloads; LiteLLM offers a common error surface across more providers. |
| Cost tracking | Parses token usage, estimates cost from a small audited local price table, and appends privacy-conscious success/failure JSONL records. Unknown models return no estimate. | SDK supports application-level cost tracking and callbacks. The Proxy adds centralized spend tracking and per-project/user budgets. | The gateway's accounting is simple and local; LiteLLM scales further when centralized tracking and budgets are needed. |
| Maintenance cost | Small dependency surface, stable local contract, and no proxy service. New providers, streaming, tools, price updates, and edge-case adapters are this project's responsibility. | Broad provider coverage and mature features reduce feature-development work, but add package updates, provider-version changes, and potentially Proxy configuration/operations. | Prefer the gateway for a tightly controlled integration; prefer LiteLLM when feature breadth outweighs the value of owning the transport layer. |

## Evidence and limits

The LiteLLM capability statements above are based on its current official
[Getting Started documentation](https://docs.litellm.ai/), which documents the
Python SDK, streaming, normalized exceptions, callbacks, Router behavior, and
the separate Proxy feature set. The gateway statements are derived from the
current repository implementation, especially `packages/llm/client.py` and
`packages/llm/usage.py`.

This spike verifies installation and import behavior only. It intentionally
does not make a paid network call: doing so requires a user-provided API key
and would produce provider-specific cost and latency measurements rather than
a general SDK comparison.

## Recommendation

Do not replace `packages.llm` solely to shorten a single OpenAI-compatible
call: both interfaces keep that call small, and the local implementation
provides explicit policy control. Introduce LiteLLM behind the existing
`llm.chat()` facade if a future task needs native non-compatible providers,
streaming, tool calling, cross-provider fallback, or centralized cost
governance. That preserves the current caller contract while allowing a
measured migration.
