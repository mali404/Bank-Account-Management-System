-- Migration 001: initial schema + role grants
-- Run as the database owner / agentic_admin.

-- Extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Two DB roles: admin (DDL) and app (runtime DML).
-- The app role is what the FastAPI process connects as. It cannot run DDL
-- and cannot UPDATE/DELETE the audit table.

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agentic_app') THEN
        CREATE ROLE agentic_app LOGIN PASSWORD 'agentic_app_pw';
    END IF;
END $$;

-- Tables ---------------------------------------------------------------

CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           VARCHAR(254) NOT NULL UNIQUE,
    password_hash   TEXT         NOT NULL,
    role            VARCHAR(32)  NOT NULL,
    is_active       BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT users_role_valid CHECK (
        role IN ('customer','teller','loan_officer','compliance_officer','admin')
    )
);

CREATE TABLE IF NOT EXISTS customers (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL UNIQUE REFERENCES users(id) ON DELETE RESTRICT,
    -- Encrypted PII columns. The application reads these via
    -- pgp_sym_decrypt(col, current_setting('app.dek')) and never logs raw values.
    full_name   BYTEA NOT NULL,
    gov_id      BYTEA NOT NULL,
    dob         BYTEA NOT NULL,
    kyc_status  VARCHAR(16) NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS accounts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    customer_id     UUID NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    account_number  VARCHAR(20) NOT NULL UNIQUE,
    account_type    VARCHAR(16) NOT NULL,
    balance         NUMERIC(18,2) NOT NULL DEFAULT 0.00,
    is_frozen       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT accounts_balance_nonnegative CHECK (balance >= 0),
    CONSTRAINT accounts_type_valid CHECK (
        account_type IN ('checking','savings','loan')
    )
);

CREATE TABLE IF NOT EXISTS transactions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    from_account_id     UUID REFERENCES accounts(id),
    to_account_id       UUID REFERENCES accounts(id),
    amount              NUMERIC(18,2) NOT NULL,
    memo                TEXT NOT NULL DEFAULT '',
    state               VARCHAR(16) NOT NULL,
    originator_user_id  UUID NOT NULL REFERENCES users(id),
    approver_user_id    UUID REFERENCES users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    settled_at          TIMESTAMPTZ,
    CONSTRAINT transactions_amount_positive CHECK (amount > 0),
    CONSTRAINT transactions_state_valid CHECK (
        state IN ('pending_approval','approved','settled','rejected','cancelled')
    ),
    CONSTRAINT transactions_separation_of_duties CHECK (
        approver_user_id IS NULL OR approver_user_id <> originator_user_id
    )
);
CREATE INDEX IF NOT EXISTS ix_transactions_from  ON transactions(from_account_id);
CREATE INDEX IF NOT EXISTS ix_transactions_to    ON transactions(to_account_id);
CREATE INDEX IF NOT EXISTS ix_transactions_state ON transactions(state);

CREATE TABLE IF NOT EXISTS audit_events (
    id              BIGSERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_user_id   TEXT,
    actor_role      VARCHAR(32),
    action          VARCHAR(64) NOT NULL,
    resource        VARCHAR(128),
    outcome         VARCHAR(16) NOT NULL,
    nist_control    VARCHAR(16),
    detail          JSONB NOT NULL DEFAULT '{}'::jsonb,
    request_ip      VARCHAR(45),
    prev_hmac       VARCHAR(64) NOT NULL,
    hmac            VARCHAR(64) NOT NULL UNIQUE,
    payload_json       JSONB NOT NULL,
    payload_canonical  TEXT  NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_audit_events_actor    ON audit_events(actor_user_id);
CREATE INDEX IF NOT EXISTS ix_audit_events_action   ON audit_events(action);
CREATE INDEX IF NOT EXISTS ix_audit_events_outcome  ON audit_events(outcome);

-- Grants --------------------------------------------------------------
-- Default: the runtime app role can SELECT/INSERT/UPDATE everything except
-- audit_events, which is INSERT-only. UPDATE/DELETE on audit_events are
-- explicitly NOT granted; the table is append-only at the DB level.
GRANT CONNECT ON DATABASE agentic_bank TO agentic_app;
GRANT USAGE  ON SCHEMA public          TO agentic_app;

GRANT SELECT, INSERT, UPDATE ON users, customers, accounts, transactions TO agentic_app;
GRANT INSERT, SELECT          ON audit_events                            TO agentic_app;
GRANT USAGE, SELECT           ON ALL SEQUENCES IN SCHEMA public          TO agentic_app;

-- Future tables: same defaults.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE ON TABLES TO agentic_app;
