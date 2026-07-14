# ADR-006 — Memory Identity and Write-Path Mutation Semantics

## Status

Proposed

## Context

Extracted memory candidates are represented as unstructured natural language content. If the system treats every candidate as a net-new fact, it will accumulate duplicate or conflicting active memories under the same user scope. To prevent this, the Policy Broker must have an authoritative mechanism to identify whether a CandidateMemory refers to an existing subject, property, or event, enabling state mutations like `UPDATE_EXISTING` or `MERGE_WITH_EXISTING` before persistence.

Without a formal identity model, the write path cannot safely execute updates. Overwriting the wrong memory (false update) destroys user history, while combining unrelated events (false merge) pollutes context. 

The system requires an identity representation that separates a memory's category coordinate (identity) from its natural language payload (value), enforcing strict scope isolation and deterministic mutation boundaries during the Phase 1 write path.

## Decision

Introduce a scope-relative **Identity Slot** model to govern write-path mutations.

### 1. Identity Slot Representation
Each memory's identity coordinate is defined by the following composite key:
*   `tenant_id` (enforced tenant isolation partition)
*   `user_id` (enforced user scope partition)
*   `memory_type` (acts as the identity namespace: `SEMANTIC`, `PROCEDURAL`, `EPISODIC`)
*   `identity_slot` (TEXT, application-defined, normalized property coordinate)

By utilizing `memory_type` as the namespace, we reject introducing a redundant `identity_namespace` column, preventing state drift.
The `identity_slot` is a normalized, user-scoped coordinate (e.g. `profession`, `residence`, `technology_stack`, `explanation_style`, `formatting_hashtags`). Arbitrary third-party entity modeling and general knowledge-graph representation are explicitly non-goals.

### 2. Slot Registry Authority
The Policy Broker maintains a central **Slot Registry** mapping known `(memory_type, identity_slot)` pairs to their cardinality:
*   `single-valued` slots (e.g., `profession`, `explanation_style`): Hold at most one active record. Matches trigger `UPDATE_EXISTING`.
*   `multi-valued` slots (e.g., `technology_stack`, `project_built`): Can hold multiple active records. Matches trigger `SAVE`.

The Extractor proposes the `memory_type` and `identity_slot` in the CandidateMemory payload, but has no authority over cardinality. The Policy Broker validates the slot and resolves cardinality from the registry. Cardinality is not stored on memory records, as it is authoritatively derived from the Slot Registry configuration.

If a proposed slot is not registered in the Slot Registry, it represents an unknown slot. Because no authoritative cardinality semantics are available for that slot, the Policy Broker lacks the authority to authorize mutations (such as update or merge), resulting in a conservative fallback to `SAVE` (admitting a new memory). Unknown slots are thus ineligible for mutations in the Phase 1 MVP.

#### PENDING Slot Occupancy and Approval-Time Revalidation
PENDING records do not reserve active identity slots. The existing write-path occupancy query `get_active_by_slot` matches only `status == ACTIVE`. Therefore, a PENDING record is a governance proposal, not an active slot occupant, and multiple PENDING proposals may exist for the same registered SINGLE slot.

Direct status flipping from PENDING to ACTIVE is not an approved governed transition. A future governed approval path must not activate a PENDING record without revalidation. Before a PENDING record can become active, the approval coordinator must revalidate:
*   The record's `memory_type` and `identity_slot`
*   Slot Registry membership and cardinality
*   Current `ACTIVE` occupancy for the scoped slot

If the slot is registered as `SINGLE` and is already occupied by an active record (which may have been written after the pending proposal was created), approval-time occupancy must be re-evaluated against the current state. Detailed approval execution semantics are owned by future HITL design/application coordination.

### 3. Exact Deterministic Matching Algebra
Two memory records occupy the same identity slot if and only if:
*   `tenant_id` matches exactly
*   `user_id` matches exactly
*   `memory_type` matches exactly
*   `identity_slot` matches exactly (case-sensitive string equality)

Deterministic slot lookups do not use vector similarity, cosine thresholds, or substring matching.

### 4. Deterministic Policy Broker Precedence
During candidate evaluation, rules execute in the following priority order:
1.  **Secret Detection:** Check patterns. If matched $\rightarrow$ `BLOCK` (redacted reason).
2.  **Sensitivity Gate:** If `sensitivity == HIGH` $\rightarrow$ `PENDING_APPROVAL` (requires review).
3.  **Slot Registry Check:** Validate proposed `(memory_type, identity_slot)` against the Slot Registry.
4.  **Unknown Slot:** If slot is not registered $\rightarrow$ Conservatively fall back to `SAVE` (mutation-ineligible due to unavailable cardinality semantics).
5.  **Known Multi-Valued Slot:** If slot is registered as `multi` $\rightarrow$ `SAVE` (additive fact).
6.  **Known Single-Valued Slot:** If slot is registered as `single`, execute a scoped query to locate active records occupying the slot.
7.  **Single Slot Lookup Result:**
    *   `0` active records found $\rightarrow$ `SAVE` (slot is vacant).
    *   `1` active record found $\rightarrow$ `UPDATE_EXISTING` (with `target_memory_id`).
    *   `> 1` active records found $\rightarrow$ `PENDING_APPROVAL` (violates single-valued slot invariant).

