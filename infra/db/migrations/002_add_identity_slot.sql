-- MemoryOps AI
-- Migration: 002_add_identity_slot
-- Purpose: Add identity_slot for governed write-path mutations

BEGIN;

-- Add identity_slot column with constraint enforcing canonical slot grammar
ALTER TABLE memories
    ADD COLUMN identity_slot TEXT NULL
    CONSTRAINT check_identity_slot_grammar
        CHECK (
            identity_slot IS NULL
            OR identity_slot ~ '^[a-z][a-z0-9_]{0,63}$'
        );

-- Add composite partial index optimized for active-slot lookups
CREATE INDEX idx_memories_identity_active
    ON memories (
        tenant_id,
        user_id,
        memory_type,
        identity_slot
    )
    WHERE status = 'active'
    AND identity_slot IS NOT NULL;

COMMIT;
