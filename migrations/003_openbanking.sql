-- Migration 003: Open Banking (OBIE) tables
-- Run as agentic_admin.

CREATE TABLE IF NOT EXISTS third_party_providers (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    client_id            VARCHAR(64) NOT NULL UNIQUE,
    client_secret_hash   TEXT        NOT NULL,
    organisation_name    VARCHAR(200) NOT NULL,
    software_id          VARCHAR(128),
    roles                VARCHAR(8)[]  NOT NULL DEFAULT ARRAY[]::VARCHAR[],
    is_active            BOOLEAN     NOT NULL DEFAULT TRUE,
    redirect_uris        VARCHAR(512)[] NOT NULL DEFAULT ARRAY[]::VARCHAR[],
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT tpp_roles_valid CHECK (
        roles <@ ARRAY['AISP','PISP','CBPII']::VARCHAR[]
    )
);

CREATE TABLE IF NOT EXISTS account_access_consents (
    id                  VARCHAR(64) PRIMARY KEY,
    tpp_id              UUID         NOT NULL REFERENCES third_party_providers(id),
    psu_user_id         UUID         REFERENCES users(id),
    status              VARCHAR(32)  NOT NULL DEFAULT 'AwaitingAuthorisation',
    permissions         VARCHAR(64)[] NOT NULL,
    account_ids         VARCHAR(64)[] NOT NULL DEFAULT ARRAY[]::VARCHAR[],
    expiration_at       TIMESTAMPTZ,
    transaction_from    TIMESTAMPTZ,
    transaction_to      TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    status_updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_request         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT aac_status_valid CHECK (
        status IN ('AwaitingAuthorisation','Authorised','Rejected','Revoked','Expired')
    )
);
CREATE INDEX IF NOT EXISTS ix_aac_tpp     ON account_access_consents(tpp_id);
CREATE INDEX IF NOT EXISTS ix_aac_psu     ON account_access_consents(psu_user_id);
CREATE INDEX IF NOT EXISTS ix_aac_status  ON account_access_consents(status);

CREATE TABLE IF NOT EXISTS domestic_payment_consents (
    id                       VARCHAR(64) PRIMARY KEY,
    tpp_id                   UUID         NOT NULL REFERENCES third_party_providers(id),
    psu_user_id              UUID         REFERENCES users(id),
    status                   VARCHAR(32)  NOT NULL DEFAULT 'AwaitingAuthorisation',
    instructed_amount        NUMERIC(18,2) NOT NULL,
    currency                 VARCHAR(3)   NOT NULL,
    debtor_account_id        UUID         REFERENCES accounts(id),
    creditor_scheme          VARCHAR(64)  NOT NULL,
    creditor_identification  VARCHAR(256) NOT NULL,
    creditor_name            VARCHAR(140),
    end_to_end_id            VARCHAR(64),
    instruction_id           VARCHAR(64),
    risk                     JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at               TIMESTAMPTZ  NOT NULL DEFAULT now(),
    status_updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
    consumed_payment_id      UUID         REFERENCES transactions(id),
    CONSTRAINT dpc_status_valid CHECK (
        status IN ('AwaitingAuthorisation','Authorised','Consumed','Rejected','Expired')
    ),
    CONSTRAINT dpc_amount_positive CHECK (instructed_amount > 0)
);
CREATE INDEX IF NOT EXISTS ix_dpc_tpp    ON domestic_payment_consents(tpp_id);
CREATE INDEX IF NOT EXISTS ix_dpc_psu    ON domestic_payment_consents(psu_user_id);
CREATE INDEX IF NOT EXISTS ix_dpc_status ON domestic_payment_consents(status);

-- Grants for the runtime app role.
GRANT SELECT, INSERT, UPDATE ON
    third_party_providers,
    account_access_consents,
    domestic_payment_consents
TO agentic_app;
