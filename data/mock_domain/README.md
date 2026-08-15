# Mock Domain: Acme Clearing & Fulfillment System (ACFS)

This document defines the fictional enterprise domain that backs the
Co-Ops RAG corpus, evaluation questions, and support-investigation demos.
Everything under `data/` refers to this system. All names, clients,
venues, and incidents are invented; the domain is deliberately generic and
does not reproduce any real clearing house's workflows or any vendor ERP's
process model.

## System Background

Acme Clearing & Fulfillment System (ACFS) is the in-house clearing and
settlement platform of the fictional Acme Capital Group. It handles the
post-trade lifecycle for listed derivatives across several Asia-Pacific
venues:

- nightly import of executed trades from venue files;
- client and house position maintenance;
- daily margin calculation and reconciliation against venue-published
  aggregate margins;
- invoice generation for clearing fees and margin calls;
- fulfillment of settlement instructions to custodians and venues.

ACFS runs as a mix of a Java service layer (margin, reconciliation, and
trade reporting), Python batch jobs (import, export, reporting), a
relational database, and a nightly batch schedule. A small operations team
supports it around the clock because a failed margin run can block morning
reporting to venues.

## Core Modules

| Module | Runtime | Responsibility |
| --- | --- | --- |
| Margin Service | Java | Calculates initial and variation margin per client account from positions, applies venue-specific rates, and writes `margin_results`. |
| Trade Importer | Python batch | Parses nightly venue trade files, validates them, and loads records into `trades`. Rejects are written to a reject report. |
| Trade Reporting Converter | Java | Receives broker trade messages (FIX), enriches and maps them against broker and instrument master data, and converts them into TRC009 regulatory messages (fictional format) for the risk monitoring system. |
| Position Reconciler | Java | Aggregates client-level positions and compares them with venue aggregate positions; raises breaks on any mismatch. |
| Invoice Generator | Python batch | Builds monthly clearing-fee and margin-call invoices from `margin_results` and `trades`, writes `invoices`. |
| Fulfillment Adapter | Java | Converts approved settlement instructions into venue/custodian message formats and tracks acknowledgment status. |
| Batch Scheduler | Python | Orchestrates the nightly window: import → margin run → reconciliation → invoicing; records every run in `batch_jobs`. |
| Support Runbook | Docs | Operational procedures for known failure classes, owned by the support team. |

## Primary Users

| Role | Main interaction with ACFS |
| --- | --- |
| Support engineers | Investigate tickets, trace batch failures, run reconciliation repairs. |
| Operations analysts | Monitor the nightly batch, triage breaks, approve manual corrections. |
| Margin operations staff | Review margin runs, investigate mismatches before venue reporting. |
| Service developers | Maintain the Java services and Python batch jobs; debug incidents. |
| Risk & compliance | Consume margin reports; query historical runs for audit. |

## Common Support Scenarios

1. **Margin result mismatch** — the ACFS aggregate margin for a venue does
   not equal the venue-published figure; investigation spans the margin
   run, positions, and the reconciliation output.
2. **Failed trade import** — a venue file is rejected (format change,
   duplicate trade IDs, unknown client codes); downstream margin run is
   blocked.
3. **Reconciliation breaks** — client-level positions do not roll up to
   venue aggregates after a manual position adjustment.
4. **Batch job failure or timeout** — a job in the nightly window fails or
   overruns, and downstream jobs must be restarted safely.
5. **Invoice discrepancies** — a client disputes an invoice line; support
   must trace it back to specific margin runs and trades.
6. **Stuck fulfillment instructions** — a settlement message never
   receives acknowledgment; the adapter log and venue status must be
   correlated.

## Main Data Entities

| Entity | Storage | Key fields (illustrative) |
| --- | --- | --- |
| clients | DB table | `client_id`, `client_name`, `status`, `margin_model` |
| trades | DB table | `trade_id`, `client_id`, `venue`, `instrument`, `quantity`, `price`, `trade_date`, `import_batch` |
| positions | DB table | `client_id`, `venue`, `instrument`, `quantity`, `as_of_date` |
| margin_runs | DB table | `run_id`, `run_date`, `venue`, `status`, `started_at`, `finished_at` |
| margin_results | DB table | `run_id`, `client_id`, `initial_margin`, `variation_margin`, `currency` |
| invoices | DB table | `invoice_id`, `client_id`, `period`, `amount`, `status` |
| support_tickets | DB table | `ticket_id`, `summary`, `severity`, `status`, `module`, `opened_at` |
| batch_jobs | DB table | `job_id`, `job_name`, `status`, `scheduled_at`, `exit_code` |

Naming conventions used across the corpus:

- Client IDs: `ACME-101`, `ACME-102`, ...
- Ticket IDs: `TKT-2024-001`, ...
- Margin run IDs: `MR-YYYYMMDD-{venue}`, e.g. `MR-20240315-SGX`.
- Venues: `SGX`, `ASX`, `HKEX` (fictional usage only).
- Currencies: `SGD`, `AUD`, `HKD`, `USD`.

The full SQL schema and data dictionary will be provided in
`data/sample_db/` in a subsequent data-fixture update.

## Problems the AI Assistant Should Solve

The Co-Ops assistant is built to support this domain. Target capabilities:

1. **Support investigation** — given a ticket such as "Margin result
   mismatch for client ACME-102", propose likely causes, and name the
   relevant files, SQL tables, and runbooks as an investigation plan.
2. **Code understanding** — answer where a behavior lives, e.g. "Which
   class calculates client margin?" or "What does `PositionReconciler`
   compare?"
3. **Document QA** — answer operational questions from runbooks,
   architecture docs, and FAQs with citations.
4. **Data-flow questions** — trace how a trade record moves from the venue
   file through the importer into positions and margin results.
5. **SQL schema questions** — identify which tables and columns back a
   business concept such as variation margin.
6. **Impact analysis** — estimate which files, tables, and downstream jobs
   are affected when, for example, the margin formula changes.

## Corpus Layout

| Directory | Content | Status |
| --- | --- | --- |
| `data/mock_domain/` | This domain definition | Delivered |
| `data/sample_codebase/java/` | Mock `margin-service` Java sources | Planned |
| `data/sample_db/` | `schema.sql`, data dictionary, sample records | Planned |
| `data/sample_docs/runbooks/` | Operational runbooks | Planned |
| `data/sample_docs/tickets/` | Support tickets and incident notes | Planned |
| `data/sample_docs/` | Architecture, data-flow, FAQ docs | Planned |
| `data/eval_seed/` | RAG evaluation question set v0 | Planned |
