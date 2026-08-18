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
  evidence, in the reject report or operations audit record, then reprocess
  that reject. Do not delete and insert a second row: the primary key would
  still collide.
- Quarantine a row without reprocessing only when the venue confirms that it
  is a duplicate or otherwise non-authoritative record; retain that evidence
  with the reject report and keep the batch blocked until the exception is
  approved.
- After a successful import, verify that every remaining reject has an
  approved non-authoritative exception, then restart downstream jobs in order:
  `margin_run`, then `reconciliation`, then `invoicing` if it was skipped or
  blocked by the import failure. Check each downstream `batch_jobs` status
  before restarting so an already completed invoicing run is not repeated.

## Escalation

Escalate to service developers for format violations, and to operations
analysts if the window cannot be recovered before morning reporting.

## Related Artifacts

- Tables: `trades`, `clients`, `batch_jobs`
- Batch job: `trade_import`
