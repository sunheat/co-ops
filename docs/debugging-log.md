# Debugging Log

A running log of non-obvious debugging findings in this project. Each
entry records the symptom, root cause, and the rule that prevents a
repeat. Newest entries first.

## Entry format

```text
### [milestone] Short title
- Symptom:
- Investigation:
- Root cause:
- Resolution:
- Prevention:
```

---

### [LLM Gateway v0.1] Application-layer import cycles broke package loading

- **Symptom**: importing application modules failed intermittently with
  circular-import errors after the application modules were consolidated.
- **Investigation**: traced the import graph across `packages/` layers;
  higher-level helpers imported from modules that imported them back for
  convenience re-exports.
- **Root cause**: convenience re-exports created cycles between
  application layers once modules were merged into single packages.
- **Resolution**: broke the cycles by moving shared types to the lower
  layer and keeping re-exports one-directional
  (see commits `fix: break application import cycles`, `fix: preserve llm
  package exports`).
- **Prevention**: `tests/test_import_boundaries.py` provides fresh-process
  importability smoke checks for public package entry points; it does not
  inspect dependency directions or cycles, so those remain a review
  responsibility.

### [Provider compatibility] Newly issued Gemini key rejected for gemini-2.5-flash

- **Symptom**: a freshly provisioned Gemini API key returned access errors
  when calling `gemini-2.5-flash`, while other models on the same key
  worked.
- **Investigation**: ruled out key format and quota issues by testing
  other models with the same key.
- **Root cause**: model-level access is provisioned per model; the new key
  had not been granted access to that specific model.
- **Resolution**: switched the probe to a model available on the key.
- **Prevention**: provider probes in `compare_models.py` treat
  model-access errors as a configuration finding, not a client bug, and
  report the raw provider error body.

### [Structured output] Reasoning model returned null content

- **Symptom**: a reasoning model returned a response whose `content` field
  was `null`, which the client initially treated as a failure.
- **Investigation**: inspected the raw payload; `usage` was present and
  the request had succeeded.
- **Root cause**: some reasoning models emit their answer through
  reasoning channels and may return a null visible content field.
- **Resolution**: response handling now treats null content with present
  usage as a valid (possibly empty) response instead of an error.
- **Prevention**: the convention is recorded in the LLM client design
  notes; fixtures cover the null-content case.

### [Provider compatibility] Error bodies differ across providers

- **Symptom**: error handling assumed OpenAI-style error payloads, but
  other providers returned different shapes (flat message strings, nested
  errors, non-JSON bodies).
- **Investigation**: collected raw error responses from each configured
  provider via the error probes.
- **Root cause**: "OpenAI-compatible" endpoints diverge on error formats.
- **Resolution**: the client normalizes multiple error-body shapes and
  preserves the provider's raw error text for diagnostics.
- **Prevention**: compatibility tests assert that raw provider error text
  remains visible in raised errors.
