# Phase 06 — Memory Architecture

## Core Question
Does MemoryOps treat memory as governed state across identity, capture, mutation, retrieval, context injection, and deletion?

## MemoryOps Mapping
Memory is scoped by tenant and user and governed by a Policy Broker. Stale embeddings are cleared to `None` upon content mutations. Candidate retrieval is bounded, and candidates are ranked using 6 signals (semantic, keyword, importance, recency, confidence, reinforcement) and tie-breakers. The Context Composer applies character and count budgets. Soft-deleted records are excluded at the repository layer, and the Retriever defensively validates inputs.

## Gate Conditions
- [x] Active scoped candidate isolation is enforced.
- [x] Deterministic 6-signal ranking and tie-breakers are implemented.
- [x] Context character and count budgets are enforced with skip behavior.
- [x] Embedding invalidation on content mutation (ADR-006) is enforced on write path.
- [ ] Database durability and PostgreSQL runtime wiring are established.

## Evidence
- [retrieval.py](file:///d:/AI/memoryops-ai/services/api/app/services/retrieval.py)
- [write.py](file:///d:/AI/memoryops-ai/services/api/app/services/write.py)
- [test_retrieval_services.py](file:///d:/AI/memoryops-ai/tests/test_retrieval_services.py)
- [test_write_service.py](file:///d:/AI/memoryops-ai/tests/test_write_service.py)

## Gaps
Memory persistence is process-lifetime only, utilizing `InMemoryMemoryRepository`. Persistent PostgreSQL/pgvector storage is not wired in.

## Status
PARTIAL

## Next Unlock
Future phase wiring of PostgreSQL and pgvector database persistence.
