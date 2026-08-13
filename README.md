# Co-Ops

A production-style enterprise GenAI learning project covering an
OpenAI-compatible LLM gateway, prompt and context engineering, structured
output, evaluation, observability, and cost-aware model routing.

## Week 2 module boundaries

Week 2 keeps transport concerns separate from application-layer decisions:

```text
packages/
  llm/                 # Low-level gateway: HTTP, providers, routing, errors, usage
  prompt/              # PromptTemplate, ContextBlock, MessageBuilder
  context/             # Four-layer ContextBuilder and retrieved-chunk contract
  structured_output/   # Pydantic schemas, JSON parsing, one correction retry
  rag/                 # Future RAG components; current context exports are compatible aliases
```

The application packages depend on the stable data contracts in `packages.llm`
but do not own provider configuration or HTTP behavior. The compatibility
modules `packages.llm.prompt`, `packages.llm.structured_output`, and
`packages.rag.context` remain as import shims for earlier Week 2 examples.
New code should use the four explicit package boundaries above.

## Quick start

Install the locked dependencies with [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

Run the complete test suite:

```bash
uv run pytest -q -p no:cacheprovider
```

If the default uv cache is not writable on Windows, use the repository-local
cache instead:

```powershell
uv --cache-dir .local\uv-cache run pytest -q -p no:cacheprovider
```

Run the offline Week 2 examples from the repository root:

```bash
uv run python -m examples.prompt_building
uv run python -m examples.context_engineered_prompt
uv run python -m examples.structured_output
```

Generate the offline prompt-quality benchmark catalog without making a model
call:

```bash
uv run python -m examples.context_engineering_compare --dry-run --repeats 2 --seed 42
```

The live gateway reads provider settings from environment variables. For a
live call, create a local `.env` with the required provider credentials and
run an example with `uv run --env-file .env ...`. Do not commit credentials or
generated live artifacts.

## Current functionality

- `packages.llm` provides a synchronous OpenAI-compatible chat client,
  provider presets, model routing, typed errors, bounded retry behavior,
  timeout handling, and JSONL usage/cost logging.
- `packages.prompt` renders reusable templates and builds normalized
  `system`/`user` messages. A developer instruction is folded into `system`
  so the role contract remains `system | user | assistant`.
- `packages.context` builds the four Context Engineering layers:
  system, retrieved evidence, memory, and task. Retrieval is mocked in Week 2.
- `packages.structured_output` generates a JSON Schema instruction, parses the
  response, validates it with Pydantic, and sends one correction request when
  JSON parsing or schema validation fails.
- `examples.context_engineering_compare` compares naive, structured, and
  context-engineered prompts with versioned request/result artifacts and
  typed scoring. See [the benchmark notes](docs/prompt-quality-benchmark.md).
- `examples.litellm_spike` demonstrates the LiteLLM SDK separately from the
  local gateway. See [the LiteLLM comparison](docs/litellm-comparison.md).

## LiteLLM boundary

The local gateway is intentionally a small learning and application-specific
abstraction. It owns the contract this repository needs: provider settings,
the OpenAI-compatible request/response shape, typed errors, retry policy,
usage records, and the `llm.chat()` call surface.

LiteLLM becomes attractive when the project needs native APIs from many
providers, streaming, tool-call adaptation, cross-provider fallbacks, or
centralized spend governance. Those capabilities are expensive to maintain in
the local gateway and are not the learning target of this repository. A future
migration can put LiteLLM behind the existing gateway facade or router instead
of changing every application call site.

The following logic stays in the application layer even after such a
migration:

- prompt templates, message ordering, role policy, and output instructions;
- Context Engineering assembly and evidence/memory/task precedence;
- Pydantic schemas, JSON parsing, validation, correction retry, and refusal
  policy for invalid or insufficient output;
- domain-specific tool orchestration, citation/grounding checks, benchmark
  rubrics, and acceptance criteria.

For a summary of what has been built so far, read
[the project progress notes](docs/project-progress.md).

## Reliability and usage logs

The shared client applies timeout and retry settings and appends one JSON
record per completed call to `logs/usage.jsonl` by default:

```dotenv
LLM_TIMEOUT=60
LLM_MAX_RETRIES=2
LLM_RETRY_BASE_DELAY=0.5
LLM_USAGE_LOG=logs/usage.jsonl
```

See [the LLM gateway overview](docs/llm-gateway.md) and the
[usage log example](examples/usage_log.jsonl).
