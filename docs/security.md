# Security — MemoryOps AI

## Purpose

Security is a cross-cutting system property of MemoryOps AI.

Memory is persistent state that may influence future AI behavior. A failure in memory isolation, governance, or deletion can therefore affect requests long after the original information entered the system.

Security controls must exist across the memory lifecycle rather than as a single feature or service.

This document defines the initial threat model, security invariants, and hardening direction for MemoryOps AI.

---

# Threat Model

The initial architecture considers five primary memory-system failures.

## 1. Cross-Tenant or Cross-User Leakage

A memory belonging to one tenant or user must never be exposed to another tenant or user.

This includes:

- memory listing
- semantic retrieval
- lexical retrieval
- ranking
- context composition
- audit access
- lifecycle operations

Cross-tenant memory exposure is considered a critical security failure.

### Initial Controls

Every scoped repository operation must require:

- `tenant_id`
- `user_id`

Candidate retrieval must apply scope restrictions before ranking.

Application services must not perform unscoped memory reads.

### Future Hardening

Database-level Row-Level Security should provide defense in depth against application-level isolation failures.

---

## 2. Secret and Credential Capture

Probabilistic extraction systems may identify credentials or secrets as candidate memories.

Examples include:

- API keys
- access tokens
- bearer tokens
- passwords
- cloud credentials
- private authentication material

Secret-like content must not become persistent memory.

### Initial Controls

The Policy Broker executes before the Write Service.

Deterministic secret detection runs before utility or relevance scoring.

A detected secret produces a `BLOCK` decision.

Blocked content must never be persisted as a memory.

The policy decision must remain auditable without copying the secret into audit metadata.

### Future Hardening

Secret detection may evolve through layered detectors and dedicated secret-scanning integrations.

---

## 3. Deletion Failure

A memory that has been forgotten must never influence future AI behavior.

Deletion failure includes:

- deleted memory appearing in listing
- deleted memory entering semantic search
- deleted memory entering lexical search
- deleted memory entering ranking
- deleted memory entering context composition

### Initial Controls

Memory deletion uses lifecycle state:

- `status = deleted`
- `deleted_at = timestamp`

Default repository read paths expose active memories only.

The active-memory invariant is enforced at the repository boundary.

Deletion produces governance evidence through the audit stream.

### Security Boundary

Soft deletion guarantees logical forgetting from the MemoryOps read path.

It does not claim immediate physical byte erasure.

Logical deletion and physical erasure must remain explicitly distinguished.

### Future Hardening

A governed retention and compaction process should remove memory content and vector material while preserving content-free deletion evidence.

---

## 4. Silent Sensitive Storage

Sensitive information must not silently become retrievable memory without appropriate governance.

Memory sensitivity may include identity, contact, financial, or other protected information depending on deployment policy.

### Initial Controls

Candidate memories receive a sensitivity classification:

- `low`
- `medium`
- `high`

Deployments may require approval for sensitive memories.

When approval is required, the memory enters:

`status = pending`

Pending memories must remain excluded from retrieval.

### Future Hardening

The governance model may introduce:

- explicit consent
- retention policies
- legal hold
- role-based approval
- data export workflows
- regional storage controls

---

## 5. Memory Poisoning

Low-quality, adversarial, conflicting, or repeatedly injected information may pollute persistent memory.

Because memory influences future AI context, poisoned memory may create repeated downstream failures.

### Initial Controls

Candidate memories pass through the Policy Broker.

Policy evaluation may consider:

- utility
- confidence
- duplication
- conflict
- sensitivity

The broker may produce:

- `SAVE`
- `PENDING_APPROVAL`
- `BLOCK`
- `DROP_LOW_UTILITY`
- `UPDATE_EXISTING`
- `MERGE_WITH_EXISTING`

Extraction does not have authority to persist memory directly.

### Future Hardening

Memory poisoning controls may evolve through:

- anomaly detection
- provenance scoring
- source trust
- reinforcement analysis
- adversarial evaluations
- rate limits

---

# Security Invariants

The following properties are system invariants.

## Invariant 1 — Isolation

A tenant or user must never retrieve another scope's memory.

## Invariant 2 — Deletion

A deleted memory must never influence future AI context.

## Invariant 3 — Secret Exclusion

Detected credentials and secrets must never become persistent memory.

## Invariant 4 — Safe Degradation

Failure of optional memory capabilities must not automatically fail the host AI application.

## Invariant 5 — Policy Before Storage

No candidate memory may reach persistent storage without a Policy Broker decision.

## Invariant 6 — Temporary Memory Bypass

Temporary or non-memory interactions must bypass both persistent memory reads and writes when explicitly requested.

## Invariant 7 — Auditability

Persistent memory lifecycle mutations must produce governance evidence.

---

# Defense in Depth

Security must not depend on a single control.

For example, tenant isolation should eventually exist at multiple boundaries:

    API scope
        ↓
    Service scope
        ↓
    Repository filtering
        ↓
    Database Row-Level Security

Deletion safety should similarly exist across:

    Lifecycle state
        ↓
    Repository filtering
        ↓
    Candidate retrieval
        ↓
    Ranking
        ↓
    Context admission
        ↓
    Verification

A failure in one layer should not automatically expose governed memory.

---

# Audit Safety

Audit events must preserve governance evidence without unnecessarily duplicating sensitive content.

Audit metadata should prefer:

- identifiers
- decisions
- reason codes
- timestamps
- lifecycle states
- counts

Secrets must never be copied into audit metadata.

Operational traces should avoid recording raw credentials or unrestricted user content.

---

# Security Testing

Security invariants must be validated through dedicated tests.

The initial security test categories are:

- tenant isolation
- user isolation
- secret blocking
- pending-memory retrieval exclusion
- deleted-memory retrieval exclusion
- policy-before-storage enforcement
- audit event creation
- temporary memory bypass

A violation of a security invariant is considered a correctness failure, not an optional security improvement.

---

# Production Hardening Roadmap

Future production security work may include:

- PostgreSQL Row-Level Security
- encryption at rest
- field-level encryption for high-sensitivity memory
- KMS-managed encryption keys
- role-based access control
- SSO and enterprise identity integration
- retention and consent controls
- legal hold
- regional data residency
- gateway rate limiting
- abuse detection
- tamper-evident audit evidence
- security control mapping

These controls should be introduced through documented architectural decisions as the system matures.

---

# Security Principle

Memory that persists can influence future decisions.

Therefore, the memory write path, read path, and deletion path are all security boundaries.