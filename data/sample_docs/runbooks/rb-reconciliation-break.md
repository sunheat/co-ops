# Runbook: Reconciliation Break

## Purpose

Triage breaks raised by the Position Reconciler, where client-level
positions aggregated by ACFS do not match the venue-published aggregate
positions. All breaks must be resolved before morning reporting.

## When To Use

- The `reconciliation` batch job raises one or more breaks for a venue and
  business date.
- A venue queries a position difference.

## Prerequisites

- The venue, business date, and instrument of the break.
- Read access to `positions` and `trades` for the affected date.
- Access to the operations adjustment audit record, which is maintained
  outside the ACFS schema; `positions` and `trades` do not store adjustment
  identifiers or audit metadata.

## Investigation Steps

1. Recompute the ACFS aggregate for the instrument: sum signed
   `positions.quantity` over all clients for the venue and date.
2. Compare the reconstruction with the venue aggregate from the venue file.
3. Look for manual position adjustments applied after the last venue
   submission, then check the operations adjustment audit record for the
   matching client, instrument, and date. If the external record is missing,
   treat it as an audit-control break and escalate before approving or
   correcting the position.
4. If the same instrument breaks on consecutive business dates, compare the
   break history across those dates and correlate it with one adjustment or
   venue submission before triaging each date independently.
5. Check whether late or rejected trades (see the failed-trade-import
   runbook) caused positions to lag the venue view.
6. If a single client explains the whole difference, open a ticket against
   the Position Reconciler with the client and instrument.

## Resolution Options

- Correct the client position only after recording the adjustment audit. Before
  rerunning reconciliation, stop Invoice Generator publication and the
  risk/compliance consumers. Before changing any affected invoice state,
  determine its status immediately before the dispute from the original
  invoice export or payment evidence; the current `invoices.status` may
  already be `DISPUTED` and must not be treated as proof that the invoice was
  unpaid. For a pre-dispute `PAID` invoice, require client services to record
  either a credit/refund for the original payment or an explicit payment
  transfer to the replacement before any later replacement. If that
  payment-handling evidence is missing, or the pre-dispute status cannot be
  evidenced, leave the invoice row unchanged, do not invalidate, quarantine,
  or cancel it, and escalate. Record a documented pre-dispute unpaid invoice
  as eligible for replacement.
  Invalidate or quarantine the affected `margin_results` and risk/compliance
  output derived from the old position. For an already `COMPLETED` margin run,
  in one transaction lock the existing `margin_runs` row, preserve its prior
  completion metadata in the incident record, replace its `margin_results`
  rows, set `started_at` to the rerun start time, clear `finished_at` to
  `NULL`, and mark the run `RUNNING`; rerun `margin_run` for the affected
  venue and date, and mark it `COMPLETED` only after every client result is
  present. Then rerun reconciliation. Rerun
  invoicing only after the payment handling is documented for a pre-dispute
  `PAID` invoice or a pre-dispute unpaid status is evidenced. Rerun other
  downstream consumers after the corrected margin results, and verify that no
  stale output remains before morning reporting.
- If the venue aggregate is wrong, file a venue query and record the break
  as pending-venue rather than adjusting ACFS data.

## Escalation

Escalate to operations analysts when breaks persist after one correction
cycle, or when a manual adjustment lacks an audit trail.

## Related Artifacts

- Code: `data/sample_codebase/java/margin-service/.../ReconciliationService.java`
- Tables: `positions`, `trades`, `batch_jobs`
- Batch job: `reconciliation`
- External record: operations adjustment audit record (not stored in the ACFS
  schema)
