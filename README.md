# MemoryOps AI

[![Build Status](https://img.shields.io/badge/build-passing-brightgreen.svg)]()
[![Code Coverage](https://img.shields.io/badge/coverage-97%25-green.svg)]()
[![License](https://img.shields.io/badge/license-MIT-blue.svg)]()
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg)]()
[![Code Style](https://img.shields.io/badge/code%20style-black-000000.svg)]()

Governed long-term memory infrastructure for AI agents — featuring policy-controlled writes, deterministic hybrid retrieval, secure multi-tenancy, context admission controls, state lifecycle decay, and auditable proof-of-decision evidence.

*   **Current Version:** `0.4.0`
*   **Development Status:** Stable Hardened Release Candidate (Phase 3E Complete)
*   **Test Suite:** 283 tests passing cleanly across In-Memory and PostgreSQL runners
*   **Evaluation Pass Rate:** 100% (28 golden cases verified on the benchmark runner)
*   **License:** MIT

---

## Table of Contents

1.  [What Problem Does MemoryOps AI Solve?](#what-problem-does-memoryops-ai-solve)
2.  [Why MemoryOps AI?](#why-memoryops-ai-the-core-thesis)
3.  [Key Features](#key-features)
4.  [Architecture](#architecture)
5.  [How It Works Internally](#how-it-works-internally)
6.  [Why This Technology Stack?](#why-this-technology-stack)
7.  [Security Model](#security-model)
8.  [Evaluation & Quality Gates](#evaluation--quality-gates)
9.  [Performance & Latency Benchmarks](#performance--latency-benchmarks)
10. [Challenges Faced & Solutions](#challenges-faced--solutions)
11. [Failure Handling & Graceful Degradation](#failure-handling--graceful-degradation)
12. [Developer Experience & Quickstart](#developer-experience--quickstart)
13. [Project Structure](#project-structure)
14. [Testing Suite](#testing-suite)
15. [Design Decisions (ADRs)](#design-decisions-adrs)
16. [Limitations](#limitations)
17. [Roadmap](#roadmap)

---

## 1. What Problem Does MemoryOps AI Solve?

In modern LLM applications, long-term memory is typically implemented as a naive vector search cache. While this retrieves context, it fails in production settings due to several operational challenges:

*   **Memory Staleness:** Agent preferences change over time. If a user moves from Boston to Seattle, cosine similarity retrieves both facts, causing conflicting context.
*   **PII & Credential Leaks:** Extractor models are probabilistic. If an LLM extracts an API key or password, raw vector databases store and retrieve it silently.
*   **Unbounded Duplication:** Similar user actions yield duplicate memory records representing the same semantic entity, inflating prompt token costs.
*   **Forgetting & Deletion Invariants:** Soft-deletions must execute cleanly across vector indices. Metadata filters are bypassable and prone to leakages.
*   **Multi-Tenant Isolation:** Relational databases must enforce row-level safety rules on vector lookups without performance penalties.
*   **Prompt Bloat:** Retrieved memories must not blindly flood the model context. Admissions controllers should filter and redact based on budgets.
*   **Auditable Decisions:** Operators need a trace verifying *why* a memory was stored, updated, blocked, or selected.

### The Contrast

#### Naive Vector Retrieval
```text
User Message ──> Embedding Model ──> Vector DB Index ──> Top-K Context Injection
```

#### Governed MemoryOps Pipeline
```text
User Message
 ├──> Candidate Extraction (Content, Slot, Importance)
 ├──> Policy Broker Evaluation (Regex Secret Filter, Sensitivity Route)
 ├──> Identity Slot Resolution (Single-occupant Update vs Multi-occupant Add)
 ├──> Transaction Manager Scope (Savepoints/Snapshot Isolation)
 ├──> Repository Write (PostgreSQL + pgvector / In-Memory Mock)
 ├──> Immutable Auditing (memory_audit_logs Row Insert)
 ├──> Hybrid Retrieval (pgvector Cosine Distance + Python Jaccard Matcher)
 ├──> Deterministic Ranker (Weighted multi-factor score & strict tie-breakers)
 ├──> Context Admission (Character budget, oversized skipping)
 └──> Telemetry & Evidence (Span trace_id propagation)
```

---

## 2. Why MemoryOps AI? (The Core Thesis)

### Memory is System State, Not Merely Embeddings

Embeddings are merely searchable indices. Memory is state. Because it is system state, it must adhere to traditional database rigor:

*   **Governance:** Writes must pass deterministic filters (regex sanitization, token checks) before hitting storage.
*   **Deterministic Decisions:** Context ranking should not fluctuate. Identical query metrics must generate identical prompt contents.
*   **Security:** Multi-tenancy is isolated at the database engine level, not in the application layer where bugs can bypass filters.
*   **Lifecycle:** Inactive memories decay, archive, and undergo secure compaction where text contents and vectors are zeroed out.
*   **Evidence:** Every state transition is recorded in an immutable, append-only audit trail.

---

## 3. Key Features

| Capability | What It Provides | Implemented Evidence / File |
| :--- | :--- | :--- |
| **Governed Writes** | Policy-driven filtering of candidate writes. | [broker.py](file:///d:/AI/memoryops-ai/services/api/app/policy/broker.py) |
| **Hybrid Retrieval** | Combined vector search and lexical Jaccard matching. | [retrieval.py](file:///d:/AI/memoryops-ai/services/api/app/services/retrieval.py) |
| **Context Admission** | Strict character-limit budgeting with oversized skipping. | [retrieval.py](file:///d:/AI/memoryops-ai/services/api/app/services/retrieval.py) |
| **Multi-Tenancy** | Partitioning of records by Tenant ID and User ID. | [postgres.py](file:///d:/AI/memoryops-ai/services/api/app/repositories/postgres.py) |
| **PostgreSQL RLS** | Database-enforced tenant Row-Level Security. | [008_harden_row_level_security.sql](file:///d:/AI/memoryops-ai/infra/db/migrations/008_harden_row_level_security.sql) |
| **JWT Authorization** | JWT verification with tenant-scope check rules. | [auth.py](file:///d:/AI/memoryops-ai/services/api/app/services/auth.py) |
| **Idempotency** | Prevents write duplications via request-key locks. | [idempotency.py](file:///d:/AI/memoryops-ai/services/api/app/services/idempotency.py) |
| **OCC** | Version-column optimistic concurrency checks. | [postgres.py](file:///d:/AI/memoryops-ai/services/api/app/repositories/postgres.py) |
| **Transactions** | contextvars-backed SQL savepoints and memory snapshots. | [transactions.py](file:///d:/AI/memoryops-ai/services/api/app/repositories/transactions.py) |
| **Deletion Guarantees** | Soft deletion followed by vector and content compaction. | [governance.py](file:///d:/AI/memoryops-ai/services/api/app/services/governance.py) |
| **Audit Trails** | Immutable, append-only mutation event logging database. | [audit.py](file:///d:/AI/memoryops-ai/services/api/app/services/audit.py) |
| **Lifecycle Engine** | Background tasks for Decay, Compaction, and Retention. | [lifecycle.py](file:///d:/AI/memoryops-ai/services/api/app/services/lifecycle.py) |
| **SDK** | Typed async HTTP client. | [client.py](file:///d:/AI/memoryops-ai/sdk/memoryops-sdk/memoryops_sdk/client.py) |
| **Evaluation Suite** | Golden scenario runner with programmatic quality gates. | [runner.py](file:///d:/AI/memoryops-ai/evals/runner.py) |
| **Observability** | Trace ID propagation across decorators and logs. | [telemetry.py](file:///d:/AI/memoryops-ai/services/api/app/telemetry.py) |

---

## 4. Architecture

### System Flow
```text
Host AI Client Application
      │
      ▼ (HTTP JSON Payload / JWT Auth Token)
API Gateway (FastAPI Uvicorn)
      │
      ├─► Authentication & Tenant Verification (JWT check)
      │
      ├──► Write Path (Candidate Extraction ──► Policy Broker Evaluation ──► Transaction Manager)
      │      │
      │      ├─► Save/Update/Merge (MemoryRecords DB table)
      │      └─► Immutable Evidence (memory_audit_logs DB table)
      │
      └──► Read Path (Query Vectorization ──► Repository Candidates Query ──► Deterministic Ranking)
             │
             └─► Context Admission (Selects memories fit within prompt character limit)
```

---

## 5. How It Works Internally

### Write Path Flow

1.  **Extraction:** LLMs propose a candidate memory containing `content`, `memory_type`, `importance`, and `identity_slot`.
2.  **Secret Filtering:** Regular expressions scan content for credentials (e.g. `sk-[a-zA-Z0-9-]{48,}`) and passwords. Violations trigger an immediate `BLOCK` policy decision.
3.  **Sensitivity Routing:** Candidates flagged as `high` sensitivity are stored with `status = PENDING` and routed to the administrator queue, bypassing retrievability.
4.  **Identity Slot Resolution:** Single-occupant slot configurations (e.g. `user_job_title`) check for active occupants under the user scope:
    *   If occupied, the broker issues an `UPDATE_EXISTING` instruction. The write service patches the old record's content, zeroes out its stale embedding, and increments its schema version.
    *   If unoccupied or multi-occupancy, a new `active` record is created.
5.  **Audit trail:** Writes execute inside a database transaction block, committing the record and inserting a row to `memory_audit_logs` atomically.

### Read Path Flow

1.  **Vectorization:** The query is mapped to a 1536-dimensional float vector.
2.  **Pool Fetching:** The repository fetches up to 50 active candidates matching `status = ACTIVE`, filtering strictly by Tenant ID.
3.  **Lexical Matching:** Python term tokenization splits queries and contents to compute matching coefficients:
    $$\text{keyword\_score} = \frac{\text{matched\_query\_terms}}{\max(\text{total\_unique\_query\_terms}, 1)}$$
4.  **Normalized Scoring:** The ranker blends signals into a single score:
    $$\text{Score} = 0.35 \times \text{semantic} + 0.20 \times \text{lexical} + 0.15 \times \text{importance} + 0.10 \times \text{recency} + 0.10 \times \text{confidence} + 0.10 \times \text{reinforcement}$$
5.  **Tie-Breaking:** Identical scores are resolved deterministically using `created_at` DESC, then `id` (UUID) ASC.
6.  **Context Admission:** Candidates are packed into the context. If a candidate exceeds the remaining token/character budget limit (e.g., `4000` chars), it is **skipped** (not truncated), and subsequent smaller candidates are evaluated.

### Lifecycle Workers

The `LifecycleRunner` periodic schedule registers four background workers:

*   **DecayWorker:** Decrements the importance of unused active records. When importance reaches `0`, it archives the record (`status = archived`).
*   **RetentionWorker:** Evaluates expiration timestamps and transitions records to `deleted`.
*   **ReflectionWorker:** Computes Jaccard similarity metrics over active pools and generates consolidation proposals.
*   **CompactionWorker:** Sanitizes deleted records by zeroing out embeddings and changing content to `"[COMPACTED]"`.

---

## 6. Why This Technology Stack?

*   **Python:** Chosen for its ecosystem of data utilities and native async/await asynchronous constructs.
*   **FastAPI:** Features automatic OpenAPI documentation, clean dependency injection, and Pydantic schema validation.
*   **PostgreSQL:** Serves as the system of record. Transactional ACID properties prevent state mismatches.
*   **pgvector:** Enables vector searches inside the relational DB, avoiding separate index synchronization issues.
*   **Pydantic:** Validates configuration schemas and API payloads.
*   **asyncpg:** A high-performance async database client featuring connection pools.
*   **Next.js & React:** Powers the glassmorphic administration and metrics dashboard.
*   **Docker:** Bundles dependencies for reproducible local and cloud setups.

---

## 7. Security Model

| Security Gate | Level | Enforcement Mechanism |
| :--- | :--- | :--- |
| **Authentication** | Application | JWT signature checks, expiry audits, and issuer validations. |
| **Tenant Isolation** | Database | Row-Level Security (RLS) constraints on PostgreSQL table targets. |
| **RLS Connection Setting** | Database | Context variables set the tenant parameter on active sessions. |
| **Secret Scanning** | Application | Regular expressions block credentials on write attempts. |
| **Immutable Audits** | Database | Restricts SQL schemas to write-only operations for audit tables. |
| **Legal Hold** | Application | Checks `legal_hold` flags to block deletions and compaction. |

---

## 8. Evaluation & Quality Gates

The systematic quality suite ([runner.py](file:///d:/AI/memoryops-ai/evals/runner.py)) evaluates 28 golden dataset test scenarios. All programmatic gates pass:

*   **Mean Precision@K:** 100% (Target: $\ge$ 85.00%)
*   **Mean Recall@K:** 100% (Target: $\ge$ 80.00%)
*   **Mean Reciprocal Rank (MRR):** 100% (Target: $\ge$ 80.00%)
*   **Tenant Leakage Rate:** 0.00% (Target: $\le$ 0.00%)
*   **User Leakage Rate:** 0.00% (Target: $\le$ 0.00%)
*   **Inactive Memory Leakage Rate:** 0.00% (Target: $\le$ 0.00%)
*   **Deleted Memory Leakage Rate:** 0.00% (Target: $\le$ 0.00%)
*   **Budget Overflow Rate:** 0.00% (Target: $\le$ 0.00%)

### Metrics Diagnostics
The latest execution results are committed to [evaluation_evidence.json](file:///d:/AI/memoryops-ai/evals/evaluation_evidence.json).

---

## 9. Performance & Latency Benchmarks

Stress benchmarks compared the In-Memory mock against the PostgreSQL + pgvector backend (aggregating 100 sequential operations, pool size `min=2, max=10`):

### Client Round-Trip Latency (ms)

#### In-Memory Backend (No DB Overhead)
*   **remember (write):** p50 = `24.57 ms` | p95 = `35.95 ms` | p99 = `55.47 ms`
*   **recall (retrieval):** p50 = `18.79 ms` | p95 = `43.98 ms` | p99 = `115.00 ms`
*   **search (list):** p50 = `20.32 ms` | p95 = `33.24 ms` | p99 = `43.80 ms`
*   **explain (audit):** p50 = `18.91 ms` | p95 = `27.93 ms` | p99 = `29.28 ms`
*   **delete:** p50 = `19.76 ms` | p95 = `33.37 ms` | p99 = `36.56 ms`

#### PostgreSQL Backend
*   **remember (write):** p50 = `74.31 ms` | p95 = `295.52 ms` | p99 = `1518.48 ms`
*   **recall (retrieval):** p50 = `23.80 ms` | p95 = `40.83 ms` | p99 = `89.37 ms`
*   **search (list):** p50 = `49.85 ms` | p95 = `76.43 ms` | p99 = `651.19 ms`
*   **explain (audit):** p50 = `24.25 ms` | p95 = `63.22 ms` | p99 = `667.56 ms`
*   **delete:** p50 = `72.17 ms` | p95 = `117.70 ms` | p99 = `915.43 ms`

---

## 10. Challenges Faced & Solutions

### 1. Telemetry Decorators Popped Kwargs
*   **Challenge:** Telemetry decorators popped `trace_id` from keyword args to initialize log spans. This starved downstream retrieval methods of trace context, breaking trace propagation.
*   **Solution:** Refactored decorators in [telemetry.py](file:///d:/AI/memoryops-ai/services/api/app/telemetry.py) to inspect wrapped function signatures. If the method parameter list expects `trace_id`, the decorator retains it in `kwargs` instead of stripping it.

### 2. Pydantic Model Mutation Restriction
*   **Challenge:** Attempting to assign `updated.trace_id = trace_id` on Pydantic schema instances in `write.py` threw validation errors because extra properties are blocked in schemas.
*   **Solution:** Removed the invalid assignment. The trace identifier is passed directly to the repository update contract signature instead of mutating model properties.

### 3. PostgreSQL Docker Pool Test Flakiness
*   **Challenge:** The scheduled execution timing test triggered overlapping database transactions under slow WSL2 container runs, causing database concurrency locks and test flakiness.
*   **Solution:** Refactored [test_lifecycle_infrastructure.py](file:///d:/AI/memoryops-ai/tests/test_lifecycle_infrastructure.py) to scale scheduler check intervals and wait times dynamically based on `DATABASE_TYPE`.

---

## 11. Failure Handling & Graceful Degradation

*   **Embedding Outages:** If the embedding model fails, the system falls back to Jaccard lexical match scores, preserving retrieval capabilities.
*   **Transaction Failures:** Mismatches in database commits roll back the connection to SQL `SAVEPOINT` positions.
*   **Database Outages:** When PostgreSQL is offline, requests return `503 Service Unavailable` with `STORAGE_UNAVAILABLE` error codes.

---

## 12. Developer Experience & Quickstart

### 1. Installation
```bash
git clone https://github.com/jacobjerryarackal/memoryops-ai.git
cd memoryops-ai
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
```
Update active variables. Set `DATABASE_TYPE=memory` for local development.

### 3. Run Database
```bash
docker compose up -d
```

### 4. Run Application
```bash
uvicorn services.api.app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 5. Run Verification Suite
```bash
pytest -q
```

---

## 13. Project Structure

```text
memoryops-ai/
├── Dockerfile                   # Multi-stage container build
├── docker-compose.yml           # Database configuration
├── requirements.txt             # Core dependencies
├── services/
│   └── api/
│       └── app/
│           ├── main.py          # FastAPI startup and setup
│           ├── config.py        # Settings loader
│           ├── runtime.py       # Dependency injection container
│           ├── domain/          # Model structures
│           ├── policy/          # Writes filter logic
│           ├── repositories/    # Database repository adapters
│           ├── routes/          # FastAPI routers
│           └── services/        # Business pipeline logic
├── sdk/                         # Client Python SDK
├── frontend/                    # Next.js Dashboard UI web application
├── evals/                       # Quality evaluation suite
└── tests/                       # Complete verification test suite
```

---

## 14. Testing Suite

The testing suite contains **283 tests** (282 passed, 1 skipped) verifying repository behaviors, RLS policies, security isolation, and SDK clients.

Run the test suite:
```bash
# In-Memory
DATABASE_TYPE=memory pytest -q

# PostgreSQL
DATABASE_TYPE=postgres pytest -q
```

---

## 15. Design Decisions (ADRs)

Key architectural decisions are documented in `infra/adr/`:

*   **ADR-001: Storage Selection** — Selects PostgreSQL with `pgvector` as the system of record.
*   **ADR-002: Hybrid Retrieval and Deterministic Ranking** — Blends vector similarity and lexical matching using deterministic ranking formulas.
*   **ADR-003: Policy Broker before Storage** — Restricts writes until they pass Policy Broker safety filters.
*   **ADR-005: Deletion Guarantee** — Ensures soft deletion is terminal and followed by background vector compaction.

---

## 16. Limitations

*   **Mock Inference Default:** Local testing uses lexical mocks. Validating LLM behavior requires live OpenAI/Gemini API keys.
*   **Optimistic Concurrency Constraints:** High-contention slots can trigger transaction retry loops.
*   **Lexical Matching Scope:** Jaccard calculations split raw characters, lacking stemming or complex stopword filtering.

---

## 17. Roadmap

*   **Phase 1 (Completed):** Governed write path, Policy Broker, and transaction block management.
*   **Phase 2 (Completed):** Retrieval spine, Jaccard lexical math, and deterministic ranking.
*   **Phase 3 (Completed):** PostgreSQL + pgvector persistence, migration framework, and RLS.
*   **Phase 4 (Completed):** Background workers (Retention, Decay, Reflection, Compaction).
*   **Phase 5 (Completed):** Model-agnostic embedding factory.
*   **Phase 6 (Future):** Tamper-evident audit trail hashing.
