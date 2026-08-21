# ACFS Data Flow

How data moves through ACFS during the nightly window, how broker trades
reach the risk monitoring system, and where each step reads from and writes
to. Table and column names refer to the schema in `data/sample_db/`.

## Nightly Batch Window

The Batch Scheduler orchestrates five recorded steps in fixed order. The
nightly position-maintenance operation runs between trade import and margin
run, materializing the positions that downstream calculations consume. Each
recorded step is represented by a row in `batch_jobs`.

```text
venue trade files
      |
      v
[1] trade_import --writes--> trades
      |
      v
[2] position_maintenance <---- prior positions
      | writes
      v
positions
      |
      v
[3] margin_run --writes--> margin_runs + margin_results
      |
      v
[4] reconciliation <------- venue aggregate files
      | writes
      v
break report
      |
      v
[5] invoicing (monthly) --writes--> invoices
```

### Step 1: Trade Import (`trade_import`)

- **Input**: nightly venue trade files (one per venue).
- **Processing**: parse, validate, and load accepted records.
- **Output**: rows in `trades`, tagged with an import batch such as
  `IMP-20240315-SGX`.
- **Failure mode**: rejects (duplicate trade IDs, unknown client codes,
  format violations) go to a reject report and block all downstream steps.
  See `runbooks/rb-failed-trade-import.md`.

### Step 2: Position Maintenance

- **Input**: accepted `trades` for the business date and the prior position
  snapshot.
- **Processing**: apply imported executions to the prior state and build the
  client/instrument/venue position snapshot for downstream calculations.
- **Output**: rows in `positions`, including `quantity`, `last_price`, and
  `previous_close`.
- **Failure mode**: missing position state, such as an unseeded
  `previous_close`, makes the margin result unreliable and must be corrected
  before the margin run. See `data/sample_docs/tickets/TKT-2024-009.md`.

### Step 3: Margin Run (`margin_run`)

- **Input**: `clients` (active accounts only), `positions` for the business
  date and venue.
- **Processing**: the Margin Service calculates per-client initial margin
  (venue rate on gross notional, portfolio offset where applicable) and
  variation margin (mark-to-market against the previous close).
- **Output**: one `margin_runs` row (e.g. `MR-20240315-SGX`) and one
  `margin_results` row per client, in the venue base currency.
- **Failure mode**: a failed or orphaned run leaves `margin_runs` in
  `RUNNING`/`FAILED`; the scheduler must block reconciliation and invoicing
  until a completed margin run is available. Reconciliation itself reads
  positions and venue aggregates, not `margin_results`. See
  `runbooks/rb-batch-job-failure.md`.

### Step 4: Reconciliation (`reconciliation`)

- **Input**: `positions` for the venue and date, plus the venue-published
  aggregate positions from the venue file (consumed in-memory, not
  persisted).
- **Processing**: the Position Reconciler sums client positions per
  instrument and compares with the venue aggregates.
- **Output**: a break per mismatched instrument; breaks must be triaged
  before morning reporting. See `runbooks/rb-reconciliation-break.md`.

### Step 5: Invoicing (monthly)

- **Input**: the month's `margin_results` and `trades`.
- **Output**: `invoices` rows per client and period, either clearing-fee or
  margin-call lines. Disputed lines are traced back through this flow. See
  `runbooks/rb-invoice-discrepancy.md`.

## Trade Reporting Flow (intraday)

Independent of the nightly window, the Trade Reporting Converter runs
continuously:

```text
broker FIX trade message
      |
      v
enrich + map against broker/instrument master data
      |                          |
   mapped ok                 missing master data
      |                          |
      v                          v
TRC009 XML message         in-memory retry list (bounded retries,
      |                    dead-letter report when exhausted)
      v
risk monitoring system
```

Messages whose master data is missing are retried; after the retry budget
is exhausted they are moved to a dead-letter report and raise a data-
quality alert instead of retrying indefinitely (see INC-2024-006).

## Support Investigation Flow

Support questions follow a standard trace direction, from the visible
symptom back to the originating data:

```text
ticket / dispute
      |
      v
margin_results or invoices row
      |
      v
margin_runs + positions snapshot for the run date
      |
      v
trades and the originating import batch
```

Runbooks in `runbooks/` codify this trace per failure class; tickets in
`tickets/` record concrete investigations, and `tickets/incidents/` record
retrospectives for recurring or severe events.
