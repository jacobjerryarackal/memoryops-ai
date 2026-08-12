-- MemoryOps AI
-- Migration: 005_create_app_user
-- Purpose: Create non-superuser role for application queries to enforce RLS

BEGIN;

-- 1. Create role if not exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'memoryops_app') THEN
        CREATE ROLE memoryops_app WITH LOGIN PASSWORD 'memoryops_password';
    END IF;
END
$$;

-- 2. Grant connection and schema privileges
GRANT CONNECT ON DATABASE memoryops_ai TO memoryops_app;
GRANT USAGE ON SCHEMA public TO memoryops_app;

-- 3. Grant access to existing tables and sequences
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO memoryops_app;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO memoryops_app;

-- 4. Grant access to future tables and sequences
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO memoryops_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO memoryops_app;

COMMIT;
