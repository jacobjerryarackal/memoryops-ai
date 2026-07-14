# ADR-005 — Deletion Guarantee

## Status

Accepted

## Context

When a user requests that a memory be forgotten, the memory must no longer influence future AI behavior.

At the same time, MemoryOps AI requires governance evidence proving that a deletion occurred.

Immediate physical deletion removes memory content but also reduces recoverability and forensic visibility.

Retaining deleted memory without strict retrieval controls creates the risk that forgotten information may re-enter the read path.

The system therefore requires a deletion model that guarantees retrieval exclusion while preserving deletion evidence.

## Decision

Use soft deletion as the default memory deletion mechanism.

A delete operation will:

- set `status = 'deleted'`
- set `deleted_at` to the deletion timestamp
- emit a `memory_deleted` audit event

All default repository read operations must return only active memories. Conceptually, repository access is separated into two categories:

1. **Retrieval methods** (e.g., `search_candidates`, `semantic_search`, `lexical_search`):
   These always enforce:
   - `tenant_id`
   - `user_id`
   - `status = 'active'`

   Deleted, pending, rejected, and archived memories must remain structurally excluded from all application context retrieval paths.

2. **Governance methods** (e.g., `list_by_status`, `list_pending`, `get_for_governance`):
   These may explicitly inspect non-active lifecycle states (such as pending or archived) but must still strictly enforce `tenant_id` and `user_id` scope isolation. Deleted memories remain excluded from default listing.

Deletion operations must be idempotent.

Physical content erasure is treated as a separate governed lifecycle operation.

## Alternatives Considered

### Immediate Hard Delete

The memory row could be permanently deleted when a deletion request is received.

Rejected because immediate hard deletion removes recoverability and complicates governance evidence and forensic investigation.

### Application-Level Filtering

Deleted memories could remain in storage while each application service filters them independently.

Rejected because a new retrieval path may accidentally omit the deletion filter.

Deletion exclusion is a system invariant and must be enforced centrally.

## Trade-offs

Soft deletion preserves memory content until a later retention or erasure process executes.

This means soft deletion guarantees logical forgetting but does not guarantee immediate physical byte erasure.

The system accepts this limitation during the initial lifecycle architecture.

The distinction between logical deletion and physical erasure must remain explicit in documentation.

## Consequences

Deleted memories are excluded from all default read and retrieval paths.

The repository becomes responsible for enforcing the active-memory invariant.

Every deletion must produce an audit event.

Repeated deletion requests must preserve the deleted state without corrupting the lifecycle.

Tests must verify that deleted memories cannot appear in retrieval, listing, candidate search, or context assembly.

## Invariants

1. A deleted memory must never influence a future response.
2. Deleted memories must never enter the ranking pipeline.
3. Deleted memories must never enter context composition.
4. The active-status filter is enforced at the repository boundary for all application retrieval paths.
5. Every deletion must produce governance evidence.
6. Deletion must be idempotent.
7. Logical deletion and physical erasure must remain explicitly distinguished.

## Exit Strategy

Introduce a governed retention and erasure process for deleted memories.

The future lifecycle process may clear memory content and vector material after a configured retention period while preserving a content-free governance tombstone and audit history.

Physical deletion and cryptographic erasure guarantees must be documented separately and must not be implied by soft deletion.