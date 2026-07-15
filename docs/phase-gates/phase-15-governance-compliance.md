# Phase 15 — Governance and Compliance

## Core Question
Can MemoryOps demonstrate why memory state changed and enforce lifecycle governance?

## MemoryOps Mapping
Every write mutation (creation, updates, blocks, merges, deletions) must be approved by the Policy Broker and creates an immutable, append-only `AuditEvent` via the `AuditService`. Soft-deletion is terminal and guarantees logical forgetting from the read paths.

## Gate Conditions
- [x] Lifecycle mutations generate corresponding, structured audit events.
- [x] Audit logs are recorded as an append-only timeline.
- [x] Policy decisions govern memory admissions.
- [x] Soft deletion guarantees complete logical forgetting from retrieval.
- [ ] Database-level immutable constraints (append-only tables/roles) are enforced.

## Evidence
- [audit.py](file:///d:/AI/memoryops-ai/services/api/app/services/audit.py)
- [policy.py](file:///d:/AI/memoryops-ai/services/api/app/services/policy.py)
- [write.py](file:///d:/AI/memoryops-ai/services/api/app/services/write.py)
- [test_audit_service.py](file:///d:/AI/memoryops-ai/tests/test_audit_service.py)

## Gaps
Audit persistence is process-lifetime only (`InMemoryAuditService`). Database-level read-only role constraints or ledger checks are not yet configured.

## Status
PARTIAL

## Next Unlock
Durable PostgreSQL audit service persistence implementation.
