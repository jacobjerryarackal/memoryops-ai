# MemoryOps AI Roadmap

**Version:** 0.1
**Status:** Phase 0 — Design Spine

---

# Purpose

This roadmap defines the engineering evolution of MemoryOps AI.

The roadmap uses **Engineering Phases** as the primary implementation gates. Project release versions are kept distinct from these phases to decouple structural development milestones from application deployment versions.

---

# Phase to Version Mapping

The platform progresses through the following gated milestones:

| Engineering Phase | Scope | Release Version |
|---|---|---|
| **Phase 0** | Design spine: product definition, architecture, security, governance, ADRs, schema, API contracts | **v0.1.0** (Done) |
| **Phase 1** | Core write path: gateway → extractor → policy broker → write service → repository → audit | **v0.2.0** (Done) |
| **Phase 2** | Read path: retriever → ranker → context composer | **v0.3.0** (Done) |
| **Phase 3** | Governance control plane backend and API endpoints | **v0.4.0** (Done) |
| **Phase 4** | Unified Interactive Frontend (Next.js): chat UI, review queue, metrics dashboard, audit explorer | **v0.5.0** |
| **Phase 5** | Production Persistence & Observability Depth: pgvector, PostgreSQL storage, isolation verification | **v0.6.0** |
| **Phase 6** | Advanced Background Lifecycle & Compaction: workers, decay, reflection, physical compaction | **v0.7.0** |
| **Phase 7** | Production Hardening, Client SDK, and Stable governed release | **v1.0.0** |

---

# Phase 0 — Design Spine (v0.1.0)

## Goal
Establish the technical design spine, system architecture, database schema, security invariants, governance model, and HTTP API contracts before implementation begins.

## Exit Criteria
- Security, governance, and architecture documents are reviewed and approved.
- Executable SQL database schema is drafted.
- API contract endpoints are formally defined.

---

# Phase 1 — Core Write Path (v0.2.0)

## Goal
Implement the core write pipeline that processes incoming information, runs automated policies, and persists memory with provenance and audit logs.

## Deliverables
- FastAPI gateway hosting `POST /api/chat`.
- In-memory repository implementing memory storage.
- Extractor service that proposes candidate memories.
- Policy Broker evaluating candidates (`SAVE`, `PENDING_APPROVAL`, `BLOCK`, `DROP_LOW_UTILITY`, `UPDATE_EXISTING`, `MERGE_WITH_EXISTING`).
- Write Service executing broker outcomes.
- Audit Service capturing append-only audit evidence.

## Exit Criteria
- System successfully processes messages and persists eligible memory.
- Prohibited secrets and credentials are blocked before storage.
- Audit records are successfully written to database logs.

---

# Phase 2 — Read Path (v0.3.0)

## Goal
Enable context composition for LLMs by retrieving relevant active memories while strictly respecting governance boundaries.

## Deliverables
- Hybrid Retriever (combining semantic and lexical queries).
- Deterministic Ranker using normalized signals.
- Context Composer formatting top-ranked memories.
- `used_memories` explainability metadata in responses.

## Exit Criteria
- Only `active` memories are retrievable.
- Pending, rejected, archived, and deleted memories are structurally excluded from retrieval.
- Retrieval degrades gracefully under service faults.

---

# Phase 3 — Governance Control Plane (v0.4.0)

## Goal
Introduce administrative capabilities and lifecycle controls to allow operators to review, mutate, and delete memories.

## Deliverables
- Governance endpoints (`GET /api/memories`, `PATCH`, `DELETE`).
- Review queue interface to approve/reject pending memories.
- Archival and logical deletion flows.

## Exit Criteria
- Memories can be transitioned between lifecycle states.
- Deleted memories are excluded from all default read operations.
- All actions generate append-only audit events.

---

# Phase 4 — Unified Interactive Frontend (v0.5.0)

## Goal
Deliver a fully interactive Next.js web application implementing the complete user and operator control plane.

## Deliverables
- Next.js application structure initialized.
- **Chat Interface**: Interactive chat to converse with the bot, showing the read path `used_memories` and write path `candidate_memories` with automated policy decisions.
- **Governance Dashboard & Review Queue**: Interface for administrators to approve/reject pending memories, archive or update active memories, and trigger logical deletions.
- **Audit Log & Evidence Explorer**: View and query the append-only audit stream and provenance timeline for any record.
- **Metrics Panel**: Graphical charts for tenant memory status distribution, audit action counts, and system metrics.

## Exit Criteria
- Users and administrators can execute chat, review, deletion, and audit verification actions in a single visual interface connected to the FastAPI backend.

---

# Phase 5 — Production Persistence & Observability Depth (v0.6.0)

## Goal
Replace the in-memory repository with production PostgreSQL and pgvector storage, implement transaction-safe writes, database-level tenant isolation, and operational observability.

## Deliverables
- Production PostgreSQL storage repository with native pgvector index support.
- Transactional mutation-plus-audit atomicity (`BEGIN ... COMMIT` in write/governance service).
- Database-level tenant isolation validation suite.
- OpenTelemetry tracing and structured execution logs.

## Exit Criteria
- Semantic vector similarity search executes natively in the database.
- Repository tests verify 100% tenant isolation at the database boundary.

---

# Phase 6 — Advanced Background Lifecycle & Compaction (v0.7.0)

## Goal
Build background workers and schedules for decay, reflection, retention, and physical deletion compaction.

## Deliverables
- Background lifecycle worker daemon runtime and scheduled task execution.
- Memory decay algorithms and conflict-resolution reflections.
- Physical deletion compaction (wiping deleted content while preserving tombstone footprint).
- Retention windows, legal holds, and consent withdrawal enforcement.

## Exit Criteria
- Background compaction successfully clears soft-deleted record values from disk/indexes without breaking audit timelines.
- Decay and reflection execute asynchronously without interrupting chat latency.

---

# Phase 7 — Production Hardening & Release (v1.0.0)

## Goal
Deliver public release assets, client SDK, security audits, and stable release hardening.

## Deliverables
- Typed Client SDK for simple third-party application integration.
- Penetration testing and secret verification reports.
- Performance profiling and stable v1.0.0 release.

## Exit Criteria
- The system achieves stable performance under target load with zero-trust security clearance.

---

# Definition of Done

A phase is considered complete only when:
- Scoped code is implemented and verified.
- Unit and integration tests validate the invariants.
- Documentation and architecture reflect actual behavior.
- All lifecycle mutations generate append-only audit evidence.