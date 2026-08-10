# Week 02 Day 05: Prompt Quality Benchmark

This exercise compares `naive`, `structured`, and `context_engineered` prompts on ten fixed evidence cases. The benchmark uses the versioned `context-engineering-benchmark-v2` artifact envelope and the `typed-answers-v3` rubric. It is an auditable learning fixture, not a general model leaderboard.

## Typed Answer Contract

Every prompt style receives identical evidence and the same output requirements. The styles differ only in role instructions, grounding guidance, and context organization.

An answer supported by the evidence uses a case-specific object:

```json
{
  "answer": {
    "status": "answered",
    "case_specific_field": "typed value"
  },
  "evidence": ["bare-source-id"]
}
```

When evidence is insufficient, the answer is a tagged alternative that does not require invented values:

```json
{
  "answer": {"status": "insufficient_evidence"},
  "evidence": ["bare-source-id"]
}
```

The scorer rejects unknown or missing fields, duplicate JSON members, non-standard JSON constants, wrong JSON types, non-finite decimals, malformed dates/times, and malformed timestamps. Decimal fields are finite base-10 strings and are compared as `Decimal`. Dates use `YYYY-MM-DD`; UTC times use `HH:MM:SSZ`. Datetimes use an RFC 3339 subset with required seconds, a known `Z` or numeric offset, at most six fractional digits, and no leap seconds or `-00:00` unknown-offset marker. Equivalent known-offset instants compare equal.

Citations must be non-empty, unique, known, exact, trimmed, bare source IDs. Missing required IDs, extra unknown IDs, bracketed IDs, and non-string IDs fail citation validation.

The ten expected conclusions are:

| Case | Typed conclusion |
| --- | --- |
| 01 | Reconciliation `2025-03-07T02:00:00Z`, import `2025-03-07T02:18:00Z`, cause `delayed_trade_import` |
| 02 | `deployable_now=false`, blocker `staging_incomplete` |
| 03 | `additional_spend_usd=40.00` |
| 04 | Change `database_migration`, mechanism `schema_mismatch` |
| 05 | Approval `false`, document `national_identity_card`, status `not_accepted` |
| 06 | Severity `P1` |
| 07 | `ENABLE_NEW_BILLING=false`, effect `disabled` |
| 08 | Unlock at `10:35:00Z` |
| 09 | Deletion date `2025-03-12` |
| 10 | Shipping charge `6.99` |

## Result And Run States

Each observed provider call has one result state:

- `ok`: the response is gradable; format, answer, evidence, and grounded metrics are booleans.
- `provider_error`: the call failed, was filtered, or returned no choice; quality metrics are `null`.
- `truncated`: the provider reached a token limit; quality metrics are `null`.

Interruption is a run-level state. A partial manifest records the active request ID and interruption timestamp; it does not fabricate a result row for a call that never completed. Persisted result files are atomically replaced with complete canonical JSONL snapshots, so an interrupted artifact contains only parseable rows.

## Metrics

`Answer correct`, `Format`, `Evidence cited`, and `Grounded` are separate. `Grounded` requires a correct typed answer and every required valid citation. Quality ratios use only gradable `ok` rows and display gradable/planned coverage beside each ratio. Provider failures, truncations, and missing calls are shown separately rather than being misreported as ordinary wrong answers.

Stability requires every planned repeat for a case/style group to exist, have status `ok`, and be grounded. Missing, failed, or truncated calls therefore cannot produce 100% stability. Usage reporting includes input, output, and total token means with planned coverage. Latency has the same coverage policy. Cost is shown only when every planned row for the style has valid cost data.

## Artifact And Provenance Model

Dry runs, live runs, regrades, and legacy imports use unique directories. Files are prepared in a hidden staging directory and published only after the artifact is internally consistent.

