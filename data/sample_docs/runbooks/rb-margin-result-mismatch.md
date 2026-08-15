# Runbook: Margin Result Mismatch

## Purpose

Investigate cases where the ACFS aggregate margin for a venue does not equal
the venue-published figure, or where a client's reconstructed margin does not
match the stored `margin_results` rows.

## When To Use

- A venue reports a margin figure that differs from the ACFS margin run.
- A client disputes a margin call.
- Reconciliation of margin totals raises a break.

## Prerequisites

- Read access to `margin_runs`, `margin_results`, `positions`, and `clients`.
- The run identifier, e.g. `MR-20240315-SGX`, and the affected client, e.g.
  `ACME-102`.

## Investigation Steps

1. Confirm the run state: `margin_runs.status` must be `COMPLETED`. A run
   still `RUNNING` or `FAILED` explains partial figures; handle via the
   batch-job-failure runbook first.
2. Reconstruct the client margin from `positions` for the run date and venue
   and compare with the `margin_results` row for the same run and client.
3. Check `clients.margin_model`: a `PORTFOLIO` account receives a
   diversification offset that venues may not apply. This is a frequent root
   cause of aggregate mismatches.
4. Verify the position snapshot: late trade imports or manual adjustments
   after the margin run change `positions` without retriggering the run.
5. Confirm the venue rate used matches the configured rate in
   `MarginCalculator` for the venue.

## Resolution Options

- Rerun the margin calculation for the venue after correcting inputs.
- If the venue figure is authoritative, raise a correction request and
  document the adjustment before morning reporting.

## Escalation

Escalate to margin operations if the mismatch exceeds the venue tolerance or
if morning reporting is at risk.

## Related Artifacts

- Code: `data/sample_codebase/java/margin-service/.../MarginCalculator.java`
- Tables: `margin_runs`, `margin_results`, `positions`, `clients`
- Batch job: `margin_run`