### 5. UPDATE_EXISTING Mutation Semantics
An `UPDATE_EXISTING` decision is an executable mutation targeting exactly one active record.
The candidate's content and metadata replace the target's fields.
*   **Mutable Fields:** `content`, `confidence`, `importance`, `sensitivity`, `source_kind`, `source_conversation_id`, `source_excerpt`.
*   **Derived-State Invalidation:** `embedding = None` when content is replaced.
*   **Immutable Fields:** `id`, `tenant_id`, `user_id`, `memory_type`, `identity_slot`, `initial_policy_decision`, `initial_policy_reason`, `created_at`.
*   **Provenance Integrity:** The target's genesis admission provenance (`initial_policy_decision`, `initial_policy_reason`) is immutable and remains unaltered. The mutation event is recorded separately in the audit log, and `updated_at` is refreshed.

#### Embedding Derived-State Invalidation Invariant
Embedding is derived state from memory content. Any content replacement invalidates the existing embedding. UPDATE_EXISTING must clear the target embedding atomically with content replacement. Regeneration is owned by a later embedding/indexing pipeline. Record mutation atomicity (content replacement + embedding invalidation) must occur in the same MemoryRecord update operation.

### 6. MERGE_WITH_EXISTING MVP Deferral
`MERGE_WITH_EXISTING` is retained in the `PolicyDecision` enum contract but is **deferred from the Phase 1 MVP**. Because natural language merging requires synthesis, deterministic code cannot execute merges without model-assisted generation. Candidate facts that would trigger a merge fall back to `SAVE` (coexisting as separate active records) to prevent data corruption.

### 7. Conservative Ambiguity Behavior
When memory identity is ambiguous (unregistered slots, unverified episodic event identity, or complementary facts without merge rules), the system falls back to `SAVE`. Although this accepts duplication or conflicting records (RAG prompt noise), it mitigates the severe risk of false updates (data loss) and false merges (context pollution).

### 8. Repository Lookup Shape
The repository interface will define a bounded lookup method:
`get_active_by_slot(tenant_id, user_id, memory_type, identity_slot) -> List[MemoryRecord]`
To prevent unbounded scans, the result is capped to a maximum limit of `2` records, which is sufficient for the Policy Broker to evaluate vacant, valid single, or invalid duplicate states.

### 9. Database Representation
Add a single column to the database schema:
*   `identity_slot` (TEXT, nullable, default NULL, immutable after admission).
It is nullable to support legacy or unclassified memories.
*   **Index:** A composite partial index `idx_memories_identity_active` on `(tenant_id, user_id, memory_type, identity_slot) WHERE status = 'active'` will optimize slot-lookups.

### 10. PolicyResult Executability
The existing fields (`decision`, `reason`, `target_memory_id`) are sufficient to execute `UPDATE_EXISTING` since the candidate payload carries all new mutable values.

## Alternatives Considered

*   **Exact Normalized-Content Matching as Memory Identity:** Rejected because it fails to capture fact evolution, preference updates, or paraphrases.
*   **Free-Form Canonical Keys as Authoritative Identity:** Rejected because LLMs produce inconsistent keys over time (e.g., `explanation_style` vs `verbosity`), causing slot duplication.
*   **Identity Keys or Multiple-Key Overlap Matching:** Rejected because multi-key overlap matching introduces complex set-matching rules that are non-deterministic and difficult to validate.
*   **Extractor-Owned Cardinality:** Rejected because the Extractor has no policy authority; allowing it to dictate cardinality violates the rule that Policy governs state.
*   **Embedding Similarity or Similarity Thresholds as Mutation Authority:** Rejected because semantic similarity cannot distinguish between evolution (which requires an update) and complementary additions (which require a save).
*   **LLM Disposition Classification for Phase 1 MVP:** Deferred because LLM classification introduces high latency, cost, and non-deterministic logic on the critical write path.
*   **Write Service Semantic Merge or String-Concatenation Merge:** Rejected because the Write Service has no semantic understanding; string concatenation yields malformed natural language content.
*   **Repository-Owned SAVE / UPDATE / MERGE Disposition Logic:** Rejected because the repository must remain a simple state persistence layer. Moving policy decisions to the repository violates the system boundary.
*   **General Knowledge-Graph Subject/Predicate Identity Modeling for Phase 1 MVP:** Deferred because graph-based triple representation introduces high schema complexity that is unnecessary for the user-scoped memory slots of the initial MVP.

## Trade-offs

*   **Registry Maintenance:** Bounding slots inside a Slot Registry requires application-level updates to register new capabilities. This is accepted to ensure policy control.
*   **Redundancy Risk:** Fallbacks to `SAVE` allow duplicate/conflicting records. This is accepted as the safest failure direction during Phase 1.

## Invariants

1.  Scope isolation must be enforced on every slot lookup and update.
2.  Persisted records in a single-valued slot must never exceed one active record.
3.  Initial admission provenance fields are immutable and must not be updated during mutation.
4.  Updates to already logically deleted records must be rejected.
5.  State transitions to `deleted` must occur only via `delete()`.
6.  Embedding is derived state from memory content; target content mutation must clear the target embedding atomically.
7.  PENDING records do not reserve active slot occupancy.
8.  Transitioning from PENDING to ACTIVE requires revalidation of Slot Registry cardinality and current ACTIVE occupancy.

## Exit Strategy

Introduce a model-assisted merge processor in a later phase. When the Policy Broker detects a complementary match, it can invoke an LLM synthesis turn to construct the merged state, appending the result as the new target value while preserving provenance.
