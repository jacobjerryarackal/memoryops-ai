-- MemoryOps AI
-- Migration: 006_add_version_to_memories
-- Purpose: Add version column to memories table for optimistic concurrency control (OCC)

BEGIN;

ALTER TABLE memories ADD COLUMN version INTEGER DEFAULT 1 NOT NULL;

COMMIT;
