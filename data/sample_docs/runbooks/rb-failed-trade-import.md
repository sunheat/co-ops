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

- Fix or quarantine the offending rows, then rerun the import for the batch.
- After a successful import, restart downstream jobs in order: `margin_run`,
  then `reconciliation`, per the batch-job-failure runbook.

## Escalation

Escalate to service developers for format violations, and to operations
analysts if the window cannot be recovered before morning reporting.

## Related Artifacts

- Tables: `trades`, `clients`, `batch_jobs`
- Batch job: `trade_import`
