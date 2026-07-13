# Rollout — MemoryOps AI

Phased delivery plan for MemoryOps AI.

Status reflects the current state of this repository.

| Phase | Scope | Status |
|---|---|---|
| 0 | Design spine: product definition, architecture, security, governance, ADRs, schema, API contracts | In Progress |
| 1 | Core write path: gateway → extractor → policy broker → write service → repository → audit | Planned |
| 2 | Read path: retriever → ranker → context composer → memory-used response | Planned |
| 3 | Governance control plane: approve, reject, edit, archive, delete, audit | Planned |
| 4 | Production depth: pgvector, tenant isolation, evaluations, observability | Planned |
| 5 | Background intelligence: decay, archive, deletion verification, conflict detection, reflection | Planned |
| 6 | Deletion compaction and vector purge verification | Planned |
| 7 | Worker runtime and scheduled lifecycle orchestration | Planned |
| 8 | Public results dashboard and evidence explorer | Planned |
| 9 | Retention, legal hold, and consent-aware memory | Planned |
| 10 | SDK and integration examples | Planned |
| 11 | Interactive playground and hosted demo | Planned |
| 12 | Production hardening and stable governed runtime | Planned |

---

# Phase 0 — Design Spine

## Goal

Define the system before implementation begins.

The design spine establishes the product boundary, architecture, governance model, security invariants, and initial technical contracts.

## Deliverables

- `README.md`
- `docs/design/product-blueprint.md`
- `docs/architecture/system-overview.md`
- `docs/security.md`
- `docs/governance.md`
- `docs/rollout.md`
- `docs/demo-script.md`
- `infra/adr/ADR-001-storage.md`
- `infra/adr/ADR-002-retrieval.md`
- `infra/adr/ADR-003-policy-broker.md`
- `infra/adr/ADR-004-observability.md`
- `infra/adr/ADR-005-deletion-guarantee.md`
- initial database migration
- initial API contracts

## Done When

A reviewer can understand:

- what MemoryOps AI is
- what the system owns
- how memory enters the system
- who authorizes persistence
- how memory is retrieved
- how deletion is enforced
- how lifecycle actions are audited

without running the application.

---

# Phase 1 — Core Write Path

## Goal

Build the governed memory capture path.

## Flow

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
    Audit Service

## Scope

- request gateway
- trace identifier generation
- explicit memory capture
- candidate extraction
- typed memory classification
- importance scoring
- confidence scoring
- sensitivity classification
- deterministic secret detection
- utility evaluation
- policy decisions
- memory persistence
- provenance
- audit events

## Required Policy Decisions

- `SAVE`
- `PENDING_APPROVAL`
- `BLOCK`
- `DROP_LOW_UTILITY`
- `UPDATE_EXISTING`
- `MERGE_WITH_EXISTING`

## Done When

The system can correctly process:

> Remember that I prefer Python for AI backend systems.

and persist an eligible memory.

The system must also correctly process secret-like input and block it before memory persistence.

---

# Phase 2 — Read Path

## Goal

Retrieve useful memory without violating governance boundaries.

## Flow

    Query
      ↓
    Scope Filtering
      ↓
    Hybrid Retriever
      ↓
    Deterministic Ranker
      ↓
    Context Composer
      ↓
    Memory-Used Response

## Scope

- tenant and user filtering
- active-only retrieval
- semantic retrieval
- lexical retrieval
- hybrid candidate generation
- deterministic ranking
- ranking score breakdown
- context composition
- source memory lineage
- `used_memories`
- graceful retrieval degradation

## Ranking Signals

The initial ranker considers:

- semantic similarity
- lexical similarity
- importance
- recency
- confidence
- reinforcement

## Done When

Future requests use relevant active memory.

Pending, rejected, archived, and deleted memories must never enter normal context composition.

Every memory used in context must remain traceable to its source memory identifier.

---

# Phase 3 — Governance Control Plane

## Goal

Provide a browser-based control plane for governed memory.

## Scope

- memory listing
- memory detail
- provenance inspection
- policy decision inspection
- pending approval queue
- approve
- reject
- edit
- archive
- restore
- soft delete
- per-memory audit timeline
- governance metrics

## Product Boundary

The governance interface is an operational control plane.

It is not the interactive AI playground.

All governance mutations must use governed backend APIs.

The frontend must never modify memory storage directly.

## Done When

An authorized operator can inspect a memory from creation through its current lifecycle state and perform supported governance actions.

Every mutation must produce audit evidence.

---

# Phase 4 — Production Depth

## Goal

Strengthen storage, isolation, evaluation, and operational visibility.

## Scope

- PostgreSQL production repository
- pgvector-backed semantic retrieval
- vector indexing
- database migrations
- tenant isolation hardening
- Row-Level Security readiness
- structured operational logging
- evaluation datasets
- golden retrieval cases
- adversarial cases
- evaluation runner
- baseline metrics

## Evaluation Areas

- retrieval relevance
- tenant isolation
- secret blocking
- pending-memory exclusion
- deleted-memory exclusion
- policy correctness
- retrieval latency

## Done When

Critical memory invariants are validated by automated tests and evaluation cases.

