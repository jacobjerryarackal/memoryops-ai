-- MemoryOps AI
-- Migration: 008_harden_row_level_security
-- Purpose: Harden RLS policies to check for empty strings and prevent accidental wildcards

BEGIN;

-- 1. Recreate policy for memories table
DROP POLICY IF EXISTS tenant_user_isolation_policy ON memories;

CREATE POLICY tenant_user_isolation_policy ON memories
    USING (
        current_setting('app.bypass_rls', true) = 'true'
        OR (
            tenant_id = current_setting('app.current_tenant_id', true)
            AND tenant_id <> ''
            AND user_id = current_setting('app.current_user_id', true)
            AND user_id <> ''
        )
    )
    WITH CHECK (
        current_setting('app.bypass_rls', true) = 'true'
        OR (
            tenant_id = current_setting('app.current_tenant_id', true)
            AND tenant_id <> ''
            AND user_id = current_setting('app.current_user_id', true)
            AND user_id <> ''
        )
    );

-- 2. Recreate policy for memory_audit_logs table
DROP POLICY IF EXISTS tenant_user_isolation_policy ON memory_audit_logs;

CREATE POLICY tenant_user_isolation_policy ON memory_audit_logs
    USING (
        current_setting('app.bypass_rls', true) = 'true'
        OR (
            tenant_id = current_setting('app.current_tenant_id', true)
            AND tenant_id <> ''
            AND (
                user_id IS NULL
                OR (
                    user_id = current_setting('app.current_user_id', true)
                    AND user_id <> ''
                )
            )
        )
    )
    WITH CHECK (
        current_setting('app.bypass_rls', true) = 'true'
        OR (
            tenant_id = current_setting('app.current_tenant_id', true)
            AND tenant_id <> ''
            AND (
                user_id IS NULL
                OR (
                    user_id = current_setting('app.current_user_id', true)
                    AND user_id <> ''
                )
            )
        )
    );

COMMIT;
