# MemoryOps AI — Agentic SWE Kit Local Mapping

This document maps concepts from the external `agentic-swe-kit` framework to their specific operational equivalents in the MemoryOps AI repository. 

*MemoryOps AI does not implement the entire external agentic-swe-kit framework. Concerns that are not yet operationalized are marked honestly as PLANNED.*

| External SWE Kit Concept | MemoryOps Local Equivalent | Authoritative Local Document | Local Workflow / Gate | Current Status |
| :--- | :--- | :--- | :--- | :--- |
| **Cognitive & Architecture Design** | Phase 0 Design and Architecture | `docs/architecture/system-overview.md`, ADRs | `PHASE GATE` / `ARCHITECTURE REVIEW` | **OPERATIONALIZED** |
| **Memory Architecture** | Governed write-path and deterministic read-path retrieval | `docs/design/retrieval-spine.md`, ADR-001 through ADR-007 | `ARCHITECTURE REVIEW` | **OPERATIONALIZED** |
| **Observability** | Structured retrieval telemetry, request trace IDs, and latency spans | `infra/adr/ADR-004-observability.md` | `ARCHITECTURE REVIEW` / `REGRESSION GATE` | **OPERATIONALIZED** |
| **Governance** | Policy broker check, admission gates, and append-only audit log | `docs/governance.md`, `services/api/app/services/audit.py` | `PHASE GATE` | **OPERATIONALIZED** |
| **AI PR Review Agent** | PR validation against system rule bounds and ADR contracts | `AGENTS.md` | `ARCHITECTURE REVIEW` / `REGRESSION GATE` | **OPERATIONALIZED** (Implemented locally as agent system instructions) |
| **Evaluation Framework** | LLM memory retrieval quality and accuracy evaluation suite | `ROADMAP.md` (Phase 3 milestone) | N/A | **PLANNED** (Not yet operationalized) |
| **Compaction / Memory Decay** | Background reinforcement and decay workers | `ROADMAP.md` (Phase 2 milestone) | N/A | **PLANNED** (Not yet operationalized) |
| **Release Checks & CI/CD** | Automated pipeline checks for whitespace, diff check, and tests | `AGENTS.md` | `REGRESSION GATE` | **OPERATIONALIZED** |
