# Governance — MemoryOps AI

## Purpose

MemoryOps AI treats memory as governed persistent state.

Governance defines how memory may be captured, stored, retrieved, updated, approved, rejected, archived, and forgotten.

The governance model answers three questions:

1. Who may act on memory?
2. Which memory state transitions are allowed?
3. How is every important decision proven?

Governance applies across the complete memory lifecycle.

---

# Governed Memory Lifecycle

Memory begins as a candidate proposed by the extraction system.

The Extractor does not have authority to persist memory.

A candidate must pass through the Policy Broker before entering the governed memory lifecycle.

    Incoming Information
            ↓
        Extractor
            ↓
    Candidate Memory
            ↓
      Policy Broker
            ↓
         Decision
            │
    ┌───────┼──────────────────────────────────────┐
    │       │          │          │                │
   SAVE   PENDING     BLOCK      DROP          UPDATE / MERGE
    │       │          │          │                │
 active   pending   audit only  audit only     existing active
            │
       ┌────┴────┐
       │         │
    approve    reject
       │         │
     active    rejected

An active memory may later become:

    active
       │
       ├── updated
       │
       ├── merged
       │
       ├── archived
       │
       └── deleted

Deleted memories must never return to the active retrieval path.

---

# Policy Decision Semantics

The Policy Broker may produce the following decisions.

| Decision | Stored | Retrievable | Meaning |
|---|---|---|---|
| `SAVE` | Yes | Yes | Candidate becomes active memory |
| `PENDING_APPROVAL` | Yes | No | Candidate requires human review |
| `BLOCK` | No | No | Candidate violates a hard policy |
| `DROP_LOW_UTILITY` | No | No | Candidate does not justify persistence |
| `UPDATE_EXISTING` | Yes | Yes | Existing memory is updated |
| `MERGE_WITH_EXISTING` | Yes | Yes | Candidate is merged with related memory |

Every policy decision must include a human-readable reason.

The policy decision must remain auditable.

---

# Memory Lifecycle States

The initial lifecycle states are:

- `active`
- `pending`
- `rejected`
- `archived`
- `deleted`

## Active

The memory is eligible for retrieval.

Only active memories may enter the default retrieval pipeline.

## Pending

The memory exists for governance review but is not retrievable.

A pending memory may transition to:

- `active`
- `rejected`

## Rejected

The candidate was reviewed and denied.

Rejected memory must not enter retrieval.

## Archived

The memory is retained but excluded from normal active retrieval.

Archival is distinct from deletion.

Future lifecycle policies may archive memory because of age, decay, or operational policy.

## Deleted

The memory has been logically forgotten.

Deleted memory must remain structurally excluded from all application context retrieval paths. Active-only filtering is mandatory for all application retrieval methods and default listing paths.

To enforce this, database and repository access is conceptually divided into two categories:

*   **Retrieval Methods** (e.g., `search_candidates`, `semantic_search`, `lexical_search`):
    These always enforce:
    ```text
    tenant_id
    user_id
    status = active
    ```
    Non-active memories (deleted, pending, rejected, archived) can never be fetched by retrieval methods.
*   **Governance Methods** (e.g., `list_by_status`, `list_pending`, `get_for_governance`):
    These may explicitly inspect non-active lifecycle states within tenant and user scope to enable administrative and moderation actions.

Physical erasure is governed separately from logical deletion.

---

# Governance Roles

The initial governance model defines four conceptual roles.

## User

A user may govern memory within their own scope.

Target capabilities include:

- view memory
- approve pending memory
- reject pending memory
- edit memory
- archive memory
- delete memory
- manage memory settings

## Approver

An Approver may review pending memories within an authorized tenant scope.

Target capabilities include:

- inspect pending memory
- review policy rationale
- approve memory
- reject memory

## Admin

An Admin manages tenant-level memory governance.

Target capabilities include:

- inspect governance metrics
- manage memory policy settings
- oversee lifecycle operations
- inspect policy outcomes

Administrative access must not imply unrestricted covert access to raw memory content.

## Auditor

An Auditor has read-only access to governance evidence.

Target capabilities include:

- inspect audit events
- trace memory lifecycle actions
- inspect policy decisions
- verify deletion events

Auditors must not mutate memory state.

---

# Human-in-the-Loop Governance

Human review is required when automated policy cannot safely authorize persistence.

The initial human review workflow is:

    Candidate Memory
            ↓
    PENDING_APPROVAL
            ↓
       Review Queue
         ↙     ↘
    APPROVE    REJECT
       ↓          ↓
     active     rejected

Approval changes the memory lifecycle state to `active`.

Rejection changes the memory lifecycle state to `rejected`.

Every approval or rejection must produce an audit event.

The governance interface must use governed backend operations.

A frontend must never modify memory state directly in storage.

---

