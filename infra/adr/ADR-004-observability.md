# ADR-004 — Observability and Audit

## Status

Accepted

## Context

MemoryOps AI must be both explainable and operable.

The system must be able to reconstruct the lifecycle of a memory and explain what was stored, blocked, updated, retrieved, approved, or deleted.

The platform must also expose operational information including request latency, failures, memory counts, and system performance.

Governance evidence and operational telemetry serve different purposes and have different retention, access, and immutability requirements.

A single logging stream is insufficient for both responsibilities.

## Decision

Introduce two complementary observability streams.

### Audit Log

Maintain an append-only audit stream for business-level memory lifecycle events.

Examples include:

- `memory_created`
- `memory_blocked`
- `memory_updated`
- `memory_approved`
- `memory_deleted`

The audit stream is the governance source of truth.

Audit events must preserve enough information to reconstruct why a memory operation occurred.

### Structured Operational Logs

Emit structured JSON logs for system execution.

Operational events (such as `memory_retrieved`, `retrieval_failed`, and `temporary_chat_skipped`) should include, where applicable:

- `trace_id`
- `tenant_id`
- `user_id`
- `event`
- `latency_ms`
- `memory_count`
- `status`

A trace identifier must be generated at the request gateway and propagated through downstream components.

Operational logging should be compatible with future OpenTelemetry instrumentation.

## Derived Metrics

Operational and audit events may be used to derive metrics including:

- memory write count
- retrieval count
- blocked candidate count
- deletion count
- retrieval latency
- candidate-to-saved rate
- correction rate
- helpfulness rate

## Alternatives Considered

### Application Logs Only

Standard application logs could record memory lifecycle actions.

Rejected because operational logs do not provide a durable governance history and may be rotated or deleted.

Application logs alone cannot reliably prove lifecycle events such as memory deletion.

### Audit Events Only

All events could be stored in the audit system.

Rejected because audit records are not designed for detailed latency, throughput, request diagnostics, or distributed execution tracing.

### Full Observability Platform Immediately

The initial system could deploy OpenTelemetry, Prometheus, Grafana, Tempo, Jaeger, and LLM tracing infrastructure.

Rejected for the initial architecture because the operational cost is disproportionate to the current system maturity.

The system will instead emit structured telemetry that can later be exported to dedicated observability infrastructure.

## Trade-offs

Maintaining two observability streams introduces two event paths.

This increases implementation responsibility and requires developers to understand whether an event is a governance event, an operational event, or both.

The complexity is accepted because audit evidence and operational telemetry have fundamentally different purposes.

## Consequences

Every memory lifecycle action must record an audit event.

Missing lifecycle audit events are considered correctness failures.

Structured operational logs must use machine-readable JSON.

A `trace_id` must be generated at the gateway and propagated through the request lifecycle.

The architecture will introduce an Audit Service responsible for recording governance events.

Operational logging must remain independent from business logic where possible.

## Invariants

1. Every persistent memory lifecycle mutation must produce an audit event.
2. Audit history must be append-only.
3. Audit events must preserve human-readable reasons where a decision is involved.
4. Every request must receive a trace identifier.
5. Trace identifiers must propagate through downstream memory components.
6. Operational failures must be visible through structured logs.
7. Audit evidence and operational telemetry must remain logically separate.

## Exit Strategy

Structured operational logs may later be exported through OpenTelemetry.

Traces may be sent to Tempo or Jaeger.

Metrics may be exported to Prometheus and visualized in Grafana.

LLM-specific traces may be sent to a dedicated AI observability platform.

Because trace identifiers and structured event fields are established from the beginning, future observability integrations should primarily change telemetry transport rather than core memory business logic.