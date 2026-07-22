# API Contracts — MemoryOps AI

Canonical reference for the initial MemoryOps AI HTTP surface.

The API contract defines the boundary between external applications and the governed memory runtime.

Implementation changes that modify endpoint methods, paths, required fields, response semantics, or lifecycle behavior must update this document.

## Base URL

Development:

    http://localhost:8000

Interactive API documentation:

    /docs

## Scope Model

Memory operations are scoped by:

- `tenant_id`
- `user_id`

Every memory operation must preserve tenant and user isolation.

The initial API contract uses explicit scope fields in requests.

Authentication is not part of the initial implementation phase.

Future authentication must bind authenticated identity to the requested tenant and user scope without weakening repository-level isolation.

---

# Common Concepts

## Memory Types

Initial memory types:

- `semantic`
- `procedural`
- `episodic`

### Semantic

Facts and durable information.

Example:

    Jacob is an AI Engineer.

### Procedural

Preferences or instructions that influence future behavior.

Example:

    Jacob prefers production-grade engineering explanations.

### Episodic

Events, experiences, achievements, or time-bound information.

Example:

    Jacob built GIMS during a memory-system hackathon.

---

## Memory Status

Supported lifecycle states:

- `active`
- `pending`
- `rejected`
- `archived`
- `deleted`

Only `active` memories are eligible for normal retrieval.

---

## Sensitivity

Initial sensitivity levels:

- `low`
- `medium`
- `high`

Sensitivity classification may influence Policy Broker decisions.

---

## Policy Decisions

The Policy Broker may produce:

- `SAVE`
- `PENDING_APPROVAL`
- `BLOCK`
- `DROP_LOW_UTILITY`
- `UPDATE_EXISTING`
- `MERGE_WITH_EXISTING`

Every candidate memory decision must include a reason.

---

# POST /api/chat

Processes one application interaction through the governed memory pipeline.

The endpoint may:

- retrieve eligible memory
- compose memory context
- produce an assistant response
- extract candidate memories
- evaluate candidates through the Policy Broker
- persist authorized memory
- emit audit evidence

## Request

    {
      "tenant_id": "tenant_demo",
      "user_id": "user_demo",
      "message": "Remember that I prefer Python for AI backend systems.",
      "temporary_chat": false,
      "conversation_id": null
    }

## Fields

| Field | Required | Description |
|---|---|---|
| `tenant_id` | Yes | Tenant scope |
| `user_id` | Yes | User scope |
| `message` | Yes | Incoming application message |
| `temporary_chat` | No | Bypass persistent memory read and write |
| `conversation_id` | No | Optional conversation identifier |

## Temporary Chat

When:

    temporary_chat = true

the request must bypass:

- persistent memory retrieval
- candidate memory persistence

The request may still produce an assistant response.

## Response

    {
      "assistant_message": "Understood.",
      "used_memories": [],
      "candidate_memories": [
        {
          "content": "Jacob prefers Python for AI backend systems.",
          "memory_type": "procedural",
          "confidence": 0.92,
          "importance": 8,
          "sensitivity": "low",
          "decision": "SAVE",
          "reason": "Durable technical preference.",
          "memory_id": "mem_123"
        }
      ],
      "audit_event_ids": [
        "audit_123"
      ],
      "temporary_chat": false,
      "retrieval_mode": "none",
      "trace_id": "trace_123"
    }

## Candidate Memory Contract

Each candidate memory contains:

| Field | Description |
|---|---|
| `content` | Proposed memory content |
| `memory_type` | Semantic, procedural, or episodic |
| `confidence` | Extraction confidence |
| `importance` | Estimated long-term importance |
| `sensitivity` | Low, medium, or high |
| `decision` | Policy Broker disposition |
| `reason` | Human-readable policy reason |
| `memory_id` | Persisted or affected memory identifier when applicable |

The Extractor proposes candidate memory.

The Policy Broker determines `decision`.

The Extractor must not authorize persistence.

---

# Used Memory Contract

When memory contributes to context, `used_memories` contains:

    {
      "memory_id": "mem_123",
      "content": "Jacob prefers Python.",
      "memory_type": "procedural",
      "score": 0.82,
      "reason": "Relevant technical preference.",
      "score_breakdown": {
        "semantic_score": 0.91,
        "keyword_score": 0.70,
        "importance_score": 0.80,
        "recency_score": 0.95,
        "confidence_score": 0.92,
        "reinforcement_score": 0.20
      },
      "source": {
        "kind": "chat",
        "excerpt": "I prefer Python."
      }
    }

The ranking inputs are normalized to the range `[0,1]` before weights are applied. The normalization functions are:

*   `semantic_score = clamp(cosine_similarity, 0, 1)`
*   `keyword_score = matched_query_terms / max(total_unique_query_terms, 1)`
*   `importance_score = importance / 10`
*   `confidence_score = clamp(confidence, 0, 1)`
*   `recency_score = exp(-age_days / 30)`
*   `reinforcement_score = 1 - exp(-reinforcement_count / 5)`

