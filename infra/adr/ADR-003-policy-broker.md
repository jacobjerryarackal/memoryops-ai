# ADR-003 — Policy Broker Before Storage

## Status

Accepted

## Context

Memory candidates are produced by probabilistic extraction systems.

An extracted candidate must not automatically become persistent memory.

Without an explicit governance boundary, the system may persist secrets, sensitive information, duplicate facts, conflicting memories, or low-utility noise.

Memory storage therefore requires an authoritative decision before persistence.

## Decision

Introduce a Policy Broker between the Extractor and the Write Service.

The Policy Broker is the authoritative decision point for candidate memory persistence.

The broker may produce one of the following decisions:

- `SAVE`
- `PENDING_APPROVAL`
- `BLOCK`
- `DROP_LOW_UTILITY`
- `UPDATE_EXISTING`
- `MERGE_WITH_EXISTING`

Policy evaluation occurs in the following order:

1. Secret and credential detection
2. PII and sensitivity classification
3. Utility and duplication checks
4. Final scoring and disposition

Hard safety rules must be deterministic.

LLM-based reasoning may assist with nuanced judgments such as utility or semantic relationships, but an LLM must not override deterministic blocking rules.

Every policy decision must emit an auditable reason.

## Alternatives Considered

### Policy Logic Inside the Extractor

The extractor could determine both candidate memories and persistence decisions.

Rejected because extraction and governance are separate responsibilities.

Combining them couples model quality to system safety and makes independent testing difficult.

### Post-Write Moderation

Candidates could be stored first and reviewed after persistence.

Rejected because prohibited information may temporarily exist in persistent storage, replicas, backups, or retrieval indexes.

Policy must execute before storage.

### Pure LLM Judge

A second LLM could decide whether a candidate should be stored.

Rejected as the sole authority because probabilistic output cannot reliably enforce hard rules such as credential blocking.

LLM reasoning may remain advisory for nuanced decisions.

## Trade-offs

A centralized Policy Broker introduces an additional processing stage.

Deterministic detectors may produce false positives or false negatives.

These limitations will be mitigated through layered detection, human approval workflows, and evaluation suites.

The broker is also a potential processing bottleneck.

This is accepted because a single authoritative policy boundary makes memory governance observable and testable.

## Consequences

The write path becomes:

    Extractor
        ↓
    Candidate Memory
        ↓
    Policy Broker
        ↓
    Write Service
        ↓
    Repository

Secret-like content must be blocked before memory persistence.

Sensitive candidates may enter a pending approval state and must remain unavailable to retrieval until approved.

Every decision must produce an audit event containing a human-readable reason.

The Policy Broker interface must remain independent from the extraction implementation.

Content-changing governance updates (such as manual `PATCH` operations) must also run their proposed content through the Policy Broker's safety validation (specifically deterministic secret blocking) before persistence.

## Invariants

1. No candidate memory or manual content-changing update may reach persistent storage without a policy/safety decision.
2. Deterministic blocking rules cannot be overridden by an LLM.
3. Blocked secrets must never be persisted as memories.
4. Pending memories must not be retrievable.
5. Every policy decision must be auditable.
6. Extraction and policy evaluation must remain independently testable.

## Exit Strategy

Policy rules may later move into a versioned policy system or external policy engine.

Potential implementations include policy tables or dedicated policy-as-code systems.

The Policy Broker interface will remain stable so policy implementation can evolve independently.