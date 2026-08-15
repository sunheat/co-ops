# ACFS Data Dictionary

Column-level documentation for the mock ACFS schema defined in
`schema.sql`. All names and figures are fictional; see
`data/mock_domain/README.md` for the domain definition.

## Dialect and Conventions

- Portable SQL written against PostgreSQL-compatible syntax; no
  vendor-specific features are used.
- Monetary amounts use `DECIMAL(18,2)`; prices use `DECIMAL(18,4)`.
- Quantities are signed integers: negative values are sells (trades) or
  shorts (positions).
- Venues are restricted to `SGX`, `ASX`, `HKEX`; currencies to `SGD`,
  `AUD`, `HKD`, `USD`. Margin figures are always stored in the venue's
  base currency (`SGX→SGD`, `ASX→AUD`, `HKEX→HKD`).

Naming conventions:

| Identifier | Pattern | Example |
| --- | --- | --- |
| Client ID | `ACME-{nnn}` | `ACME-101` |
| Trade ID | `TRD-{YYYYMMDD}-{seq}` | `TRD-20240315-0001` |
| Import batch | `IMP-{YYYYMMDD}-{venue}` | `IMP-20240315-SGX` |
| Margin run ID | `MR-{YYYYMMDD}-{venue}` | `MR-20240315-SGX` |
| Invoice ID | `INV-{YYYYMM}-{seq}` | `INV-202403-001` |
| Ticket ID | `TKT-{YYYY}-{seq}` | `TKT-2024-001` |
| Batch job ID | `BJ-{YYYYMMDD}-{seq}` | `BJ-20240315-01` |

## Data Lineage

Which module writes and reads each table in the nightly window:

| Table | Written by | Read by |
| --- | --- | --- |
| `clients` | Operations (manual, out of nightly window) | Margin Service, Invoice Generator, support tooling |
| `trades` | Trade Importer (Python batch) | Position maintenance, margin investigation |
| `positions` | Nightly batch (position maintenance) | Margin Service, Position Reconciler |
| `margin_runs` | Margin Service (Java) | Batch Scheduler, support tooling |
| `margin_results` | Margin Service (Java) | Invoice Generator, risk & compliance |
| `invoices` | Invoice Generator (Python batch) | Client services, support investigation |
| `support_tickets` | Support tooling | Support engineers, AI assistant demos |
| `batch_jobs` | Batch Scheduler (Python) | Operations monitoring |

## Tables

### clients

Client accounts registered with the clearing house.

| Column | Type | Description |
| --- | --- | --- |
| `client_id` | VARCHAR(16), PK | Client identifier, e.g. `ACME-101`. |
| `client_name` | VARCHAR(128) | Display name of the client. |
| `status` | VARCHAR(16) | `ACTIVE`, `SUSPENDED`, or `CLOSED`. Only `ACTIVE` clients participate in margin runs. |
| `margin_model` | VARCHAR(16) | `STANDARD` or `PORTFOLIO`. Portfolio accounts receive a diversification offset in initial margin. |
| `created_at` | TIMESTAMP | Registration time. |

### trades

Executed trades imported from nightly venue files. Rejects during import go
to a reject report and block the downstream margin run.

| Column | Type | Description |
| --- | --- | --- |
| `trade_id` | VARCHAR(32), PK | Unique trade identifier. |
| `client_id` | VARCHAR(16), FK → clients | Client the trade belongs to. |
| `venue` | VARCHAR(8) | Execution venue. |
| `instrument` | VARCHAR(32) | Instrument code. |
| `quantity` | INTEGER | Signed quantity; negative for sells. |
| `price` | DECIMAL(18,4) | Execution price in the venue currency. |
| `trade_date` | DATE | Business date of the execution. |
| `import_batch` | VARCHAR(32) | Importer batch that loaded the record. |

### positions

Client-level positions as of a business date. Manual adjustments by
operations analysts are a known source of reconciliation breaks.

| Column | Type | Description |
| --- | --- | --- |
| `client_id` | VARCHAR(16), FK → clients, composite PK | Client the position belongs to. |
| `venue` | VARCHAR(8), composite PK | Venue the position is held at. |
| `instrument` | VARCHAR(32), composite PK | Instrument code. |
| `quantity` | INTEGER | Signed quantity; negative for shorts. |
| `last_price` | DECIMAL(18,4) | Latest mark price for the business date. |
| `previous_close` | DECIMAL(18,4) | Previous day's close; basis for variation margin. |
| `as_of_date` | DATE, composite PK | Business date of the snapshot. |

