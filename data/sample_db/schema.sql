-- ---------------------------------------------------------------------------
-- Acme Clearing & Fulfillment System (ACFS) - mock database schema
--
-- Part of the Co-Ops RAG corpus. All names, clients, venues, and figures are
-- fictional. This schema defines the relational core of ACFS as referenced
-- by the mock Java margin-service and the (planned) Python batch jobs.
--
-- Dialect: portable SQL written against PostgreSQL-compatible syntax. No
-- vendor-specific features (partitions, stored procedures, triggers) are
-- used, so the schema can be adapted to other engines with minor edits.
-- See data_dictionary.md for column-level documentation and lineage.
-- ---------------------------------------------------------------------------

-- Client accounts registered with the clearing house.
CREATE TABLE clients (
    client_id     VARCHAR(16)  PRIMARY KEY,             -- e.g. ACME-101
    client_name   VARCHAR(128) NOT NULL,
    status        VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE'
                  CHECK (status IN ('ACTIVE', 'SUSPENDED', 'CLOSED')),
    margin_model  VARCHAR(16)  NOT NULL DEFAULT 'STANDARD'
                  CHECK (margin_model IN ('STANDARD', 'PORTFOLIO')),
    created_at    TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Executed trades imported by the Python Trade Importer from venue files.
CREATE TABLE trades (
    trade_id      VARCHAR(32)  PRIMARY KEY,             -- e.g. TRD-20240315-0001
    client_id     VARCHAR(16)  NOT NULL REFERENCES clients (client_id),
    venue         VARCHAR(8)   NOT NULL
                  CHECK (venue IN ('SGX', 'ASX', 'HKEX')),
    instrument    VARCHAR(32)  NOT NULL,
    quantity      INTEGER      NOT NULL,                -- signed; negative = sell
    price         DECIMAL(18,4) NOT NULL,
    trade_date    DATE         NOT NULL,
    import_batch  VARCHAR(32)  NOT NULL                 -- e.g. IMP-20240315-SGX
);

CREATE INDEX idx_trades_client ON trades (client_id);
CREATE INDEX idx_trades_batch  ON trades (import_batch);

-- Client-level positions maintained by the nightly batch.
-- last_price / previous_close extend the illustrative domain definition so
-- that the margin service can mark positions to market from the database.
CREATE TABLE positions (
    client_id       VARCHAR(16)  NOT NULL REFERENCES clients (client_id),
    venue           VARCHAR(8)   NOT NULL
                    CHECK (venue IN ('SGX', 'ASX', 'HKEX')),
    instrument      VARCHAR(32)  NOT NULL,
    quantity        INTEGER      NOT NULL,              -- signed; negative = short
    last_price      DECIMAL(18,4) NOT NULL,
    previous_close  DECIMAL(18,4) NOT NULL,
    as_of_date      DATE         NOT NULL,
    PRIMARY KEY (client_id, venue, instrument, as_of_date)
);

CREATE INDEX idx_positions_snapshot ON positions (as_of_date, venue);

-- One row per daily margin run per venue.
CREATE TABLE margin_runs (
    run_id       VARCHAR(32) PRIMARY KEY,               -- e.g. MR-20240315-SGX
    run_date     DATE        NOT NULL,
    venue        VARCHAR(8)  NOT NULL
                 CHECK (venue IN ('SGX', 'ASX', 'HKEX')),
    base_currency VARCHAR(3) NOT NULL
                  CHECK (
                      (venue = 'SGX' AND base_currency = 'SGD')
                      OR (venue = 'ASX' AND base_currency = 'AUD')
                      OR (venue = 'HKEX' AND base_currency = 'HKD')
                  ),
    status       VARCHAR(16) NOT NULL DEFAULT 'RUNNING'
                 CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    started_at   TIMESTAMP   NOT NULL,
    finished_at  TIMESTAMP,
    UNIQUE (run_id, base_currency)
);

-- Per-client results of a margin run; consumed by the Invoice Generator.
CREATE TABLE margin_results (
    run_id            VARCHAR(32)   NOT NULL,
    client_id         VARCHAR(16)   NOT NULL REFERENCES clients (client_id),
    initial_margin    DECIMAL(18,2) NOT NULL,
    variation_margin  DECIMAL(18,2) NOT NULL,
    currency          VARCHAR(3)    NOT NULL
                      CHECK (currency IN ('SGD', 'AUD', 'HKD')),
    PRIMARY KEY (run_id, client_id),
    FOREIGN KEY (run_id, currency)
        REFERENCES margin_runs (run_id, base_currency)
);

CREATE INDEX idx_margin_results_client ON margin_results (client_id);

-- Monthly clearing-fee and margin-call invoices.
CREATE TABLE invoices (
    invoice_id  VARCHAR(32)   PRIMARY KEY,              -- e.g. INV-202403-001
    client_id   VARCHAR(16)   NOT NULL REFERENCES clients (client_id),
    period      VARCHAR(7)    NOT NULL,                 -- YYYY-MM
    amount      DECIMAL(18,2) NOT NULL,
    currency    VARCHAR(3)    NOT NULL
                CHECK (currency IN ('SGD', 'AUD', 'HKD', 'USD')),
    status      VARCHAR(16)   NOT NULL DEFAULT 'ISSUED'
                CHECK (status IN ('ISSUED', 'DISPUTED', 'PAID', 'CANCELLED'))
);

CREATE INDEX idx_invoices_client ON invoices (client_id);

-- Support tickets raised against ACFS modules.
CREATE TABLE support_tickets (
    ticket_id   VARCHAR(16)  PRIMARY KEY,               -- e.g. TKT-2024-001
    summary     VARCHAR(256) NOT NULL,
    severity    VARCHAR(8)   NOT NULL
                CHECK (severity IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')),
    status      VARCHAR(16)  NOT NULL DEFAULT 'OPEN'
                CHECK (status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED')),
    module      VARCHAR(32)  NOT NULL,                  -- e.g. Margin Service
    opened_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_tickets_module ON support_tickets (module, status);

-- Nightly batch executions recorded by the Python Batch Scheduler.
CREATE TABLE batch_jobs (
    job_id        VARCHAR(32) PRIMARY KEY,              -- e.g. BJ-20240315-01
    job_name      VARCHAR(64) NOT NULL,                 -- e.g. trade_import
    status        VARCHAR(16) NOT NULL DEFAULT 'PENDING'
                  CHECK (status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')),
    scheduled_at  TIMESTAMP   NOT NULL,
    exit_code     INTEGER
);
