# MemoryOps AI — Maturity Gap Analysis

This document provides a comprehensive architectural audit and maturity gap analysis of the MemoryOps AI repository. Findings are categorized by severity based on their impact on production readiness, data integrity, tenant isolation, and security.

---

## 1. Architectural Overview & Boundary Map

```
                          AI Application (SDK / REST client)
                                          │
                                          ▼
                                FastAPI Gateway API
                                          │
                  ┌───────────────────────┼───────────────────────┐
                  │                       │                       │
         Authentication &        Write & Read Path         Governance &
       Authorization Boundary       Pipelines (Spine)     Lifecycle workers
                  │                       │                       │
                  └───────────────────────┼───────────────────────┘
                                          │
                                          ▼
                         PostgreSQL + pgvector (with RLS)
```

The system boundaries separate the **FastAPI Gateway**, **Pipelines (Write/Read)**, **Governance & Lifecycle Workers**, and the **PostgreSQL Storage Layer**.

---

## 2. Gap Classification Matrix

| ID | Finding | Severity | Category | Status |
|---|---|---|---|---|
| **GAP-01** | Missing Row-Level Security (RLS) in Database | **CRITICAL** | Security & Tenancy | Incomplete |
| **GAP-02** | No Authentication and Authorization Abstractions | **CRITICAL** | Security | Incomplete |
| **GAP-03** | No Context Admission Layer in Read Path | **HIGH** | Retrieval & Privacy | Incomplete |
| **GAP-04** | No Structured Evidence/Provenance API | **HIGH** | Governance | Incomplete |
| **GAP-05** | Lack of a Python Client SDK | **HIGH** | Developer Experience | Incomplete |
| **GAP-06** | Missing Merge, Redact, and Defer write policies | **HIGH** | Write Path Governance | Incomplete |
| **GAP-07** | Quality Gates & Scorecard not integrated into pipeline | **MEDIUM** | Evals & CI/CD | Incomplete |
| **GAP-08** | Lack of Idempotency Keys and Concurrency Controls | **MEDIUM** | Reliability | Incomplete |
| **GAP-09** | Lack of Deterministic Failure Injection Suite | **MEDIUM** | Testing | Incomplete |
| **GAP-10** | Expensive PostgreSQL connection re-init in test runner | **MEDIUM** | Dev Experience | Incomplete |
| **GAP-11** | No Public Playground / Demo Interface | **LOW** | Ergonomics | Incomplete |

---

## 3. Detailed Gap Findings

### CRITICAL

