# ACFS Architecture Overview

Acme Clearing & Fulfillment System (ACFS) is the in-house clearing and
settlement platform of Acme Capital Group. It covers the post-trade
lifecycle for listed derivatives across Asia-Pacific venues: trade import,
position maintenance, margin calculation, reconciliation, invoicing,
settlement fulfillment, and regulatory trade reporting.

This document describes the module landscape, system boundaries, and the
operational constraints that shape support work around ACFS.

## Module Landscape

| Module | Runtime | Responsibility |
| --- | --- | --- |
| Margin Service | Java | Calculates initial and variation margin per client account from positions, applies venue-specific rates, and writes `margin_results`. |
| Trade Importer | Python batch | Parses nightly venue trade files, validates them, and loads records into `trades`. Rejects are written to a reject report. |
| Trade Reporting Converter | Java | Receives broker trade messages (FIX), enriches and maps them against broker and instrument master data, and converts them into TRC009 XML messages (eBIZ framework, "Reaction to Service Results" transaction) for the risk monitoring system. |
| Position Reconciler | Java | Aggregates client-level positions and compares them with venue aggregate positions; raises breaks on any mismatch. |
| Invoice Generator | Python batch | Builds monthly clearing-fee and margin-call invoices from `margin_results` and `trades`, writes `invoices`. |
| Fulfillment Adapter | Java | Converts approved settlement instructions into venue/custodian message formats and tracks acknowledgment status. |
| Batch Scheduler | Python | Orchestrates the nightly window: import → position maintenance → margin run → reconciliation → invoicing; records scheduled jobs in `batch_jobs`. |

The relational database is the integration point: modules exchange data
through its tables rather than through direct service calls. See
`data-flow.md` for the step-by-step flows and `data/sample_db/` for the
schema and data dictionary.

## System Boundary

Inside ACFS:

- Post-trade processing of executed trades: import, position maintenance,
  margining, reconciliation, invoicing, fulfillment, and reporting.
- Operational support tooling: support tickets, runbooks, and batch
  monitoring.

Outside ACFS:

- Trade execution and matching — executions arrive from venues as files;
  ACFS never touches order flow.
- Custody and settlement execution — custodians and venues perform the
  actual settlement; the Fulfillment Adapter only exchanges messages with
  them.
- Risk monitoring itself — ACFS feeds the risk monitoring system with
  TRC009 messages but does not evaluate risk limits.
- Client onboarding and master data ownership — client and instrument
  master data are registered upstream and consumed by ACFS modules.

External parties and their interfaces:

| External party | Interface | Direction |
| --- | --- | --- |
| Venues (SGX, ASX, HKEX) | Nightly trade files, aggregate position/margin publications, settlement messages | Both |
| Brokers | FIX trade messages | Inbound |
| Custodians | Settlement messages and acknowledgments | Both |
| Risk monitoring system | TRC009 XML messages | Outbound |
| Clients | Invoices, margin calls | Outbound |

## Operational Constraints

- **Nightly window**: the batch sequence runs in the early morning hours
  and must complete before morning reporting to venues. Slot overruns are
  treated as operational incidents.
- **Venue figures are authoritative**: where ACFS figures disagree with
  venue-published aggregates, the difference must be explained or formally
  queried; ACFS data is never silently adjusted to match.
- **Manual corrections require audit trails**: manual position adjustments
  and invoice corrections must be traceable; untracked adjustments are a
  known source of recurring reconciliation breaks.

## Known Limitations

- Margining is daily and batch-based; there is no intraday margining.
- Venue aggregate positions are consumed in-memory during reconciliation
  and are not persisted, so historical venue figures cannot be queried.
- Position adjustments are applied directly to the current snapshot; there
  is no position history table.
- The Trade Reporting Converter holds retries in memory; a restart clears
  the retry queue (see INC-2024-006).