The production storage path supports governed hybrid retrieval.

---

# Phase 5 — Background Intelligence

## Goal

Move lifecycle maintenance away from the synchronous chat path.

## Scope

- memory decay
- archive proposals
- deletion verification
- conflict detection
- reflection proposals
- lifecycle runner

## Worker Principles

Every lifecycle job must be:

- tenant scoped
- idempotent
- retry safe
- auditable

Background workers must never silently bypass the Policy Broker.

Reflection and conflict resolution begin as proposal-only capabilities.

They must not automatically overwrite or persist memory without governed authorization.

## Done When

Memory lifecycle maintenance can execute independently from interactive requests without resurrecting deleted memory or bypassing governance.

---

# Phase 6 — Deletion Compaction and Vector Purge

## Goal

Extend logical deletion into governed content and vector compaction.

## Scope

- deleted-memory retention window
- compaction candidate discovery
- content clearing
- vector material clearing
- governance tombstone preservation
- purge verification
- fail-closed verification behavior

## Honest Guarantee

This phase targets auditable content and vector compaction.

It does not claim cryptographic erasure or guaranteed physical disk reclamation.

## Done When

Eligible soft-deleted memory can be compacted while preserving content-free governance evidence.

Verification must confirm that compacted memory cannot re-enter governed retrieval paths.

---

# Phase 7 — Worker Runtime

## Goal

Make lifecycle workers operationally reliable.

## Scope

- worker orchestration
- scheduled execution
- tenant-scoped job execution
- lease and lock handling
- retry policy
- exponential backoff
- dead-letter handling
- persisted run history
- worker health endpoint

## Done When

Lifecycle jobs can run on a schedule without duplicate concurrent execution.

Transient failures are retried safely.

Exhausted jobs remain inspectable.

---

# Phase 8 — Results Dashboard and Evidence Explorer

## Goal

Make MemoryOps AI understandable through inspectable evidence.

## Scope

- system overview
- version timeline
- memory lifecycle visualization
- deletion proof
- worker runtime results
- audit evidence
- evaluation results
- documented limitations

## Product Boundary

The results dashboard is read-only.

It is not the governance control plane.

It must not expose secrets or provide direct memory mutation capabilities.

## Done When

A reviewer can inspect the system's architecture, guarantees, evaluation evidence, and limitations without modifying governed memory.

---

# Phase 9 — Retention, Legal Hold, and Consent

## Goal

Introduce policy-driven lifecycle governance.

## Scope

- named retention policy packs
- sensitivity-based retention windows
- retention decision preview
- retention worker
- legal hold
- consent state
- consent expiry
- consent withdrawal
- audit evidence

## Governance Rules

Legal hold must fail closed.

When a memory is under legal hold, governed forgetting operations must not remove it.

Consent withdrawal or expiry may make memory eligible for the normal deletion lifecycle.

## Done When

Retention, preservation, and consent state influence lifecycle decisions through explicit and auditable policy.

---

# Phase 10 — SDK and Integrations

## Goal

Allow external AI applications to adopt MemoryOps AI without reimplementing governance.

## Scope

- typed Python SDK
- tenant and user scope injection
- chat operations
- memory operations
- governance operations
- audit access
- health operations
- typed errors
- integration examples

## Example Integrations

- quickstart assistant
- FastAPI application
- RAG assistant
- agent memory integration

## Governance Boundary

The server remains authoritative.

The SDK must not duplicate or override Policy Broker decisions.

## Done When

An external Python application can integrate with the governed MemoryOps API through a typed client.

---

# Phase 11 — Interactive Playground

## Goal

Provide an interactive demonstration of the governed memory pipeline.

## Scope

- conversational interface
- memory-used visibility
- candidate memory visibility
- policy decision visibility
- temporary memory mode
- hosted demonstration

## Product Boundary

The playground is not the governance dashboard.

The playground demonstrates the governed pipeline.

Governance actions remain within the governance control plane.

## Done When

A reviewer can interact with MemoryOps AI and observe how memory is proposed, governed, stored, retrieved, and used.

---

# Phase 12 — Stable Governed Runtime

## Goal

Prepare MemoryOps AI for a stable production-oriented release.

## Scope

- stable API contracts
- production deployment
- security review
- evaluation baselines
- performance benchmarks
- release automation
- deployment documentation
- operational runbooks
- architecture documentation
- public demo
- known limitations

## Done When

The governed memory runtime can be deployed, operated, evaluated, and integrated through documented interfaces.

The repository must clearly distinguish implemented guarantees from future or unsupported guarantees.

---

# Phase Gate Rules

A phase is not complete because code exists.

A phase is complete only when:

- the scoped capability is implemented
- required tests pass
- security invariants remain valid
- governance boundaries remain intact
- audit evidence exists where required
- documentation reflects the implementation
- architectural changes are recorded through ADRs
- limitations are explicitly documented

---

# Rollout Principle

MemoryOps AI evolves one governed capability at a time.

Each phase should solve the next architectural limitation exposed by the previous phase.

The system must not add complexity merely to appear production-grade.

Architecture, implementation, evidence, and documentation must evolve together.