### margin_runs

One row per daily margin run per venue.

| Column | Type | Description |
| --- | --- | --- |
| `run_id` | VARCHAR(32), PK | Run identifier, e.g. `MR-20240315-SGX`. |
| `run_date` | DATE | Business date of the run. |
| `venue` | VARCHAR(8) | Venue the run covers. |
| `base_currency` | VARCHAR(3) | Venue base currency; constrained to `SGX→SGD`, `ASX→AUD`, or `HKEX→HKD`. |
| `status` | VARCHAR(16) | `RUNNING`, `COMPLETED`, or `FAILED`. |
| `started_at` | TIMESTAMP | Run start time. |
| `finished_at` | TIMESTAMP, nullable | Run end time; NULL while running. |

### margin_results

Per-client figures produced by a margin run.

| Column | Type | Description |
| --- | --- | --- |
| `run_id` | VARCHAR(32), composite FK → margin_runs | Run the result belongs to. Together with `currency`, references the run's base currency. Part of the PK. |
| `client_id` | VARCHAR(16), FK → clients | Client the result belongs to. Part of the PK. |
| `initial_margin` | DECIMAL(18,2) | Venue rate applied to gross notional, with portfolio offset where applicable. |
| `variation_margin` | DECIMAL(18,2) | Daily mark-to-market change. |
| `currency` | VARCHAR(3), composite FK → margin_runs.base_currency | Venue base currency of the amounts; the schema enforces the run-venue mapping. |

### invoices

Monthly clearing-fee and margin-call invoices built from `margin_results`
and `trades`.

| Column | Type | Description |
| --- | --- | --- |
| `invoice_id` | VARCHAR(32), PK | Invoice identifier. |
| `client_id` | VARCHAR(16), FK → clients | Billed client. |
| `period` | VARCHAR(7) | Billing period, `YYYY-MM`. |
| `amount` | DECIMAL(18,2) | Total billed amount. |
| `currency` | VARCHAR(3), CHECK | Currency of the amount; restricted to `SGD`, `AUD`, `HKD`, or `USD`. |
| `status` | VARCHAR(16) | `ISSUED`, `DISPUTED`, `PAID`, or `CANCELLED`. Disputed invoices drive invoice-discrepancy tickets. |

### support_tickets

Support tickets raised against ACFS modules.

| Column | Type | Description |
| --- | --- | --- |
| `ticket_id` | VARCHAR(16), PK | Ticket identifier, e.g. `TKT-2024-001`. |
| `summary` | VARCHAR(256) | One-line problem description. |
| `severity` | VARCHAR(8) | `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL`. |
| `status` | VARCHAR(16) | `OPEN`, `IN_PROGRESS`, `RESOLVED`, or `CLOSED`. |
| `module` | VARCHAR(32) | Module the ticket is raised against, e.g. `Margin Service`. |
| `opened_at` | TIMESTAMP | Ticket creation time. |

### batch_jobs

Nightly batch executions recorded by the scheduler.

| Column | Type | Description |
| --- | --- | --- |
| `job_id` | VARCHAR(32), PK | Job execution identifier. |
| `job_name` | VARCHAR(64) | Job type, e.g. `trade_import`, `margin_run`, `reconciliation`. |
| `status` | VARCHAR(16) | `PENDING`, `RUNNING`, `SUCCEEDED`, or `FAILED`. |
| `scheduled_at` | TIMESTAMP | Scheduled start time in the nightly window. |
| `exit_code` | INTEGER, nullable | Process exit code; NULL while pending or running. |

## Relationships

```text
clients 1─N trades
clients 1─N positions
clients 1─N margin_results
clients 1─N invoices
margin_runs 1─N margin_results
```

Venue-published aggregate positions (the comparison target of the Position
Reconciler) are intentionally not persisted here: they arrive with the venue
files and are consumed in-memory during reconciliation.

## Known Limitations

- Fixture-scale data only; sample records cover a single business date and a
  handful of clients (see `sample_records.json`).
- No audit/history tables for manual corrections, and no FK `ON DELETE`
  policies beyond the engine default.
- No venue aggregate position table by design (see Relationships).
- Status enumerations are stored as checked strings rather than native enum
  types, to keep the schema engine-portable.
