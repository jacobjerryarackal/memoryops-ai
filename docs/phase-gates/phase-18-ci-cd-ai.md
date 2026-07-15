# Phase 18 — CI/CD for AI

## Core Question
Does the repository automatically protect AI-sensitive architecture and invariants during change and release?

## MemoryOps Mapping
Automated unit and integration tests (`pytest`) cover retrieval and writing invariants. Developer and agent instructions in `AGENTS.md` mandate executing the regression checks, baseline delta assessments, and whitespace checks.

## Gate Conditions
- [x] Automated test suite covers all API, retrieval, policy, and telemetry contracts.
- [x] Local workflow rules enforce regression baseline checking and whitespace checking.
- [ ] CI pipeline automation (e.g., GitHub Actions) is wired to run tests on PR submissions automatically.
- [ ] Automations (PR gates) inspect changes to sensitive paths (ADRs, schemas).

## Evidence
- [tests/](file:///d:/AI/memoryops-ai/tests/)
- [AGENTS.md](file:///d:/AI/memoryops-ai/AGENTS.md)
- [regression_gate.md](file:///d:/AI/memoryops-ai/docs/phase-gates/regression_gate.md)

## Gaps
No CI/CD pipeline automation (such as GitHub Action workflow files) is configured in the repository.

## Status
PARTIAL

## Next Unlock
Future phase implementation of GitHub Actions or CI configuration to enforce test execution and formatting validation.
