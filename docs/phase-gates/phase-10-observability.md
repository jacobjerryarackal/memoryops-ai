# Phase 10 — Observability

## Core Question
Can operators understand important MemoryOps execution behavior through correlated operational evidence without polluting governance audit records?

## MemoryOps Mapping
MemoryOps AI implements two distinct observability paths in accordance with `ADR-004`. The read path emits non-persistent structured JSON logs covering timed retrieve, rank, and compose latencies. Request trace IDs are generated at the gateway and propagated downstream. The write path records persistent, append-only governance events via the `AuditService`. Read-path telemetry is kept separate from governance audit logs.

## Gate Conditions
- [x] Request trace IDs correlate gateway routing, coordinator timing, and responses.
- [x] Structured operational JSON logging tracks retrieval durations and metrics.
- [x] Governance audit log (`AuditService`) records mutations.
- [x] Read-path telemetry remains separated from governance audit logs.
- [ ] Write-path components and policy broker decisions emit operational telemetry.
- [ ] OpenTelemetry collectors and distributed trace exports are integrated.

## Evidence
- [ADR-004-observability.md](file:///d:/AI/memoryops-ai/infra/adr/ADR-004-observability.md)
- [retrieval_telemetry.py](file:///d:/AI/memoryops-ai/services/api/app/services/retrieval_telemetry.py)
- [audit.py](file:///d:/AI/memoryops-ai/services/api/app/services/audit.py)
- [chat.py](file:///d:/AI/memoryops-ai/services/api/app/routes/chat.py)
- [test_retrieval_telemetry.py](file:///d:/AI/memoryops-ai/tests/test_retrieval_telemetry.py)

## Gaps
The write path services (Extractor, Policy Broker, and Write Service) do not yet emit structured operational JSON logs. No external collectors (OTel, Prometheus, Grafana) are wired.

## Status
PARTIAL

## Next Unlock
Phase 3 telemetry updates to instrument write-path operations.
