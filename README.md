# MemoryOps AI

### Governed Memory Infrastructure for AI Applications

MemoryOps AI is a memory infrastructure layer for AI applications.

It governs what becomes memory, how memory is stored and retrieved, which memories may influence future context, how memory evolves, and what happens when information must be forgotten.

Memory is treated as governed persistent state rather than a vector search feature.

> Current stage: Phase 0 — Design Spine  
> Current version: `0.1.0`

---

## Why MemoryOps AI

A basic AI memory implementation often looks like this:

```text
User Message
     ↓
Embedding
     ↓
Vector Database
     ↓
Similarity Search
```

This answers one question:

> How do we find semantically similar information?

A production memory system must answer more:

- What deserves to become memory?
- What must never be stored?
- Who owns a memory?
- Which policy authorized persistence?
- How should conflicting memory evolve?
- Which memories are allowed into context?
- Why did a memory influence an answer?
- How does forgetting work?
- How can deletion be verified?
- How is memory quality evaluated?

MemoryOps AI introduces a governed runtime around the complete memory lifecycle.

---

## System Model

MemoryOps AI separates the memory write path, read path, and governance plane.

### Write Path

```text
Incoming Information
        ↓
      Gateway
        ↓
     Extractor
        ↓
 Candidate Memory
        ↓
   Policy Broker
        ↓
    Write Service
        ↓
     Repository
        ↓
 PostgreSQL + pgvector
```

The Extractor proposes memory.

The Policy Broker authorizes memory.

The Write Service executes the authorized decision.

The Repository enforces persistence invariants.

The Extractor never has authority to persist memory directly.

### Read Path

```text
Application Query
        ↓
   Scope Filtering
        ↓
  Hybrid Retriever
        ↓
Deterministic Ranker
        ↓
 Context Composer
        ↓
  Application Context
```

Retrieval combines semantic and lexical signals.

Candidate memories are filtered by governance boundaries before ranking.

Only eligible active memory may enter context composition.

### Governance Plane

```text
Capture
   ↓
Store
   ↓
Retrieve
   ↓
Update
   ↓
Forget

Governance wraps every stage.
```

Every important memory decision should have:

- an authority
- a reason
- a lifecycle state
- governance evidence

---

## Policy Before Storage

Memory extraction is probabilistic.

Persistent state cannot rely on extraction output alone.

Every candidate memory passes through the Policy Broker before storage.

The broker may produce:

| Decision | Meaning |
|---|---|
| `SAVE` | Persist as active memory |
| `PENDING_APPROVAL` | Require human review |
| `BLOCK` | Reject because of a hard policy |
| `DROP_LOW_UTILITY` | Do not persist low-value information |
| `UPDATE_EXISTING` | Update an existing memory |
| `MERGE_WITH_EXISTING` | Merge related memory |

Hard safety rules are deterministic.

LLM-based reasoning may assist with nuanced judgments, but it cannot override deterministic blocking rules.

```text
LLM proposes state.
Policy governs state.
```

---

## Memory Types

MemoryOps AI initially models three memory types.

### Semantic Memory

Durable facts and information.

```text
Jacob is an AI Engineer.
```

### Procedural Memory

Preferences and instructions that influence future behavior.

```text
Jacob prefers production-grade engineering explanations.
```

### Episodic Memory

Events, experiences, achievements, and time-bound information.

```text
Jacob built GIMS during a memory-system hackathon.
```

Memory type does not bypass governance.

Every memory follows the same policy, lifecycle, audit, and deletion boundaries.

---

## Memory Lifecycle

```text
Candidate
    ↓
Policy Decision
    │
    ├── SAVE ───────────────→ active
    │
    ├── PENDING_APPROVAL ───→ pending
    │                              │
    │                         ┌────┴────┐
    │                         ↓         ↓
    │                      active    rejected
    │
    ├── BLOCK ──────────────→ audit only
    │
    ├── DROP_LOW_UTILITY ───→ audit only
    │
    ├── UPDATE_EXISTING ────→ existing active memory
    │
    └── MERGE_WITH_EXISTING → existing active memory
```

Active memory may later be:

```text
active
   │
   ├── updated
   ├── merged
   ├── archived
   └── deleted
```

Only active memory is eligible for normal retrieval.

Pending, rejected, archived, and deleted memory must not enter normal context composition.

---

## Hybrid Retrieval

Vector similarity alone is insufficient for exact names, identifiers, and phrases.

Keyword retrieval alone cannot reliably identify semantic paraphrases.

MemoryOps AI therefore uses hybrid retrieval.

```text
Semantic Retrieval
        +
Lexical Retrieval
        ↓
Candidate Memories
        ↓
Governance Filtering
        ↓
Deterministic Ranking
        ↓
Top-K Memories
```

The initial ranking model is:

```text
final_score =
    0.35 × semantic
  + 0.20 × keyword
  + 0.15 × importance
  + 0.10 × recency
  + 0.10 × confidence
  + 0.10 × reinforcement
```

