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
5. For a historical run, obtain the venue rate and calculation-version
   evidence recorded by that execution, such as an execution trace or a
   versioned configuration snapshot. Do not use the current `MarginCalculator`
   constants as proof of the rate used by an older run. If the run-time
   evidence or versioned rate is unavailable, stop short of confirming a
   mismatch or triggering a rerun and escalate the evidence gap.

## Resolution Options

- For a `COMPLETED` run whose inputs or results must be corrected, do not
  start a second calculation with the same date and venue. `MarginCalculator`
  deterministically reuses the existing `run_id`, and `(run_id, client_id)`
  is the primary key of `margin_results`.
- First stop Invoice Generator publication and notify the risk & compliance
  consumers, invalidate or quarantine any derived output that used the old
  results, and record the affected executions for rerun. Reconciliation does
  not consume `margin_results`; include it only if the correction also changes
  the underlying positions. Preserve the prior completion metadata in the
  incident record. In one transaction, lock the existing run, replace its
  `margin_results` rows, set `started_at` to the rerun start time, clear
  `finished_at` to `NULL`, and mark the run `RUNNING`; complete the run and
  set it back to `COMPLETED` only after every client result is present.
- Before rerunning invoicing, determine each affected invoice's status
  immediately before the dispute from the original invoice export or payment
  evidence; the current `invoices.status` may already be `DISPUTED` and must
  not be treated as proof that the invoice was unpaid. For a pre-dispute
  `PAID` invoice, require client services to record either a credit/refund for
  the original payment or an explicit payment transfer to the replacement. If
  that payment-handling evidence is missing, or the pre-dispute status cannot
  be evidenced, do not cancel and reissue the invoice; leave it unchanged and
  escalate. Rerun invoicing only after the payment handling is documented or a
  pre-dispute unpaid status is evidenced. Rerun reconciliation only when the
  underlying positions changed, and verify that no stale downstream output
  remains before morning reporting.
- If the venue figure is authoritative, raise a correction request and
  document the adjustment before morning reporting.

## Escalation

Escalate to margin operations if the mismatch exceeds the venue tolerance or
if morning reporting is at risk.

## Related Artifacts

- Code: `data/sample_codebase/java/margin-service/.../MarginCalculator.java`
- Tables: `margin_runs`, `margin_results`, `positions`, `clients`
- Batch job: `margin_run`
