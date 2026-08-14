# Changelog

All notable changes to this project will be documented in this file.

---

## [v0.4.0] — 2026-08-14
### Added
*   FastAPI Governance API endpoints: `GET /api/memories`, `PATCH /api/memories/{id}`, `DELETE /api/memories/{id}`.
*   Admin review queue functionality to transition candidate memories between states (`PENDING`, `ACTIVE`, `ARCHIVED`).
*   Audit history tracing endpoints to track mutations and reasons.
*   Support for optimistic concurrency control (OCC) versions and legal holds.

---

## [v0.3.0] — 2026-07-28
### Added
*   Hybrid Retrieval Coordinator combining vector search and Jaccard lexical term queries.
*   Normalized scoring ranker using Jaccard overlaps and database vector distance.
*   Context Composer with token budget limit compliance.
*   Degraded fallback mode when embedding provider is offline.

---

## [v0.2.0] — 2026-06-15
### Added
*   FastAPI Gateway with `/api/chat` RAG pipeline endpoint.
*   Policy Broker to filter coordinates against Regex and secret-blocking policies.
*   Write Service and in-memory mock repository database storage.
*   Append-only Audit Log recorder.

---

## [v0.1.0] — 2026-05-10
### Added
*   Initial project scaffolding.
*   Pydantic schema definitions for `MemoryRecord`, `AuditEvent`, and `CandidateMemory`.
*   Local settings parser (Pydantic Settings) and docker database compose scripts.