The ranking model is intentionally deterministic and inspectable.

Every used memory should eventually expose a score breakdown and source memory identifier.

---

## Security Invariants

The following properties are non-negotiable system invariants.

1. **Tenant isolation**  
   A tenant or user must never retrieve another scope's memory.

2. **Policy before storage**  
   No candidate memory reaches persistent storage without a Policy Broker decision.

3. **Secret exclusion**  
   Detected credentials and secrets must never become persistent memory.

4. **Deletion guarantee**  
   Deleted memory must never influence future AI context.

5. **Pending-memory exclusion**  
   Pending memory is not retrievable until approved.

6. **Temporary memory bypass**  
   Temporary interactions bypass persistent memory reads and writes.

7. **Auditability**  
   Persistent memory lifecycle mutations produce append-only governance evidence.

8. **Explainability**  
   Memory usage remains traceable to source memory identifiers.

9. **Graceful degradation**  
   Failure of optional memory retrieval must not automatically fail the host AI application.

A violation of a security invariant is treated as a correctness failure.

---

## Deletion Guarantee

A delete operation performs logical forgetting.

```text
DELETE memory
      ↓
status = deleted
deleted_at = timestamp
      ↓
memory_deleted audit event
      ↓
excluded from every governed read path
```

Deleted memory must not appear in:

- active memory listing
- semantic candidate retrieval
- lexical candidate retrieval
- ranking
- context composition

The active-memory invariant is enforced at the repository boundary.

The initial architecture guarantees logical forgetting from governed MemoryOps read paths.

It does not claim immediate physical byte erasure.

Physical content and vector compaction are separate lifecycle capabilities planned for a later phase.

---

## Audit and Observability

MemoryOps AI separates governance evidence from operational telemetry.

### Audit Stream (Append-Only Governance Evidence)

Answers:

> What happened to memory state?

Governance audit events record memory lifecycle mutations:

```text
memory_created
memory_pending_approval
memory_blocked
memory_dropped
memory_updated
memory_merged
memory_approved
memory_rejected
memory_archived
memory_deleted
```

Audit history is append-only.

### Operational Stream (Operational Telemetry)

Answers:

> How did the system behave?

Operational telemetry captures reads, performance, and bypasses:

```text
memory_retrieved
retrieval_failed
temporary_chat_skipped
```

Structured telemetry logs may contain:

```text
trace_id
tenant_id
user_id
event
latency_ms
memory_count
status
```

A trace identifier begins at the request gateway and propagates through downstream memory components.

```text
Gateway
   ↓ trace_id
Extractor
   ↓ trace_id
Policy Broker
   ↓ trace_id
Write Service
   ↓ trace_id
Repository
```

Governance evidence and operational telemetry remain logically separate.

---

## Architecture

```text
                         AI Application
                                │
                                ▼
                         MemoryOps API
                                │
              ┌─────────────────┴─────────────────┐
              │                                   │
          WRITE PATH                          READ PATH
              │                                   │
          Extractor                           Retriever
              │                                   │
       Candidate Memory                          Ranker
              │                                   │
        Policy Broker                     Context Composer
              │                                   │
        Write Service                             │
              └─────────────────┬─────────────────┘
                                │
                           Repository
                                │
                       PostgreSQL + pgvector
                                │
                 ┌──────────────┴──────────────┐
                 │                             │
            Audit Stream                Operational Logs
```

Detailed architecture is documented in `docs/architecture/system-overview.md`.

---

## Storage Architecture

PostgreSQL with pgvector is the canonical system of record for long-term memory and governance data.

Storage access occurs through a repository abstraction.

Initial repository implementations:

```text
Repository Interface
        │
        ├── postgres
        │      └── PostgreSQL + pgvector
        │
        └── memory
               └── in-process storage
```

The in-memory implementation supports local development and deterministic testing without external infrastructure.

Application services depend on the repository contract rather than a concrete storage backend.

See `infra/adr/ADR-001-storage.md`.

---

## API Surface

The initial HTTP contract defines:

```text
POST   /api/chat

GET    /api/memories
GET    /api/memories/{memory_id}
GET    /api/memories/{memory_id}/provenance
GET    /api/memories/{memory_id}/audit

PATCH  /api/memories/{memory_id}
DELETE /api/memories/{memory_id}

GET    /api/audit
GET    /api/metrics

GET    /healthz
GET    /readyz
```

The canonical initial contract is documented in `docs/api-contracts.md`.

The API contract is defined before route implementation.

Changes to endpoint methods, paths, required fields, response semantics, or lifecycle behavior must update the contract.

---

## Repository Layout

