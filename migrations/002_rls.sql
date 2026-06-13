-- Migration 002: Row-Level Security
-- The application sets per-request session variables before queries:
--    SET LOCAL app.user_id  = '<uuid>';
--    SET LOCAL app.role     = '<role>';
-- RLS policies use these to filter rows. Combined with FastAPI guards,
-- this is layered defense: an SQL injection that bypasses the app layer
-- still cannot read another customer's account.

ALTER TABLE accounts      ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions  ENABLE ROW LEVEL SECURITY;
ALTER TABLE customers     ENABLE ROW LEVEL SECURITY;

-- Customers can only see their own customer row.
DROP POLICY IF EXISTS customers_self_or_staff ON customers;
CREATE POLICY customers_self_or_staff ON customers
USING (
    current_setting('app.role', true) IN ('teller','loan_officer','compliance_officer','admin','system')
    OR user_id::text = current_setting('app.user_id', true)
);

-- Accounts: customers see their own (via their customer_id);
-- staff roles see all.
DROP POLICY IF EXISTS accounts_self_or_staff ON accounts;
CREATE POLICY accounts_self_or_staff ON accounts
USING (
    current_setting('app.role', true) IN ('teller','loan_officer','compliance_officer','admin','system')
    OR customer_id IN (
        SELECT id FROM customers
        WHERE user_id::text = current_setting('app.user_id', true)
    )
);

-- Transactions: customer sees those touching their own accounts;
-- staff see all.
DROP POLICY IF EXISTS transactions_self_or_staff ON transactions;
CREATE POLICY transactions_self_or_staff ON transactions
USING (
    current_setting('app.role', true) IN ('teller','loan_officer','compliance_officer','admin','system')
    OR from_account_id IN (
        SELECT a.id FROM accounts a
        JOIN customers c ON a.customer_id = c.id
        WHERE c.user_id::text = current_setting('app.user_id', true)
    )
    OR to_account_id IN (
        SELECT a.id FROM accounts a
        JOIN customers c ON a.customer_id = c.id
        WHERE c.user_id::text = current_setting('app.user_id', true)
    )
);

-- Force RLS even for the table owner (defense in depth — operators can't
-- bypass policy by accident in psql).
ALTER TABLE accounts      FORCE ROW LEVEL SECURITY;
ALTER TABLE transactions  FORCE ROW LEVEL SECURITY;
ALTER TABLE customers     FORCE ROW LEVEL SECURITY;
