-- MemoryOps AI
-- Migration: 001_initial_schema
-- Purpose: Initial governed memory and audit schema

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;


-- ============================================================
-- MEMORY RECORDS
-- ============================================================

CREATE TABLE memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    tenant_id TEXT NOT NULL,
    user_id TEXT NOT NULL,

    content TEXT NOT NULL,

    memory_type TEXT NOT NULL
        CHECK (
            memory_type IN (
                'semantic',
                'procedural',
                'episodic'
            )
        ),

    status TEXT NOT NULL DEFAULT 'active'
        CHECK (
            status IN (
                'active',
                'pending',
                'rejected',
                'archived',
                'deleted'
            )
        ),

    sensitivity TEXT NOT NULL DEFAULT 'low'
        CHECK (
            sensitivity IN (
                'low',
                'medium',
                'high'
            )
        ),

    importance SMALLINT NOT NULL DEFAULT 5
        CHECK (
            importance >= 0
            AND importance <= 10
        ),

    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0
        CHECK (
            confidence >= 0.0
            AND confidence <= 1.0
        ),

    reinforcement_count INTEGER NOT NULL DEFAULT 0
        CHECK (
            reinforcement_count >= 0
        ),

    embedding VECTOR(1536),

    source_kind TEXT NOT NULL DEFAULT 'chat',

    source_conversation_id TEXT,

    source_excerpt TEXT,

    policy_decision TEXT
        CHECK (
            policy_decision IS NULL
            OR policy_decision IN (
                'SAVE',
                'PENDING_APPROVAL',
                'UPDATE_EXISTING',
                'MERGE_WITH_EXISTING'
            )
        ),

    policy_reason TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    deleted_at TIMESTAMPTZ,

    CONSTRAINT deleted_memory_requires_deleted_at
        CHECK (
            status <> 'deleted'
            OR deleted_at IS NOT NULL
        )
);


-- ============================================================
-- MEMORY AUDIT LOGS
-- ============================================================

CREATE TABLE memory_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    tenant_id TEXT NOT NULL,

    user_id TEXT,

    memory_id UUID
        REFERENCES memories(id)
        ON DELETE SET NULL,

    action TEXT NOT NULL,

    reason TEXT,

    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,

    trace_id TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ============================================================
-- MEMORY INDEXES
-- ============================================================

CREATE INDEX idx_memories_scope
    ON memories (
        tenant_id,
        user_id
    );


CREATE INDEX idx_memories_active_scope
    ON memories (
        tenant_id,
        user_id,
        status
    );


CREATE INDEX idx_memories_type
    ON memories (
        tenant_id,
        user_id,
        memory_type
    );


CREATE INDEX idx_memories_created_at
    ON memories (
        created_at DESC
    );


CREATE INDEX idx_memories_deleted_at
    ON memories (
        deleted_at
    )
    WHERE deleted_at IS NOT NULL;


-- ============================================================
-- AUDIT INDEXES
-- ============================================================

CREATE INDEX idx_memory_audit_scope
    ON memory_audit_logs (
        tenant_id,
        user_id
    );


CREATE INDEX idx_memory_audit_memory
    ON memory_audit_logs (
        memory_id
    );


CREATE INDEX idx_memory_audit_created_at
    ON memory_audit_logs (
        created_at DESC
    );


CREATE INDEX idx_memory_audit_trace
    ON memory_audit_logs (
        trace_id
    )
    WHERE trace_id IS NOT NULL;


COMMIT;