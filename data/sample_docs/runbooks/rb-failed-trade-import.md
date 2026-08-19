# Runbook: Failed Trade Import

## Purpose

Recover the nightly window when the Trade Importer rejects a venue file.
Downstream jobs (margin run, reconciliation, invoicing) are blocked until the
import completes, so this runbook is time-critical.

## When To Use

- `batch_jobs` shows `trade_import` with status `FAILED` or a non-zero
  `exit_code`.
- The reject report contains records for the current import batch, e.g.
  `IMP-20240315-SGX`.

## Prerequisites

- Access to the reject report of the failed batch.
- The venue file that failed, and the `batch_jobs.job_id` of the attempt.
- The Batch Scheduler execution record for that `job_id`, including the
  venue, business date, import batch, and linked downstream job IDs. The
  `batch_jobs` row is intentionally unscoped and cannot identify those
  relationships by itself.

## Investigation Steps

1. Classify the rejects from the reject report:
   - **Duplicate trade IDs**: the same `trade_id` already exists in
     `trades`, often after a venue resend.
   - **Unknown client codes**: the file references a `client_id` that is not
     registered in `clients`.
   - **Format violations**: changed column layout or malformed values.
2. For duplicates, confirm with the venue whether the file is a resend and
   which copy is authoritative.
3. For unknown client codes, check whether client registration is pending;
   if so, register the client before reprocessing.
4. For format violations, treat as a venue file format change incident and
   notify service developers.

## Resolution Options

- Fix the offending rows and reprocess every reject before unblocking the
  batch. Quarantine alone is not sufficient for unknown-client or malformed
  records because it can omit real exposure from positions and margin.
- When the venue confirms that the incoming copy of a duplicate `trade_id` is
  authoritative, lock the existing `trades` row and atomically replace its
  incoming fields (`client_id`, `venue`, `instrument`, `quantity`, `price`,
  `trade_date`, and `import_batch`) while retaining the same `trade_id`. Record
  the prior and replacement values, together with the venue's authority
  evidence, in the reject report or operations audit record, then mark the
  reject resolved after the replacement succeeds. Do not send that reject
  through the importer again, and do not delete and insert a second row: the
  primary key would still collide.
- If the replacement changes a business or financial field, identify both the
  original and replacement venue/date/client/instrument scopes. Invalidate and
  rebuild the affected `positions` rows, then invalidate and recompute the
  downstream `margin_results` and risk/compliance output derived from the old
  trade values. Stop invoice publication and apply the paid-invoice
  payment-handling safeguards before changing or replacing any affected
  invoice. Rerun `margin_run`, `reconciliation`, and `invoicing` for each
  affected scope in order; do not limit the recovery to the currently failed
  import batch.
- Quarantine a row without reprocessing only when the venue confirms that it
  is a duplicate or otherwise non-authoritative record; retain that evidence
  with the reject report and keep the batch blocked until the exception is
  approved.
- After a successful import, verify that every remaining reject has an
  approved non-authoritative exception. Use the Batch Scheduler execution
  record for the same venue, business date, and import batch to identify the
  linked downstream jobs, then restart them in order: `margin_run`, followed
  by `reconciliation`, then `invoicing` if it was skipped or blocked by the
  import failure. Check only those linked `batch_jobs` statuses before
  restarting so another venue's completed invoicing run is not mistaken for
  this batch.

## Escalation

Escalate to service developers for format violations, and to operations
analysts if the window cannot be recovered before morning reporting.

## Related Artifacts

- Tables: `trades`, `clients`, `batch_jobs`
- Batch job: `trade_import`
- External record: Batch Scheduler execution record linking the import to its
  venue, business date, import batch, and downstream job IDs
