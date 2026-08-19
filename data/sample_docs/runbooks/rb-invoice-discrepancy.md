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
2. Verify the invoice row and its currency. From the generator evidence,
   identify every venue and run/date scope included in the invoice, then
   enumerate the matching `margin_runs` rows for each covered venue. If the
   covered venues cannot be established, stop and escalate rather than
   reconstructing a partial total. Group the client's `margin_results` rows
   by their `currency`; never sum rows from different currencies before
   conversion.
3. For clearing fees, recompute the fee base from the client's `trades` in
   the period grouped by venue currency, and obtain the configured fee rule
   from the generator evidence.
   If no fee rule or line-level trace is available, stop short of claiming a
   recomputed fee and escalate the evidence gap.
4. Apply the recorded FX/conversion evidence to each currency group. For the
   disputed component, compare the converted recomputed amount with the
   corresponding line in the invoice export or generator trace; do not compare
   a single component directly with `invoices.amount`. Compare with
   `invoices.amount` only after reconstructing every billed component for the
   period and converting them into the invoice currency. If the evidence is
   unavailable, do not compare a mixed-currency total or cancel/confirm the
   invoice; escalate the evidence gap. Note any reruns or corrected runs in
   the period, which can double-count if the invoice was built from stale
   results.
5. Check whether a margin mismatch investigation (see the margin-result-
   mismatch runbook) is open for the client; invoice disputes frequently
   share a root cause with margin mismatches.

## Resolution Options

- If the aggregate amount is wrong, preserve any line-level breakdown in the
  external invoice artifact rather than inventing rows in `invoices`. First
  determine the invoice's status immediately before the dispute from the
  original invoice export or payment evidence; the current `invoices.status`
  may already be `DISPUTED` and must not be treated as proof that the invoice
  was unpaid. For a pre-dispute `PAID` invoice, do not cancel and reissue
  until client services records either a credit/refund for the original
  payment or an explicit payment transfer to the replacement. If that
  payment-handling evidence is missing, or the pre-dispute status cannot be
  evidenced, leave the invoice status unchanged and escalate. Once the
  payment handling is documented, obtain current payment evidence immediately
  before cancellation or reissue. Treat any payment received after the
  dispute opened as paid: do not cancel or reissue until a credit, refund, or
  payment transfer is recorded. A pre-dispute unpaid invoice is eligible for
  replacement only when current evidence also shows that no intervening
  payment was received; if current payment state cannot be evidenced, leave
  the invoice status unchanged and escalate. Otherwise, cancel it
  (`CANCELLED`) and reissue the corrected amount.
- If the aggregate amount is correct but any component line is wrong, preserve
  `invoices.amount` and correct or re-render the external invoice breakdown
  from the recorded generator and conversion evidence before replying to the
  client. Do not close the dispute based only on the balanced total; restore
  the status recorded before the dispute only after the corrected breakdown is
  available. If the prior status is not evidenced, leave the row `DISPUTED`
  and escalate.
- If the aggregate amount and every component line are correct, reply to the
  client with the available trace from the invoice export or total to runs and
  trades, and restore the status recorded before the dispute (for example,
  `PAID` in TKT-2024-007), rather than hard-coding `ISSUED`. If the prior
  status is not evidenced, leave the row `DISPUTED` and escalate.

## Escalation

Escalate to client services with the full trace when the client contests the
recomputed figure.

## Related Artifacts

- Tables: `invoices`, `margin_results`, `margin_runs`, `trades`