```text
memoryops-ai/
│
├── apps/
│   ├── web/                     # Governance control plane
│   └── playground/              # Interactive governed memory demo
│
├── services/
│   ├── api/                     # MemoryOps HTTP runtime
│   └── worker/                  # Background lifecycle workers
│
├── packages/
│   └── shared/                  # Shared contracts and types
│
├── infra/
│   ├── adr/                     # Architecture Decision Records
│   └── db/
│       └── migrations/          # PostgreSQL + pgvector schema
│
├── evals/                       # Golden and adversarial evaluation cases
│
├── docs/
│   ├── architecture/            # System architecture
│   ├── design/                  # Product and system blueprints
│   ├── api-contracts.md
│   ├── governance.md
│   ├── rollout.md
│   └── security.md
│
├── AGENTS.md                    # Coding-agent engineering contract
├── CLAUDE.md                    # Agent context
├── ROADMAP.md                   # Product evolution
└── README.md
```

Some implementation directories are introduced by later rollout phases.

The repository structure represents the intended system boundary, not a claim that every planned capability is already shipped.

---

## Architecture Decisions

The initial architecture is defined through five ADRs.

| ADR | Decision |
|---|---|
| ADR-001 | PostgreSQL + pgvector with repository abstraction |
| ADR-002 | Hybrid retrieval and deterministic ranking |
| ADR-003 | Policy Broker before storage |
| ADR-004 | Separate audit and operational observability streams |
| ADR-005 | Repository-enforced logical deletion guarantee |

ADRs live under:

```text
infra/adr/
```

Architecture changes should introduce or update an ADR when they alter a load-bearing system decision.

---

## Rollout

MemoryOps AI evolves through gated engineering phases.

| Phase | Capability | Status |
|---|---|---|
| 0 | Design spine | In Progress |
| 1 | Core write path | Planned |
| 2 | Read path | Planned |
| 3 | Governance control plane | Planned |
| 4 | Production depth and evaluations | Planned |
| 5 | Background lifecycle intelligence | Planned |
| 6 | Deletion compaction and vector purge | Planned |
| 7 | Worker runtime | Planned |
| 8 | Results and evidence dashboard | Planned |
| 9 | Retention, legal hold, and consent | Planned |
| 10 | SDK and integrations | Planned |
| 11 | Interactive playground | Planned |
| 12 | Stable governed runtime | Planned |

A phase is not complete because code exists.

A phase is complete when:

- scoped capability is implemented
- tests validate required invariants
- governance boundaries remain intact
- audit evidence exists where required
- documentation matches implementation
- limitations are explicit

See `docs/rollout.md`.

---

## Current Status

MemoryOps AI is currently in **Phase 0 — Design Spine**.

The current repository defines:

- product boundary
- system architecture
- storage strategy
- retrieval strategy
- policy authority
- observability model
- deletion guarantee
- security threat model
- governance model
- HTTP API contract
- initial PostgreSQL schema
- phased rollout

The governed runtime is not yet implemented.

The next phase introduces the core write path:

```text
Gateway
   ↓
Extractor
   ↓
Policy Broker
   ↓
Write Service
   ↓
Repository
   ↓
Audit Service
```

The repository will only claim capabilities that are implemented and validated.

---

## Developer & Agent Harness

To reduce prompt repetition, this repository hosts local engineering harness files that govern developer and AI agent workflows, and map production engineering concern gates:

* **Engineering Rules:** [AGENTS.md](file:///d:/AI/memoryops-ai/AGENTS.md)
* **Concern Gate Matrix & Workflows:** [docs/phase-gates/README.md](file:///d:/AI/memoryops-ai/docs/phase-gates/README.md)
* **Agentic SWE Kit Mapping:** [agentic-swe-kit-map.md](file:///d:/AI/memoryops-ai/docs/agentic-swe-kit-map.md) *(Comparative guidance only)*
* **Failure Mode Mapping:** [failure-mode-map.md](file:///d:/AI/memoryops-ai/docs/failure-mode-map.md) *(Mitigations and test evidence)*

> [!NOTE]
> External agentic engineering frameworks (e.g., agentic-swe-kit, Hermes, AI PR review automation) are referenced for comparative architectural guidance. MemoryOps AI uses a native repository-local harness for all active agent guidance and validation checks.

---

## Design Documentation


| Document | Purpose |
|---|---|
| `docs/design/product-blueprint.md` | Product boundary and system intent |
| `docs/architecture/system-overview.md` | High-level system architecture |
| `docs/security.md` | Threat model and security invariants |
| `docs/governance.md` | Memory authority and lifecycle governance |
| `docs/api-contracts.md` | Canonical HTTP contract |
| `docs/rollout.md` | Phased delivery plan |
| `infra/adr/` | Architecture decisions |
| `infra/db/migrations/` | Executable persistence schema |

The repository is designed so architecture, implementation, tests, evaluation, and documentation evolve together.

---

## Engineering Principle

> Memory that persists can influence future decisions.

Therefore, memory is not treated as passive application data.

The write path is a policy boundary.

The read path is a context admission boundary.

The deletion path is a forgetting boundary.

Every important memory decision should remain governed, observable, and explainable.

---

## License

MIT License.