# Governance Actions

The initial governance surface includes:

- view
- approve
- reject
- edit
- archive
- delete

Each governance action maps to a controlled lifecycle operation.

## View

Allows an authorized actor to inspect memory within their scope.

## Approve

Transitions:

    pending → active

## Reject

Transitions:

    pending → rejected

## Edit

Updates an existing memory.

The change must remain auditable.

## Archive

Transitions:

    active → archived

Archived memory is excluded from normal retrieval.

## Delete

Transitions eligible memory into the deleted lifecycle state.

Deletion must follow the deletion guarantee defined in ADR-005.

---

# Audit Events and Operational Telemetry

MemoryOps AI separates persistent governance evidence (audit logs) from execution logging (operational telemetry).

## Governance Audit Events

Governance audit events record memory lifecycle changes. These records are **append-only**, and the application API exposes no endpoints to update or delete audit history.

Initial lifecycle audit events include:

*   `memory_created` — Candidate memory passed automated policy and was saved as active.
*   `memory_pending_approval` — Candidate memory requires review and was saved as pending.
*   `memory_blocked` — Candidate memory failed deterministic rules and was blocked.
*   `memory_dropped` — Candidate memory utility score did not justify storage.
*   `memory_updated` — Stored memory content or attributes were updated.
*   `memory_merged` — Candidate memory was merged into an existing active memory.
*   `memory_approved` — Pending memory was approved by an operator and became active.
*   `memory_rejected` — Pending memory was rejected by an operator.
*   `memory_archived` — Active memory was archived.
*   `memory_deleted` — Active, pending, or archived memory was logically deleted.

An audit event should contain:

*   `id` (unique audit identifier)
*   `tenant_id`
*   `user_id`
*   `memory_id` (null for blocked/dropped candidates)
*   `action` (one of the event names above)
*   `reason` (human-readable explanation)
*   `metadata`
*   `trace_id`
*   `created_at`

## Operational Telemetry Events

Operational telemetry records system performance, reads, and bypasses. These events are processed as structured execution logs and are not part of the append-only governance audit log database:

*   `memory_retrieved` — Active memories retrieved during a read request.
*   `retrieval_failed` — Retrieval path failed, triggering fallback or degradation.
*   `temporary_chat_skipped` — Request used temporary mode, bypassing reads and writes.

Operational logs must use trace identifiers for end-to-end request tracking.

---

# Explainability

Every memory-influenced response should eventually expose which memories contributed to the generated context.

The read path should preserve:

- source memory identifier
- memory type
- source
- ranking reason
- ranking score breakdown

A response may expose:

    used_memories

This allows an authorized reviewer to answer:

- Which memories influenced this response?
- Why were those memories retrieved?
- Which ranking signals caused them to surface?

Candidate memory decisions should also remain inspectable.

The system should preserve:

    candidate_memories

with the Policy Broker decision and reason.

Explainability metadata must not bypass memory scope or sensitivity controls.

---

# Governance Authority

The Policy Broker is the authoritative decision point for candidate persistence.

The Write Service may execute an approved decision.

The Repository may enforce storage invariants.

The Retrieval Pipeline may retrieve only eligible memory.

The Governance Interface may request lifecycle transitions through backend APIs.

No component may silently bypass these boundaries.

The authority chain is:

    Extractor
        ↓ proposes
    Policy Broker
        ↓ authorizes
    Write Service
        ↓ executes
    Repository
        ↓ enforces persistence invariants
    Audit Service
        ↓ records evidence

---

# Temporary Memory Bypass

Applications may support interactions that explicitly bypass persistent memory.

When temporary mode is enabled:

- persistent memory must not be retrieved
- candidate memories must not be persisted
- the bypass should produce an operational or audit event where appropriate

Temporary mode must bypass both the read path and write path.

---

# Governance Invariants

1. The Extractor may propose memory but cannot authorize persistence.
2. The Policy Broker is authoritative for candidate memory decisions.
3. Pending memories must never be retrieved.
4. Rejected memories must never be retrieved.
5. Deleted memories must never influence future AI context.
6. Governance mutations must produce audit evidence.
7. Audit history must remain append-only.
8. Frontend applications must not write directly to memory storage.
9. Governance operations must respect tenant and user scope.
10. Explainability must preserve memory lineage without bypassing access controls.

---

# Future Governance Evolution

The governance model may later introduce:

- role-based access control
- consent-aware memory
- retention policies
- legal hold
- protected memory
- pinned memory
- background lifecycle governance
- provenance scoring
- deletion verification
- physical deletion compaction
- tamper-evident audit evidence

These capabilities must extend the existing governance authority chain rather than bypass it.

---

# Governance Principle

The system may automate memory operations.

It must never make memory governance invisible.

Every important memory decision should have an authority, a reason, a state transition, and evidence.