The final retrieval score is computed as:

    score =
        0.35 * semantic_score
      + 0.20 * keyword_score
      + 0.15 * importance_score
      + 0.10 * recency_score
      + 0.10 * confidence_score
      + 0.10 * reinforcement_score

Every used memory must remain traceable to a source memory identifier.

---

# Retrieval Modes

`retrieval_mode` may be:

- `hybrid`
- `fallback`
- `none`

## Hybrid

Semantic and lexical retrieval signals were available.

## Fallback

The semantic retrieval path was unavailable and retrieval degraded to lexical matching.

## None

Persistent memory retrieval was intentionally bypassed or no retrieval path executed.

Retrieval failure must not automatically fail the host application response.

---

# GET /api/memories

Returns memories within tenant and user scope.

## Query Parameters

- `tenant_id` — required
- `user_id` — required
- `status` — optional
- `memory_type` — optional

Example:

    GET /api/memories?tenant_id=tenant_demo&user_id=user_demo

## Default Behavior

Deleted memories are excluded by default.

The normal active memory surface must never expose deleted memory as active state.

## Response

    [
      {
        "id": "mem_123",
        "tenant_id": "tenant_demo",
        "user_id": "user_demo",
        "content": "Jacob prefers Python.",
        "memory_type": "procedural",
        "status": "active",
        "importance": 8,
        "confidence": 0.92,
        "sensitivity": "low",
        "reinforcement_count": 1,
        "source_kind": "chat",
        "source_conversation_id": "conversation_demo",
        "source_excerpt": "Remember that I prefer Python.",
        "initial_policy_decision": "SAVE",
        "initial_policy_reason": "Durable technical preference.",
        "created_at": "2026-07-14T10:00:00Z",
        "updated_at": "2026-07-14T10:00:00Z",
        "archived_at": null,
        "deleted_at": null
      }
    ]

---

# GET /api/memories/{memory_id}

Returns one scoped memory.

## Query Parameters

- `tenant_id` — required
- `user_id` — required

## Behavior

The memory identifier alone is not sufficient authorization.

The requested memory must belong to the supplied tenant and user scope.

Return `404` when the memory does not exist within the requested scope.

## Response

Returns a `MemoryRecord`.

Viewing a governed memory should produce a `memory_viewed` audit event when implemented by the governance phase.

---

# GET /api/memories/{memory_id}/provenance

Returns memory provenance and lifecycle metadata.

## Query Parameters

- `tenant_id` — required
- `user_id` — required

## Response

    {
      "memory_id": "mem_123",
      "source_kind": "chat",
      "source_conversation_id": "conversation_123",
      "source_excerpt": "Remember that I prefer Python.",
      "initial_policy_decision": "SAVE",
      "initial_policy_reason": "Durable technical preference.",
      "status": "active",
      "created_at": "2026-07-14T10:00:00Z",
      "updated_at": "2026-07-14T10:00:00Z",
      "archived_at": null,
      "deleted_at": null,
      "reinforcement_count": 1,
      "importance": 8,
      "confidence": 0.92,
      "audit_event_ids": [
        "audit_123"
      ]
    }

The provenance API must not expose embeddings or secret material.

---

# GET /api/memories/{memory_id}/audit

Returns the audit timeline for one memory.

## Query Parameters

- `tenant_id` — required
- `user_id` — required
- `limit` — optional

## Response

Returns `AuditEvent[]`.

Events are ordered newest first.

---

# PATCH /api/memories/{memory_id}

Performs a governed memory update or lifecycle transition.

## Request

    {
      "tenant_id": "tenant_demo",
      "user_id": "user_demo",
      "content": "Jacob prefers Python for AI infrastructure.",
      "importance": 9,
      "confidence": 0.95,
      "status": "active"
    }

All mutable fields are optional except scope fields.

## Supported Lifecycle Transitions

Initial transitions include:

    pending → active
    pending → rejected
    active → archived
    archived → active

Content and supported scoring metadata may be edited through governed update operations.

## Deleted Memory

Deletion is terminal for the initial lifecycle contract.

A deleted memory cannot be restored through `PATCH`.

Attempts to update a deleted memory return `404`.

## Policy Gating

Content-changing update requests must be evaluated by the Policy Broker's safety validation (specifically deterministic secret blocking). If the proposed content contains secrets or credentials, the update is blocked, the record is not modified, and the endpoint returns a `400 Bad Request` with error code `POLICY_BLOCKED`.

## Response

Returns the updated `MemoryRecord`.

Every successful mutation must produce an audit event.

---

# DELETE /api/memories/{memory_id}

Logically deletes a memory.

## Request

    {
      "tenant_id": "tenant_demo",
      "user_id": "user_demo"
    }

## Behavior

Deletion performs:

    status = deleted
    deleted_at = current timestamp

The operation emits:

    memory_deleted

Deletion is idempotent.

A deleted memory must never return to:

- active listing
- semantic retrieval
- lexical retrieval
- ranking
- context composition

