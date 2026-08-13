# MemoryOps AI — Phase 3A: Reality Audit Report

This report provides a comprehensive architectural and operational reality audit of the MemoryOps AI repository, verifying whether the production-grade guarantees claimed by the system are actually supported by the current implementation.

---

## Executive Summary

A comprehensive reconnaissance of the MemoryOps AI repository reveals a significant disparity between high-level architectural claims and actual implementation details. While core algorithmic behaviors (such as deterministic ranker tie-breaking and optimistic concurrency control) are correctly implemented in the repository layer, the security boundaries and production infrastructure are either missing, bypassed, or mocked.

Specifically:
- **Authentication and Authorization** are entirely absent from all HTTP endpoints, despite being implemented as helper classes in the services layer.
- **Row-Level Security (RLS)** is enabled in migration scripts but bypassed in production because the application connects to PostgreSQL using the superuser/owner account (`postgres`) by default.
- **In-Memory Transactions** suffer from a severe concurrency race condition where a rollback in one request wipes out concurrent writes from other requests.
- **The Evaluation Engine** metrics are 100% because the runner is hardcoded to run isolated test scenarios in-memory using a mock embedding service that yields identical similarity scores.
- **Lifecycle Management Workers** are written but are never started during the API gateway lifecycle.

Confidence in these findings is **High**, backed by codebase source inspection, database schema queries, and baseline test execution telemetry.

---

## Verified Guarantees

The following claims are fully verified in the codebase:

### 1. Deterministic Retrieval
* **Evidence:** Implemented in [postgres.py:search_candidates](file:///d:/AI/memoryops-ai/services/api/app/repositories/postgres.py#L614-L655) and [memory.py:list_active](file:///d:/AI/memoryops-ai/services/api/app/repositories/memory.py#L126-L147).
* **Implementation:** Ties are deterministically broken using `ORDER BY (1 - (embedding <=> $3)) DESC, created_at DESC, id ASC` in PostgreSQL, and custom sorting in-memory.
* **Test Evidence:** Asserted in `tests/test_postgres_repository.py::test_postgres_list_active_deterministic_ordering` and `tests/test_negative_controls.py::test_negative_control_tie_ordering_detection`.
* **Confidence:** High
* **Severity:** N/A (Successfully verified)

### 2. Optimistic Concurrency Control (OCC)
* **Evidence:** Implemented in [postgres.py:update](file:///d:/AI/memoryops-ai/services/api/app/repositories/postgres.py#L417-L513) and [memory.py:update](file:///d:/AI/memoryops-ai/services/api/app/repositories/memory.py#L45-L89).
* **Implementation:** The update method checks that `persisted.version == record.version` and increments `version = version + 1` inside a transaction. In PostgreSQL, it asserts that the query returns `"UPDATE 1"` and throws a `ValueError("Concurrency conflict...")` if 0 rows are affected.
* **Test Evidence:** Verified in `tests/test_rls_adversarial.py::test_postgres_optimistic_concurrency_control`.
* **Confidence:** High
* **Severity:** N/A (Successfully verified)

### 3. Transaction/Savepoint Rollback (PostgreSQL)
* **Evidence:** Implemented in [transactions.py:TransactionManager](file:///d:/AI/memoryops-ai/services/api/app/repositories/transactions.py#L19-L55) and wrapped in [write.py:WriteService:process](file:///d:/AI/memoryops-ai/services/api/app/services/write.py#L56-L99).
* **Implementation:** In PostgreSQL mode, nested transactions are mapped to database `SAVEPOINT`s automatically using asyncpg's transaction manager. A failure inside a nested transaction block correctly rolls back to the savepoint without aborting the parent transaction.
* **Test Evidence:** Verified in `tests/test_transaction_rollback.py::test_postgres_nested_savepoint_rollback` and `tests/test_transaction_rollback.py::test_postgres_transaction_rollback`.
* **Confidence:** High
* **Severity:** N/A (Successfully verified)

---

## Partially Verified Guarantees

The following claims are partially implemented but have significant operational gaps:

### 1. Row-Level Security (RLS)
* **Evidence:** Migration file [004_add_row_level_security.sql](file:///d:/AI/memoryops-ai/infra/db/migrations/004_add_row_level_security.sql) and [postgres.py:scoped_connection](file:///d:/AI/memoryops-ai/services/api/app/repositories/postgres.py#L164-L195).
* **Implementation:** PostgreSQL tables `memories` and `memory_audit_logs` have RLS policies checking `current_setting('app.bypass_rls')` or matching `tenant_id` and `user_id`. Python sets these settings in database transactions via `SET LOCAL`.
* **Gaps:** 
  > [!IMPORTANT]
  > Superusers always bypass RLS. By default, the application connects as the database owner `postgres` (configured in `.env` and [config.py](file:///d:/AI/memoryops-ai/services/api/app/config.py#L19)). This means RLS is bypassed in default production deployments.
  > The RLS enforcement only functions when the application is reconfigured to connect using the restricted `memoryops_app` role.
* **Test Evidence:** RLS enforcement is only tested in `tests/test_rls_adversarial.py` which explicitly overrides the database credentials to use the restricted role. All other test suites (e.g., `test_postgres_repository.py`) run as the superuser, bypassing RLS.
* **Confidence:** High
* **Severity:** High

### 2. Context Admission
* **Evidence:** Implemented in [retrieval.py:ContextAdmissionLayer](file:///d:/AI/memoryops-ai/services/api/app/services/retrieval.py#L154-L242).
* **Implementation:** Evaluates retrieved candidates against PII, Length, and Downrank policies post-retrieval.
* **Gaps:** The admission layer processes text representations, but the downstream LLM answer generation is completely mocked in the chatbot API pipeline.
* **Test Evidence:** Verified in `tests/test_admission_layer.py`.
* **Confidence:** High
* **Severity:** Medium

### 3. Idempotency
* **Evidence:** Implemented in [idempotency.py:IdempotencyService](file:///d:/AI/memoryops-ai/services/api/app/services/idempotency.py#L13-L70).
* **Implementation:** Intercepts `X-Idempotency-Key` headers on chat, patch, and delete API endpoints.
* **Gaps:** 
  > [!WARNING]
  > The service checks an in-memory dictionary fallback `self._in_memory_store` first. If present, it returns the response immediately without hitting PostgreSQL. In multi-instance API deployments, this results in split-brain behavior where requests hitting different container instances bypass idempotency keys.
* **Test Evidence:** Asserted in `tests/test_idempotency.py` which cleans only the shared in-memory dictionary.
* **Confidence:** High
* **Severity:** Medium

---

## Unverified Claims

The following claims are completely unverified, mocked, or bypassed:

### 1. JWT Authentication
* **Evidence:** Class `MockBearerAuthService` in [auth.py](file:///d:/AI/memoryops-ai/services/api/app/services/auth.py#L29-L58).
* **Implementation:** The service splits bearer tokens on hyphens (e.g., `token-{tenant}-{user}`) to resolve tenant and user scope.
* **Gaps:** There is **NO** true cryptographic validation of JWT tokens, no signature checks, no JWKS fetching, and no expiry enforcement.
* **Confidence:** High
* **Severity:** Critical

### 2. Authorization Scopes
* **Evidence:** Class `ScopeChecker` in [auth.py](file:///d:/AI/memoryops-ai/services/api/app/services/auth.py#L135-L148).
* **Gaps:** 
  > [!CRITICAL]
  > Although `ScopeChecker` exists, it is **never injected** as a FastAPI dependency in any active routing endpoint. 
  > All endpoints in [chat.py](file:///d:/AI/memoryops-ai/services/api/app/routes/chat.py) and [governance.py](file:///d:/AI/memoryops-ai/services/api/app/routes/governance.py) accept `tenant_id` and `user_id` as raw query parameters or JSON body fields, with zero authentication or authorization dependencies. Anyone can query, update, or purge any memory in the system without a credentials check.
* **Test Evidence:** `tests/test_auth_gate.py` asserts scope checker behavior using a dummy standalone FastAPI app. The actual API routes are never validated for authentication in integration tests.
* **Confidence:** High
* **Severity:** Critical

### 3. Lifecycle Management Scheduler
* **Evidence:** Class `WorkerScheduler` in [lifecycle.py](file:///d:/AI/memoryops-ai/services/api/app/services/lifecycle.py#L147-L225).
* **Gaps:** The background job scheduler is never started or registered in [main.py](file:///d:/AI/memoryops-ai/services/api/app/main.py). In production, background jobs (like retention deletion and physical compaction) never run automatically.
* **Confidence:** High
* **Severity:** High

---

## Security Findings

### 1. API Authentication Bypass
* **File:** [routes/chat.py](file:///d:/AI/memoryops-ai/services/api/app/routes/chat.py) & [routes/governance.py](file:///d:/AI/memoryops-ai/services/api/app/routes/governance.py)
* **Vulnerability:** Endpoints do not use `Depends(get_current_identity)` or `ScopeChecker`.
* **Impact:** Cross-tenant leakage. Any external user can inspect or purge records of any tenant by guessing the `tenant_id`.
* **Severity:** Critical

### 2. Database RLS Bypass by Owner Connection
* **File:** [repositories/postgres_connection.py](file:///d:/AI/memoryops-ai/services/api/app/repositories/postgres_connection.py#L65) & [config.py](file:///d:/AI/memoryops-ai/services/api/app/config.py#L19-L20)
* **Vulnerability:** Default database username is `postgres` (superuser).
* **Impact:** Superusers bypass RLS. Even though `scoped_connection` sets session parameters, PostgreSQL ignores them and allows access to all rows because the connection is authenticated as a superuser.
* **Severity:** Critical

---

## Data Integrity Findings

### 1. In-Memory Transaction Concurrency Data Erasure
* **File:** [repositories/transactions.py:TransactionManager](file:///d:/AI/memoryops-ai/services/api/app/repositories/transactions.py#L56-L97)
* **Vulnerability:** In-memory simulated rollback does:
  ```python
  repo._records.clear()
  repo._records.update(snap["records"])
  ```
* **Impact:** If Request A starts a transaction and takes a snapshot, and Request B concurrently updates `_records`, Request A failing and rolling back will clear the entire repository dictionary and restore its snapshot, silently deleting Request B's concurrent writes.
* **Severity:** High

---

## Retrieval/Evaluation Findings

### 1. Synthetic Evaluation Suite
* **File:** [evals/runner.py](file:///d:/AI/memoryops-ai/evals/runner.py#L148)
* **Finding:** The evaluation suite metrics (Precision=100%, Recall=100%, Tenant Leakage=0%) are synthetic.
* **Details:**
  1. The runner is hardcoded to instantiate `InMemoryMemoryRepository()` for every scenario. It never runs on PostgreSQL/pgvector.
  2. The database is cleared and seeded with only 1-2 memories specifically crafted for the test case, eliminating semantic distractors or cross-contamination.
  3. The embedding service is mocked (`MockEmbeddingService`) to return `[0.1] * 1536` for every query, meaning all cosine distances are identical and ties are resolved lexically.
* **Severity:** Medium (Provides false confidence in retrieval accuracy)

---

## SDK Findings

### 1. Network Hanging & Missing Capabilities
* **File:** [sdk/memoryops-sdk/memoryops_sdk/client.py](file:///d:/AI/memoryops-ai/sdk/memoryops-sdk/memoryops_sdk/client.py#L26)
* **Gaps:**
  1. `requests.request` is called with no timeout parameter, allowing requests to hang indefinitely.
  2. There is no retry policy or exponential backoff helper.
  3. The SDK has **no update/patch method**, meaning clients cannot update active memories or edit metadata.
  4. The client does not support passing Custom Headers or Idempotency Keys.
* **Severity:** High

---

## Observability Findings

### 1. Logging-Only Telemetry
* **File:** [services/observability.py](file:///d:/AI/memoryops-ai/services/api/app/services/observability.py#L14-L45)
* **Finding:** The system records telemetry spans and metrics by serializing events as JSON lines and emitting them to standard log outputs. There is no active integration with OpenTelemetry exporters or APM collectors.
* **Severity:** Medium

---

## Performance Unknowns

### 1. Database Connection Overhead
* **Finding:** Pytest helper `setup_db` closes and recreates the PostgreSQL pool on every single test execution because of loop-bound connection bindings. This results in significant latency overhead (over 3 minutes for 270 tests).
* **Severity:** Medium (Developer experience friction)

---

## Critical Risks

| Risk Description | Impact | Mitigation (Phase 3B) |
| :--- | :--- | :--- |
| **API Cross-Tenant Leakage** | Unauthorized data access across all tenants. | Inject auth dependencies into all route endpoints. |
| **RLS Bypass in Production** | DB connection credentials bypass RLS. | Change default connection username to `memoryops_app`. |
| **In-Memory Concurrency Loss** | Transactions can delete concurrent records on rollback. | Refactor in-memory rollback to restore only modified keys instead of clearing. |
| **Un-compacted Deleted Data** | Logically deleted records never physically purge in production. | Register and start the `WorkerScheduler` in the FastAPI lifespan. |

---

## Recommended Phase 3B Work

1. **Inject Authentication Gates into REST API Routes:** Require token headers and inject `ScopeChecker` into FastAPI endpoints in `routes/chat.py` and `routes/governance.py`.
2. **Enforce Restricted Role Connections:** Configure production and default settings to connect as `memoryops_app` instead of `postgres` to enable Row-Level Security checks.
3. **Refactor In-Memory Transaction Snapshots:** Modify `TransactionManager` in-memory rollback to track and revert only mutated keys (an undo log) rather than clearing the entire `_records` store.
4. **Wire Background Scheduler into lifespan:** Call `WorkerScheduler.start` inside the gateway app lifespan in `main.py`.
5. **Add SDK Update/Patch Support and Connection Hardening:** Implement a `patch()` method in the client, and add default timeouts and exponential backoffs to `requests` calls.
