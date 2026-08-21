# Runbook: Batch Job Failure or Timeout

## Purpose

Safely recover the nightly batch window after a job fails or overruns,
without corrupting downstream state. The nightly order is: `trade_import` →
`position_maintenance` → `margin_run` → `reconciliation` → invoicing.

## When To Use

- A `batch_jobs` row shows `FAILED` or a non-zero `exit_code`.
- A job overruns its slot and blocks the next job in the window.

## Prerequisites

- The `job_id` and `job_name` of the failed execution.
- The Batch Scheduler execution record for that `job_id`, including the
  venue, business date, and linked upstream and downstream job IDs. The
  `batch_jobs` row is intentionally unscoped and cannot establish this
  execution scope by itself.
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
   consumed it, stop downstream publication and mark each affected execution
   for rerun in `batch_jobs`. For an invoice-consuming path, before changing
   any invoice row or rendered artifact, determine the current payment
   evidence and the status immediately before the dispute, or immediately
   before the correction/retry when no dispute exists. Preserve paid or
   payment-state-unknown output until a credit, refund, or explicit payment
   transfer is recorded; a pre-action unpaid invoice is eligible for
   replacement only when current evidence shows no intervening payment. Until
   that safeguard passes, invalidate or quarantine only non-invoice derived
   output. Do not treat an output as safe merely because it was not published
   to clients. If partial `margin_results` exist and were not consumed, remove
   or replace them in the same transaction that prepares the retry. Never
   append a second result set to the same `(run_id, client_id)` keys.
4. For timeouts, determine whether the job is still doing real work before
   stopping it; a margin run near completion should usually be allowed to
   finish.

## Resolution Options

- For a failed `trade_import`, follow the failed-trade-import runbook. Do not
  replay the whole venue file after any rows have loaded; retain accepted
  trades and reprocess only rejects that were resolved, or an explicitly
  approved non-authoritative exception. Replaying accepted rows can collide
  with the `trades.trade_id` primary key.
- For a failed `position_maintenance`, keep accepted `trades` and correct the
  missing position input first, such as seeding `previous_close` for a new
  listing. If the attempt wrote partial position rows, replace them
  transactionally before writing the retry. Mark the scoped Scheduler
  execution `FAILED`; if no `batch_jobs` row was recorded, record the failed
  execution before retrying rather than inferring success from its absence.
  Reset and rerun `position_maintenance` through the normal Scheduler path
  for the same venue and business date, then verify the complete `positions`
  snapshot before starting `margin_run`.
- For a failed `margin_run`, preserve the failed execution metadata in the
  incident record. If the deterministic `margin_runs` row exists, in one
  transaction lock it, replace any partial `margin_results` rows, set
  `started_at` to the retry start time, clear `finished_at` to `NULL`, and mark
  the run `RUNNING`. If the failure occurred before that row was persisted, do
  not attempt to lock a missing row; after the scoped prerequisites are clear,
  start `margin_run` through the normal Scheduler creation path so it creates
  the deterministic row and marks it `RUNNING` before writing results. In both
  cases, set `finished_at` to the retry completion time and mark the run
  `COMPLETED` only after every client result is present.
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
- Batch jobs: `trade_import`, `position_maintenance`, `margin_run`,
  `reconciliation`, `invoicing`
- External record: Batch Scheduler execution record linking the job to its
  venue, business date, and dependency job IDs