## Response

    {
      "memory_id": "mem_123",
      "status": "deleted",
      "deleted_at": "2026-07-14T11:00:00Z"
    }

This endpoint guarantees logical forgetting from governed MemoryOps read paths.

It does not claim immediate physical byte erasure.

---

# GET /api/audit

Returns append-only governance events.

## Query Parameters

- `tenant_id` — required
- `user_id` — optional
- `memory_id` — optional
- `limit` — optional

## Response

    [
      {
        "id": "audit_123",
        "tenant_id": "tenant_demo",
        "user_id": "user_demo",
        "memory_id": "mem_123",
        "action": "memory_created",
        "reason": "Candidate passed policy.",
        "metadata": {},
        "trace_id": "trace_123",
        "created_at": "2026-07-14T10:00:00Z"
      }
    ]

Audit events are append-only.

The initial API exposes no endpoint for updating or deleting audit history.

Audit metadata must not copy secret material.

---

# GET /api/metrics

Returns tenant-scoped business metrics.

## Query Parameters

- `tenant_id` — required

## Response

    {
      "total_memories": 42,
      "by_status": {
        "active": 30,
        "pending": 4,
        "rejected": 3,
        "archived": 2,
        "deleted": 3
      },
      "audit_events": 120,
      "by_action": {
        "memory_created": 42,
        "memory_deleted": 3,
        "memory_approved": 4
      }
    }

These are governance and business metrics.

Process-level operational telemetry is a separate concern.

---

# GET /healthz

Returns process health.

## Response

    {
      "status": "ok",
      "version": "0.1.0",
      "uptime_seconds": 120
    }

---

# GET /readyz

Returns dependency readiness.

## Response

    {
      "ready": true,
      "storage": "ready",
      "llm_provider": "ready",
      "embeddings_provider": "ready",
      "detail": {}
    }

Health and readiness are separate.

`healthz` answers whether the process is alive.

`readyz` answers whether the service is capable of serving governed memory operations.

---

# Trace Contract

Every request receives a `trace_id`.

The trace identifier is created at the gateway and propagated through downstream components.

Every HTTP response should eventually expose:

    x-trace-id

The JSON response may also include:

    trace_id

where the response contract requires it.

Operational logs must use the same trace identifier.

---

# Error Contract

Errors should use a predictable response shape.

    {
      "error": {
        "code": "MEMORY_NOT_FOUND",
        "message": "Memory was not found within the requested scope.",
        "trace_id": "trace_123"
      }
    }

Initial error codes may include:

- `VALIDATION_ERROR`
- `MEMORY_NOT_FOUND`
- `INVALID_LIFECYCLE_TRANSITION`
- `POLICY_BLOCKED`
- `STORAGE_UNAVAILABLE`
- `INTERNAL_ERROR`

## Error Code Mapping

The following table defines the relationship between HTTP response statuses and specific API error codes:

| HTTP Status | API Error Code | Description / Usage Scenario |
| :--- | :--- | :--- |
| `400 Bad Request` | `VALIDATION_ERROR` | Request payload validation fails, or immutable coordinates (`identity_slot`, `memory_type`) are modified. |
| `400 Bad Request` | `INVALID_LIFECYCLE_TRANSITION` | Attempting an invalid memory status transition (e.g. `archived` to `pending`). |
| `400 Bad Request` | `POLICY_BLOCKED` | A content-changing `PATCH` or chat message fails safety validation (e.g., contains a secret or violates policy). |
| `404 Not Found` | `MEMORY_NOT_FOUND` | Memory ID does not exist, scope does not match, or updating a terminal `deleted` memory. |
| `500 Internal Server Error` | `INTERNAL_ERROR` | System errors, execution failures, or audit log persistence failures. |
| `503 Service Unavailable` | `STORAGE_UNAVAILABLE` | Database or underlying persistence layer is unavailable. |

Error responses must not expose:

- stack traces
- database credentials
- API keys
- raw secret material

---

# API Invariants

1. Every memory operation is tenant and user scoped.
2. The Extractor cannot authorize memory persistence.
3. Policy decisions are visible through candidate memory results.
4. Pending memory is not retrievable.
5. Rejected memory is not retrievable.
6. Archived memory is excluded from normal active retrieval.
7. Deleted memory never enters governed retrieval.
8. Every persistent lifecycle mutation produces audit evidence.
9. Retrieval failure degrades safely where possible.
10. Every request receives a trace identifier.
11. Temporary chat bypasses persistent memory reads and writes.
12. API responses must not expose embeddings or secret material.

---

# Contract Evolution

This document describes the initial MemoryOps AI HTTP contract.

Future phases may introduce:

- authentication
- authorization
- evaluation endpoints
- worker health
- retention APIs
- legal hold
- consent APIs
- evidence APIs
- trace inspection
- SDK-specific compatibility guarantees

New API capabilities must extend the governance model.

They must not bypass the Policy Broker, repository scope guarantees, deletion guarantees, or audit requirements.