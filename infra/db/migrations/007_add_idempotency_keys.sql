-- MemoryOps AI
-- Migration: 007_add_idempotency_keys
-- Purpose: Add idempotency_records table to handle requests cache with RLS

BEGIN;

CREATE TABLE idempotency_records (
    key VARCHAR(255) NOT NULL,
    tenant_id VARCHAR(255) NOT NULL,
    user_id VARCHAR(255) NOT NULL,
    response_status INTEGER NOT NULL,
    response_body TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (key, tenant_id, user_id)
);

ALTER TABLE idempotency_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE idempotency_records FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_user_idempotency_policy ON idempotency_records
    USING (
        current_setting('app.bypass_rls', true) = 'true'
        OR (
            tenant_id = current_setting('app.current_tenant_id', true)
            AND user_id = current_setting('app.current_user_id', true)
        )
    );

GRANT ALL PRIVILEGES ON TABLE idempotency_records TO memoryops_app;

COMMIT;
