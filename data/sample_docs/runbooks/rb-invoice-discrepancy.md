# Runbook: Invoice Discrepancy

## Purpose

Trace a disputed invoice line back to the margin runs and trades that
produced it, and correct or confirm the billed amount.

## When To Use

- A client disputes an invoice line, e.g. `INV-202403-002`.
- An `invoices` row has status `DISPUTED`.

## Prerequisites

- The invoice identifier and the disputed period, e.g. `2024-02`.
- Read access to `invoices`, `margin_results`, `margin_runs`, and `trades`.

## Investigation Steps

1. Identify the disputed line: clearing fee or margin call, amount, and
   period.
2. Enumerate the margin runs for the period and venue from `margin_runs`,
   and sum the client's `margin_results` rows for those runs.
3. For clearing fees, recompute the fee base from the client's `trades` in
   the period.
4. Compare the recomputed amount with the invoice line. Note any reruns or
   corrected runs in the period, which can double-count if the invoice was
   built from stale results.
5. Check whether a margin mismatch investigation (see the margin-result-
   mismatch runbook) is open for the client; invoice disputes frequently
   share a root cause with margin mismatches.

## Resolution Options

- If the amount is wrong, cancel the invoice (`CANCELLED`) and reissue.
- If the amount is correct, reply to the client with the trace from invoice
  line to runs and trades, and set the invoice back to `ISSUED`.

## Escalation

Escalate to client services with the full trace when the client contests the
recomputed figure.

## Related Artifacts

- Tables: `invoices`, `margin_results`, `margin_runs`, `trades`
