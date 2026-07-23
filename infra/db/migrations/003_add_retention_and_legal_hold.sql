-- MemoryOps AI
-- Migration: 003_add_retention_and_legal_hold
-- Purpose: Add columns for retention and legal holds, and create lifecycle run history table

BEGIN;

-- 1. Add retention and legal hold columns to memories
ALTER TABLE memories
    ADD COLUMN legal_hold BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN expires_at TIMESTAMPTZ NULL;

-- 2. Add composite index optimized for active-memory retention scans
CREATE INDEX idx_memories_retention
    ON memories (
        status,
        expires_at
    )
    WHERE status = 'active'
    AND expires_at IS NOT NULL;

-- 3. Add composite index optimized for soft-deleted compaction scans
CREATE INDEX idx_memories_compaction
    ON memories (
        status,
        deleted_at
    )
    WHERE status = 'deleted';

-- 4. Create lifecycle run history table
CREATE TABLE lifecycle_run_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    job_name TEXT NOT NULL,
    
    status TEXT NOT NULL
        CHECK (
            status IN (
                'running',
                'success',
                'failed'
            )
        ),
        
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    completed_at TIMESTAMPTZ,
    
    error_message TEXT,
    
    records_processed INTEGER NOT NULL DEFAULT 0
        CHECK (
            records_processed >= 0
        ),
        
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);

-- Index run history by job name and started_at
CREATE INDEX idx_lifecycle_run_job
    ON lifecycle_run_history (
        job_name,
        started_at DESC
    );

COMMIT;
