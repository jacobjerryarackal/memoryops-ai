-- MemoryOps AI
-- Migration: 004_add_row_level_security
-- Purpose: Enable Row-Level Security on memories and memory_audit_logs

BEGIN;

-- 1. Enable RLS and force it for the owner/superuser
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE memories FORCE ROW LEVEL SECURITY;

ALTER TABLE memory_audit_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_audit_logs FORCE ROW LEVEL SECURITY;

-- 2. Create policy for memories table
-- Allows access if bypass_rls is 'true' or coordinates match app settings
CREATE POLICY tenant_user_isolation_policy ON memories
    USING (
        current_setting('app.bypass_rls', true) = 'true'
        OR (
            tenant_id = current_setting('app.current_tenant_id', true)
            AND user_id = current_setting('app.current_user_id', true)
        )
    )
    WITH CHECK (
        current_setting('app.bypass_rls', true) = 'true'
        OR (
            tenant_id = current_setting('app.current_tenant_id', true)
            AND user_id = current_setting('app.current_user_id', true)
        )
    );

-- 3. Create policy for memory_audit_logs table
CREATE POLICY tenant_user_isolation_policy ON memory_audit_logs
    USING (
        current_setting('app.bypass_rls', true) = 'true'
        OR (
            tenant_id = current_setting('app.current_tenant_id', true)
            AND (
                user_id IS NULL
                OR user_id = current_setting('app.current_user_id', true)
            )
        )
    )
    WITH CHECK (
        current_setting('app.bypass_rls', true) = 'true'
        OR (
            tenant_id = current_setting('app.current_tenant_id', true)
            AND (
                user_id IS NULL
                OR user_id = current_setting('app.current_user_id', true)
            )
        )
    );

COMMIT;
