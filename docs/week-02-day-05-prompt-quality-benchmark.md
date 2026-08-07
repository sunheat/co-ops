# Week 02 Day 05: Prompt Quality Benchmark

This exercise compares `naive`, `structured`, and `context_engineered` prompts on ten fixed evidence cases. New runs use the versioned `context-engineering-benchmark-v2` artifact format and a typed answer contract. The benchmark is an audit fixture, not a general knowledge leaderboard.

## V2 Contract

Every style receives the same case-specific output shape:

```json
{"answer": {"insufficient_evidence": false, "...typed fields...": "..."}, "evidence": ["bare-source-id"]}
```

The `answer` object has exactly the fields declared in the case schema. Values are validated as booleans, exact enums, decimals, RFC 3339 UTC-aware instants, UTC times, or ISO dates. Decimal comparison uses `Decimal`; timestamp comparison uses timezone-aware instants. Free-form prose, keyword matching, negation detection, and contradictory-term heuristics are not part of v2 scoring.

Each case includes an explicit `insufficient_evidence` representation. It is valid schema output but is not correct for this intentionally sufficient fixture. Citations must be non-empty, known, exact, bare source IDs. Bracket-wrapped IDs, whitespace-wrapped IDs, unknown IDs, and missing required IDs fail citation validation.

The ten expected typed conclusions are:

| Case | Typed conclusion |
| --- | --- |
| 01 | Reconciliation `02:00Z`, import `02:18Z`, cause `delayed_trade_import` |
| 02 | `deployable_now=false`, blocker `staging_incomplete` |
| 03 | `additional_spend_usd=40.00` |
| 04 | Change `database_migration`, mechanism `schema_mismatch` |
| 05 | Approval `false`, document `national_identity_card`, status `not_accepted` |
| 06 | Severity `P1` |
| 07 | `ENABLE_NEW_BILLING=false`, effect `disabled` |
| 08 | Unlock at `10:35:00Z` |
| 09 | Deletion date `2025-03-12` |
| 10 | Shipping charge `6.99` |

## Metrics

`Answer correct`, `Format`, `Evidence cited`, and `Grounded` are separate. `Grounded` requires a valid typed answer and all required valid citations. Denominators come from the planned Cartesian matrix of 10 cases, 3 styles, and `N` contiguous repeat IDs, not from the number of observed rows.

Summaries report expected, completed, failed, truncated, interrupted, and missing calls. A partial matrix requires an explicit partial policy and cannot appear as a complete 100% benchmark. Stability is the fraction of case/style groups with one grounded result for every repeat ID; it is not reported for one repeat. Usage and latency means include reported/expected coverage. Cost remains `n/a` unless every included row has valid cost data.

## Artifacts and Provenance

Each ordinary live run is written to a new `run-v2-*` directory below `--output-dir`; an existing directory is never reused. Each run contains:

| File | Purpose |
| --- | --- |
| `manifest.json` | Schema/rubric versions, run ID, timestamps, provider/model configuration, seed, matrix, and request catalog hash |
| `requests.jsonl` | Exact send order, stable request IDs, request hashes, and serialized messages |
| `results.jsonl` | Incrementally flushed responses, response ID, actual model, finish reason, status, typed checks, usage, latency, and cost |
| `summary.md` | Generated metric table |

The request order is deterministically shuffled by `--seed`. The seed is recorded, and the full actual order is retained. Results are flushed after every provider call. Provider errors remain rows; length-limited responses are `truncated`; interruption leaves completed rows recoverable and marks the manifest partial.

Regrading reads and verifies the source manifest and the actual SHA-256 of `requests.jsonl`, then writes a new `regrade-v2-*` directory. It preserves the source provider, requested model, temperature, token, retry, delay, seed, repeat, and pricing configuration rather than accepting replacement CLI labels. It never overwrites source requests, prompts, raw responses, or the source manifest. Regrade validates the matrix plus every result request ID/hash and recomputes scoring rather than trusting persisted booleans. An unversioned legacy `results.jsonl` requires `--legacy-import`; imported records are explicitly `legacy` and non-authoritative. Legacy case 01 migration accepts only proven timestamp order, including `02:00 UTC` followed by `02:18 UTC`, and rejects reversed, equal, or negated causal claims.

## Running

Generate an offline catalog:

```bash
uv run python -m examples.context_engineering_compare --dry-run --seed 42
```

Run two repeats with explicit provider settings:

```bash
uv run --env-file .env python -m examples.context_engineering_compare \
  --provider gemini --model gemini-flash-latest --repeats 2 \
  --max-tokens 512 --request-delay-seconds 6 --seed 42
```

Prices must be supplied together and must be finite and non-negative. CLI validation rejects invalid repeats, token limits, retries, delay, prices, and temperatures with argparse exit code 2. JSON artifact serialization uses `allow_nan=False`.

The historical prose-scorer table is intentionally not reproduced here. It is legacy evidence and is not comparable to v2 percentages. A publishable table requires a complete v2 fixture containing its manifest, requests, responses/results, and generated summary.