| File | Purpose |
| --- | --- |
| `manifest.json` | Rubric/schema versions, matrix, run state/timestamps, requested configuration, scorer source identity, model/status counts, source provenance, and file hashes |
| `requests.jsonl` | Canonical UTF-8/LF send order, deterministic request IDs, generation envelopes, messages, and inner hashes |
| `prompts.md` | Canonical human-readable rendering derived from the verified request catalog |
| `results.jsonl` | Canonical UTF-8/LF result snapshots with raw responses, actual model, finish reason, usage, latency, cost, and normalized scoring |
| `summary.md` | Deterministic complete/partial report generated from validated result rows |

The request matrix is always complete. A complete result matrix must equal it exactly; an explicitly accepted partial result matrix may be any unique subset, including repeat 2 without repeat 1 after shuffled execution. Request ordering uses seeded case/repeat blocks and rotating style order, balancing first/middle/last positions while remaining reproducible.

Every request inner hash is recomputed. File hashes are calculated from the exact bytes written, avoiding platform newline ambiguity. Regrade reads each source file into one immutable byte snapshot, verifies canonical serialization and all hashes/invariants, and only then creates a staged output artifact. The output contains its own request and prompt catalogs and can be regraded again. Source bytes are never modified.

Provider-error and truncated rows are strictly validated but have all persisted quality booleans normalized to `null`; regrade never trusts stale success flags. The source manifest is authoritative for repeat count and planned denominators. Missing rows always produce a partial regrade manifest.

Legacy prose results require `--legacy-import` and use a separate non-authoritative artifact schema. They never claim synthetic v2 request provenance. Only case 01 event-bound chronology is migrated: timestamps must bind directly to reconciliation/import events, chronology must be proven, and the delayed import must be the asserted cause. Legacy results are not mixed into v3 performance tables.

## Running

Generate an offline request catalog:

```bash
uv run python -m examples.context_engineering_compare \
  --dry-run --repeats 2 --seed 42
```

Run two repeats with explicit provider settings:

```bash
uv run --env-file .env python -m examples.context_engineering_compare \
  --provider azure --model model-router --repeats 2 \
  --max-tokens 512 --request-delay-seconds 6 --seed 42
```

Regrade a complete artifact:

```bash
uv run python -m examples.context_engineering_compare \
  --regrade-results artifacts/context_engineering_compare/run-v2-*/results.jsonl
```

Add `--allow-partial` only when intentionally auditing an incomplete v2 run. Prices must be supplied as a pair and all numeric CLI inputs must be finite and within their documented ranges. Invalid modes or values exit through argparse before creating an artifact.

## Authoritative Results

The historical free-prose scorer percentages are not comparable to the typed v3 rubric. The table below comes from the complete fixture at `tests/fixtures/context_engineering_compare/live-v3/`. Regrading that fixture reproduces its summary byte-for-byte.

- Run status: complete, 60/60 observed, 60/60 gradable
- Requested route: `azure/model-router`
- Actual model: `gpt-5.5-2026-04-24` for 60/60 calls
- Provider errors / truncations: 0 / 0
- Seed / repeats: 42 / 2

| Prompt | Answer correct | Format | Evidence cited | Grounded | Stability | Mean input tokens | Mean output tokens | Mean latency ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| naive | 100% (20/20) | 100% (20/20) | 100% (20/20) | 100% (20/20) | 100% (10/10) | 303.2 | 154.3 | 3932.0 |
| structured | 100% (20/20) | 100% (20/20) | 100% (20/20) | 100% (20/20) | 100% (10/10) | 310.2 | 161.1 | 3932.0 |
| context_engineered | 100% (20/20) | 100% (20/20) | 100% (20/20) | 100% (20/20) | 100% (10/10) | 345.2 | 151.1 | 3889.5 |

All quality columns have 20/20 gradable coverage per style. Cost is `n/a` because explicit Azure token pricing was not supplied. Raw response IDs were removed from the fixture; response text, actual model, usage, latency, finish reason, requests, and all scoring inputs remain intact.
