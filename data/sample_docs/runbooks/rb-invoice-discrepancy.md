# Runbook: Invoice Discrepancy

## Purpose

Trace a disputed invoice total, or an externally rendered invoice line, back
to the margin runs and trades that produced it, and correct or confirm the
billed amount. The `invoices` table stores only the aggregate amount; invoice
lines are not stored in it.

## When To Use

- A client disputes an invoice line, e.g. `INV-202403-002`.
- An `invoices` row has status `DISPUTED`.

## Prerequisites

- The invoice identifier and the disputed period, e.g. `2024-02`.
- Read access to `invoices`, `margin_results`, `margin_runs`, and `trades`.
- The original invoice export or Invoice Generator trace log when the client
  disputes a particular line. Without that external artifact, the repository
  data can support only an aggregate-total investigation.
- The Invoice Generator's recorded margin-call calculation evidence for a
  disputed margin-call component, including the selected margin fields and
  business-date scope. Do not infer the billing rule from `margin_results`.
- The invoice currency and the Invoice Generator's recorded FX/conversion
  evidence for any multi-venue or non-venue-currency invoice.

## Investigation Steps

1. From the invoice export or generator trace, identify the disputed
   component: clearing fee or margin call, amount, and period. Do not infer a
   line item from `invoices.amount`. For a margin-call component, use the
   recorded generator evidence to identify the margin fields and business-date
   scope that were billed; if that evidence is unavailable, stop short of
   claiming that the amount is correct and escalate the evidence gap.
2. Verify the invoice row and its currency. Enumerate the margin runs for the
   period and venue from `margin_runs`, then group the client's
   `margin_results` rows by their `currency`. Never sum rows from different
   currencies before conversion.
3. For clearing fees, recompute the fee base from the client's `trades` in
   the period grouped by venue currency, and obtain the configured fee rule
   from the generator evidence.
   If no fee rule or line-level trace is available, stop short of claiming a
   recomputed fee and escalate the evidence gap.
4. Apply the recorded FX/conversion evidence to each currency group and
   compare the converted total with `invoices.amount` in the invoice currency.
   If the evidence is unavailable, do not compare a mixed-currency total or
   cancel/confirm the invoice; escalate the evidence gap. Note any reruns or
   corrected runs in the period, which can double-count if the invoice was
   built from stale results.
5. Check whether a margin mismatch investigation (see the margin-result-
   mismatch runbook) is open for the client; invoice disputes frequently
   share a root cause with margin mismatches.

## Resolution Options

- If the aggregate amount is wrong, cancel the invoice (`CANCELLED`) and
  reissue it; preserve any line-level breakdown in the external invoice
  artifact rather than inventing rows in `invoices`.
- If the aggregate amount is correct, reply to the client with the available
  trace from the invoice export or total to runs and trades, and restore the
  status recorded before the dispute (for example, `PAID` in TKT-2024-007),
  rather than hard-coding `ISSUED`. If the prior status is not evidenced,
  leave the row `DISPUTED` and escalate.

## Escalation

Escalate to client services with the full trace when the client contests the
recomputed figure.

## Related Artifacts

- Tables: `invoices`, `margin_results`, `margin_runs`, `trades`
