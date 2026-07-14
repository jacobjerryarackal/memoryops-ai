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
| **Phase 0** | Design spine: product definition, architecture, security, governance, ADRs, schema, API contracts | **v0.1.0** |
| **Phase 1** | Core write path: gateway → extractor → policy broker → write service → repository → audit | **v0.2.0** |
| **Phase 2** | Read path: retriever → ranker → context composer | **v0.3.0** |
| **Phase 3** | Governance control plane: approve, reject, edit, archive, delete, audit | **v0.4.0** |
| **Phase 4** | Production depth: pgvector, tenant isolation, evaluations, observability | **v0.5.0** |
| **Phase 5** | Background intelligence: decay, archive, deletion verification, reflection | **v0.6.0** |
| **Phase 6** | Deletion compaction and vector purge verification | **v0.7.0** |
| **Phase 7** | Worker runtime and scheduled lifecycle orchestration | **v0.8.0** |
| **Phase 8** | Public results dashboard and evidence explorer | **v0.9.0** |
| **Phase 9** | Retention, legal hold, and consent-aware memory | **v0.10.0** |
| **Phase 10** | SDK and integration examples | **v0.11.0** |
| **Phase 11** | Interactive playground and hosted demo | **v0.12.0** |
| **Phase 12** | Production hardening and stable governed runtime | **v1.0.0** |

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

# Phase 4 — Production Depth (v0.5.0)

## Goal
Incorporate pgvector persistence, database-level tenant isolation, and automated evaluation metrics.

## Deliverables
- Production PostgreSQL storage repository with pgvector indexes.
- Tenant isolation verification tests.
- Evaluation suite for retrieval relevance and policy correctness.
- OpenTelemetry integration and tracing.

## Exit Criteria
- Vector-based semantic search executes in database.
- Automated tests verify tenant isolation at the repository boundary.

---

# Phase 5 — Background Intelligence (v0.6.0)

## Goal
Implement background lifecycle operations such as memory decay, reflection, and conflict resolution.

## Deliverables
- Background lifecycle worker orchestration.
- Memory decay algorithms.
- Conflict detection and merge proposals.

## Exit Criteria
- Memory decay and reflection proposals run asynchronously without interrupting chat paths.

---

# Phase 6 — Deletion Compaction (v0.7.0)

## Goal
Implement physical content and vector purge compaction for soft-deleted records.

## Deliverables
- Compaction runner that purges content and vectors for deleted rows.
- Preservation of content-free deletion tombstones.

## Exit Criteria
- Deleted memory content is cleared from disk/indexes while preserving the audit footprint.

---

# Phase 7 — Worker Runtime (v0.8.0)

## Goal
Ensure operational stability, locking, and scheduling of background jobs.

---

# Phase 8 — Results Dashboard (v0.9.0)

## Goal
Provide a read-only monitoring interface to view system metrics and evidence.

---

# Phase 9 — Retention and Consent (v0.10.0)

## Goal
Integrate retention windows, consent withdrawal tracking, and legal holds.

---

# Phase 10 — SDK and Integrations (v0.11.0)

## Goal
Provide a typed client SDK for simple third-party integration.

---

# Phase 11 — Interactive Playground (v0.12.0)

## Goal
Deploy a web interface for developers to test the complete memory loop.

---

# Phase 12 — Production Hardening (v1.0.0)

## Goal
Execute stable release validation, penetration testing, and performance benchmarking.

---

# Definition of Done

A phase is considered complete only when:
- Scoped code is implemented and verified.
- Unit and integration tests validate the invariants.
- Documentation and architecture reflect actual behavior.
- All lifecycle mutations generate append-only audit evidence.