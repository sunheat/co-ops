# ACFS Frequently Asked Questions

Operational Q&A for support engineers, operations analysts, and new joiners.
For step-by-step procedures see the runbooks in `runbooks/`.

## Margin

**Q: Where is client margin calculated?**
A: In the Margin Service (Java). Initial margin is the venue rate applied
to the client's gross notional; portfolio-margin accounts receive a
diversification offset. Variation margin is the daily mark-to-market change
against the previous close. Per-client results land in `margin_results`.

**Q: Why does our aggregate margin differ from the venue's figure?**
A: The most frequent causes are a `PORTFOLIO` margin model applying an
offset the venue does not, a position snapshot taken before late trades
were imported, and manual adjustments applied after the run. Follow
`runbooks/rb-margin-result-mismatch.md`.

**Q: Why is a suspended client missing from the margin report?**
A: Only accounts with status `ACTIVE` in `clients` participate in a margin
run. This is expected behavior, not a defect.

**Q: What does a margin run identifier mean?**
A: `MR-YYYYMMDD-{venue}`, e.g. `MR-20240315-SGX` is the SGX run for
business date 2024-03-15. One run exists per venue per business date.

## Nightly Batch

**Q: A batch job failed. May I restart it immediately?**
A: Check `batch_jobs` and `margin_runs` first. An orphaned run in
`RUNNING` must be marked `FAILED` before any restart, and you must confirm
no downstream job consumed partial output. Follow
`runbooks/rb-batch-job-failure.md`.

**Q: The trade import was rejected. Is the whole night blocked?**
A: Yes — margin run, reconciliation, and invoicing all depend on the
import. Classify the rejects (duplicate IDs, unknown clients, format) and
reprocess per `runbooks/rb-failed-trade-import.md`.

**Q: What is a reconciliation break?**
A: A per-instrument mismatch between the ACFS aggregate of client
positions and the venue-published aggregate. Breaks must be triaged before
morning reporting; see `runbooks/rb-reconciliation-break.md`.

## Invoicing and Reporting

**Q: A client disputes an invoice line. Where do I start?**
A: Trace the line back through the month's `margin_results` and `trades`.
Reruns within the period can double-count if an invoice was built from
stale results. Follow `runbooks/rb-invoice-discrepancy.md`.

**Q: What happens to broker trades after they arrive over FIX?**
A: The Trade Reporting Converter enriches them against broker and
instrument master data, maps them, and emits TRC009 XML messages (eBIZ
framework) to the risk monitoring system. Messages with missing master
data are retried within a bounded budget and then dead-lettered.

**Q: A settlement instruction shows no acknowledgment. Is it lost?**
A: Not necessarily — custodian maintenance windows are a known cause.
Confirm the adapter logged the send, check counterparty health, and only
then resend with the same identifier per
`runbooks/rb-stuck-fulfillment.md`.

## General

**Q: May I adjust ACFS figures to match the venue?**
A: No. Venue figures are authoritative, but mismatches must be explained
or formally queried with the venue; ACFS data is never silently adjusted.

**Q: May I apply a manual position adjustment without paperwork?**
A: No. Every manual adjustment requires an audit trail entry; untracked
adjustments have caused multi-day reconciliation breaks (see INC-2024-003).

**Q: Who consumes the outputs of ACFS?**
A: Venues receive morning reporting and settlement messages; custodians
receive settlement instructions; clients receive invoices and margin
calls; the risk monitoring system receives TRC009 messages; risk and
compliance consume margin reports and historical runs for audit.