#### GAP-01: Missing Row-Level Security (RLS) in Database
* **Current Implementation:** Application code is expected to filter queries with `tenant_id` and `user_id` at the repository query layer. The database has no constraints or policies enforcing this isolation.
* **Problem:** Any application-level bug, missing where clause, or connection leak allows cross-tenant query execution. The DB pool connects as a superuser/owner (`postgres`).
* **Risk:** Cross-tenant data leakage and regulatory compliance violations (e.g., GDPR).
* **Proposed Solution:** Enable PostgreSQL Row-Level Security (RLS) on `memories` and `memory_audit_logs`. Set up `app.current_tenant_id` session configurations using `SET LOCAL` within every database transaction, verified by RLS policies.
* **Affected Files:**
  * [postgres_connection.py](file:///d:/AI/memoryops-ai/services/api/app/repositories/postgres_connection.py)
  * [postgres.py](file:///d:/AI/memoryops-ai/services/api/app/repositories/postgres.py)
  * `infra/db/migrations/`
* **Tests Required:** Adversarial security tests attempting cross-tenant retrieval, insertion, update, and deletion under a restricted connection scope.
* **Migration Impact:** Add schema migration to enable RLS and create security policies.
* **Backward Compatibility Impact:** None.

#### GAP-02: No Authentication and Authorization Abstractions
* **Current Implementation:** HTTP API routes accept `tenant_id` and `user_id` as raw query parameters or JSON body fields with zero authentication or authorization checks.
* **Problem:** Unauthenticated clients can manipulate, query, or purge memory records for any tenant. There are no interfaces separating authentication ("Who are you?") from authorization ("What can you do?").
* **Risk:** Unauthorized data access, credential abuse, and injection attacks.
* **Proposed Solution:** Implement authentication dependencies. Create clean, adapter-oriented interfaces for:
  * `AuthenticationService`
  * `AuthorizationService`
  * `Identity` (supporting Token, API Key, and Session resolutions)
  * Support a production security boundary (JWT/API keys validation) and local development bypass mode.
* **Affected Files:**
  * [main.py](file:///d:/AI/memoryops-ai/services/api/app/main.py)
  * `services/api/app/routes/`
  * `services/api/app/domain/`
* **Tests Required:** Security integration tests asserting token validation, scope checking, and mock token bypass.
* **Migration Impact:** None.
* **Backward Compatibility Impact:** API callers must supply authentication headers in production.

---

### HIGH

#### GAP-03: No Context Admission Layer in Read Path
* **Current Implementation:** Retrieved memories that pass the character budget are directly formatted into plain text and injected into the LLM context.
* **Problem:** There is no intermediate gate assessing if ranked memories are safe, compliant, or appropriate for context injection.
* **Risk:** Injecting sensitive memories (PII, credentials) or irrelevant data into the LLM prompt.
* **Proposed Solution:** Create a `ContextAdmission` component that runs after ranking but before context composition. Supports decisions:
  * `ALLOW` (inject as is)
  * `DENY` (drop entirely)
  * `REDACT` (mask sensitive tokens)
  * `TRUNCATE` (trim content to fit character/token limit)
  * `DOWNRANK` (force lower positioning in prompt composition)
* **Affected Files:**
  * [retrieval.py](file:///d:/AI/memoryops-ai/services/api/app/services/retrieval.py)
  * [retrieval.py](file:///d:/AI/memoryops-ai/services/api/app/domain/retrieval.py)
* **Tests Required:** Context admission test cases covering sensitivity-based blocking, redaction, and truncation logic.
* **Migration Impact:** None.
* **Backward Compatibility Impact:** None.

#### GAP-04: No Structured Evidence/Provenance API
* **Current Implementation:** Audit records are written to a table, but there is no API endpoint to query a consolidated "evidence bundle" explaining why a memory exists, why it was retrieved, or why it was admitted.
* **Problem:** Developers and compliance officers cannot trace memory lifecycle decisions programmatically.
* **Risk:** Audit failure and lack of explainability.
* **Proposed Solution:** Implement `GET /api/memories/{memory_id}/evidence` returning a structured provenance bundle including:
  * Policy decisions & rules fired during admission
  * Retrieval score, ranking position, and context admission results
  * Modifications & trace IDs
* **Affected Files:**
  * `services/api/app/routes/governance.py`
  * `services/api/app/services/governance.py`
  * `services/api/app/domain/`
* **Tests Required:** Verification of evidence payload structures and linked audit timelines.
* **Migration Impact:** None.
* **Backward Compatibility Impact:** None.

#### GAP-05: Lack of a Python Client SDK
* **Current Implementation:** Clients must interact with MemoryOps AI via raw HTTP REST queries.
* **Problem:** Developers must write custom HTTP boilerplate, manual trace propagation, and retry logic.
* **Risk:** Inconsistent usage patterns and slow platform adoption.
* **Proposed Solution:** Package a typed Python client SDK (`memoryops-sdk`) exposing client capabilities:
  * `client.remember(...)` (write path)
  * `client.recall(...)` (read path)
  * `client.delete(...)` (logical deletion)
  * `client.explain(...)` (retrieve ranking and evidence details)
* **Affected Files:**
  * New folder `sdk/memoryops-sdk/`
* **Tests Required:** Client connection mock tests, token propagation tests.
* **Migration Impact:** None.
* **Backward Compatibility Impact:** None.

#### GAP-06: Missing Merge, Redact, and Defer Write Policies
* **Current Implementation:** Write path supports `SAVE`, `UPDATE_EXISTING`, `PENDING_APPROVAL`, `BLOCK`, `DROP_LOW_UTILITY`. Decisions like `MERGE_WITH_EXISTING` raise an unsupported error.
* **Problem:** Proposing semantic updates that should merge with existing slots is blocked or causes duplicates.
* **Risk:** Cluttered state database and duplicate memory records.
* **Proposed Solution:** Implement `MERGE_WITH_EXISTING` mutation handler. Add `REDACT` (strip sensitive parts before saving) and `DEFER` (put candidate on hold pending manual policy review).
* **Affected Files:**
  * [write.py](file:///d:/AI/memoryops-ai/services/api/app/services/write.py)
* **Tests Required:** Integration tests asserting successful content merging, redaction of sensitive tokens, and deferred states.
* **Migration Impact:** None.
* **Backward Compatibility Impact:** None.

---

### MEDIUM

#### GAP-07: Quality Gates & Scorecard not integrated into pipeline
* **Current Implementation:** Golden dataset and runner exist, but metrics are not validated against targets during build processes.
* **Problem:** Regressions in retrieval quality or policy safety go unnoticed.
* **Risk:** Silent quality decay of retrieval pipelines.
* **Proposed Solution:** Create a deterministic scorecard builder exporting `evals/scorecard.json` and generating `docs/evaluation/scorecard.md`. Integrate validation rules into the CI/CD scripts to block releases if metrics fall below gates (e.g. 100% security, >=90% relevance).
* **Affected Files:**
  * `evals/`
* **Tests Required:** Verify evaluation runner exits with code 1 if thresholds regress.
* **Migration Impact:** None.
* **Backward Compatibility Impact:** None.

#### GAP-08: Lack of Idempotency Keys and Concurrency Controls
* **Current Implementation:** Write service relies on postgres transactions but doesn't handle idempotency keys or optimistic lock checks.
* **Problem:** Double submissions lead to duplicate records. Concurrent updates on identical slots trigger race conditions.
* **Risk:** Database duplication and race anomalies.
* **Proposed Solution:** Introduce optional idempotency key headers on `POST /api/chat`. Implement optimistic concurrency control via a `version` or `updated_at` check on memory mutations.
* **Affected Files:**
  * [write.py](file:///d:/AI/memoryops-ai/services/api/app/services/write.py)
  * [postgres.py](file:///d:/AI/memoryops-ai/services/api/app/repositories/postgres.py)
* **Tests Required:** Concurrent write conflict simulations and duplicate requests with identical idempotency keys.
* **Migration Impact:** None.
* **Backward Compatibility Impact:** None.

#### GAP-09: Lack of Deterministic Failure Injection Suite
* **Current Implementation:** Basic exception handling exists, but there are no targeted tests asserting recovery behaviors under database disconnects, vector server failures, or transaction aborts.
* **Problem:** We cannot guarantee transaction safety and rollback isolation in production failure modes.
* **Risk:** Incomplete database updates and orphan audit trails.
* **Proposed Solution:** Build a failure injection harness mocking DB connection drops, vector dimension errors, and policy exceptions. Assert transaction rollbacks.
* **Affected Files:**
  * `tests/`
* **Tests Required:** Rollback and recovery verification tests.
* **Migration Impact:** None.
* **Backward Compatibility Impact:** None.

#### GAP-10: Expensive PostgreSQL connection re-init in test runner
* **Current Implementation:** `clean_all` and `setup_db` close and recreate the database pool on every single test execution because of loop-bound connection bindings.
* **Problem:** Extremely slow test suite execution.
* **Risk:** High developer friction and slow feedback loops.
* **Proposed Solution:** Reconfigure pytest-asyncio to run tests using a shared loop, or cache/reuse connection pool across async tests, resetting pool states without closing it.
* **Affected Files:**
  * `tests/conftest.py`
  * `tests/test_postgres_repository.py`
* **Tests Required:** Verify test times drop below 30s.
* **Migration Impact:** None.
* **Backward Compatibility Impact:** None.

---

### LOW

#### GAP-11: No Public Playground / Demo Interface
* **Current Implementation:** Next.js frontend has been initialized, but lacks active chat playground or demo scripts mapping read/write pipeline steps.
* **Problem:** Hard to visualize the platform's value and decision processes.
* **Risk:** Weak developer adoption and visual presentation.
* **Proposed Solution:** Build a simple chat playground frontend demonstrating extraction, policy broker outcomes, ranking weights, context selection, logical deletion, and evidence bundle view.
* **Affected Files:**
  * `frontend/`
* **Tests Required:** None (manual verification).
* **Migration Impact:** None.
* **Backward Compatibility Impact:** None.
