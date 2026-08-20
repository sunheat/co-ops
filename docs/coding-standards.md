# Coding Standards

Public engineering and content conventions used across this repository.

## Language

- Identifiers, code comments, docstrings, log messages, and error messages
  are written in English.
- Public documentation under `README.md` and `docs/`, and corpus content
  under `data/`, are written in English.

## Python

- Toolchain: `uv` for environment and dependency management, `pytest` for
  tests, `ruff` for linting. Run tests with `uv run pytest`.
- Type hints are expected on public functions; Pydantic models are used
  for configuration and structured LLM output.
- Packages live under `packages/` (`llm`, `prompt`, `context`,
  `structured_output`, `rag`, `evals`, ...). Import boundaries between
  packages are enforced by `tests/test_import_boundaries.py`; application
  layers must not create import cycles.
- Public APIs prefer a unified high-level entry point (e.g. `llm.chat()`)
  returning flat response objects rather than nested provider payloads.
- Provider-dependent code paths must degrade gracefully: when a provider
  is not configured, tests are skipped rather than failed, and runtime
  errors surface the provider's original error body without leaking
  credentials.
- Reasoning models may return `content: null`; response handling treats a
  null content with present usage as a valid empty response, not an error.
- Secrets are read from environment variables only; usage logs contain
  metadata and omit prompt and response content. Provider error bodies may
  contain provider-supplied content and must not be logged without review or
  sanitization.

## Commits and Branches

- Commit messages are English, Conventional Commits style
  (`feat:`, `fix:`, `docs:`, `ci:`, ...).
- Deliberately partial changes state their known limitations in the commit
  body.
- Feature branches are named `feature/<scope>`; each branch maps to one PR.

## Mock Corpus Content (`data/`)

- All corpus content is fictional and self-consistent. Naming conventions
  (client IDs, ticket IDs, run IDs, venues, currencies) are defined once
  in `data/mock_domain/README.md` and reused everywhere.
- Corpus documents are written in-world without repository-planning,
  author-workflow, portfolio, or fixture meta commentary. Module-level
  READMEs may document technical fixture limitations explicitly.
- Structured fixtures (JSON, SQL) must be machine-checkable: JSON files
  must parse, and sample figures must be recomputable from the documented
  business rules.

## Tests

- Every feature ships with a minimal test or an explicit manual
  verification note.
- Tests never require live provider credentials; live-provider examples
  live under `examples/` and are run manually.
- Test fixtures that capture provider responses must sanitize key-like
  fields before committing.
