# Runbook: Batch Job Failure or Timeout

## Purpose

Safely recover the nightly batch window after a job fails or overruns,
without corrupting downstream state. The nightly order is: `trade_import` →
`margin_run` → `reconciliation` → invoicing.

## When To Use

- A `batch_jobs` row shows `FAILED` or a non-zero `exit_code`.
- A job overruns its slot and blocks the next job in the window.

## Prerequisites

- The `job_id` and `job_name` of the failed execution.
- Confirmation of which downstream jobs already ran for the same business
  date.

## Investigation Steps

1. Read the job log and record the failure class: input error, timeout, or
   infrastructure error.
2. Check `margin_runs` and `margin_results` for partially written state when
   `margin_run` fails; a run left in `RUNNING` must be marked `FAILED` before
   any restart.
3. Determine whether a downstream job consumed any partial output. If
   `Invoice Generator` or another documented downstream consumer already
   consumed it, stop downstream publication, mark each affected execution for
   rerun in `batch_jobs`, and invalidate or quarantine its derived output
   before replacing the margin results. Do not treat an output as safe merely
   because it was not published to clients. If partial `margin_results` exist
   and were not consumed, remove or replace them in the same transaction that
   prepares the retry. Never append a second result set to the same
   `(run_id, client_id)` keys.
4. For timeouts, determine whether the job is still doing real work before
   stopping it; a margin run near completion should usually be allowed to
   finish.

## Resolution Options

- For a failed `trade_import`, follow the failed-trade-import runbook. Do not
  replay the whole venue file after any rows have loaded; retain accepted
  trades and reprocess only rejects that were resolved, or an explicitly
  approved non-authoritative exception. Replaying accepted rows can collide
  with the `trades.trade_id` primary key.
- For a failed `margin_run`, preserve the failed execution metadata in the
  incident record. In one transaction, lock the existing deterministic
  `margin_runs` row, replace any partial `margin_results` rows, set
  `started_at` to the retry start time, clear `finished_at` to `NULL`, and mark
  the run `RUNNING`. Set `finished_at` to the retry completion time and mark
  the run `COMPLETED` only after every client result is present.
- After a failed job other than `trade_import` is cleanly reset, rerun it for
  the same business date. The retry must transactionally replace any
  unconsumed partial results before writing; the `(run_id, client_id)` key is
  not append-safe.
- If a downstream job consumed the partial results, replace the margin
  results only after its derived output is invalidated, then rerun that job
  and every later job in order. Confirm that no stale output remains before
  morning reporting.
- Otherwise, restart blocked downstream jobs in order after the failed job
  succeeds.
- If the window cannot be recovered, notify operations analysts and defer
  morning reporting per the escalation policy.

## Escalation

Escalate to service developers for repeated failures of the same job, and to
operations analysts whenever morning reporting is at risk.

## Related Artifacts

- Tables: `batch_jobs`, `margin_runs`
- Batch jobs: `trade_import`, `margin_run`, `reconciliation`, `invoicing`
