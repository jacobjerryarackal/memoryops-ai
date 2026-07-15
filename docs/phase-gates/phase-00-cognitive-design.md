# Phase 00 — Cognitive Design

## Core Question
Does MemoryOps AI have an explicit model of the user/system decision problem it is solving, including what deserves remembering, forgetting, retrieving, and governing?

## MemoryOps Mapping
MemoryOps AI defines a governed memory lifecycle. It models the system problem as a set of distinct lifecycle phases (write path, read path, deletion boundary) and scopes (tenant and user isolation). Stored state is classified into explicit memory types representing semantic facts, procedural preferences, and episodic time-bound events.

## Gate Conditions
- [x] Memory types (`semantic`, `procedural`, `episodic`) are defined in domain enums.
- [x] Memory statuses (`active`, `pending`, `rejected`, `archived`, `deleted`) represent the lifecycle states.
- [x] Policy disposition decisions (`SAVE`, `BLOCK`, `UPDATE_EXISTING`, `MERGE_WITH_EXISTING`) are modeled.
- [ ] Feedback loops and reinforcement learning loops are operationalized in active services.

## Evidence
- [enums.py](file:///d:/AI/memoryops-ai/services/api/app/domain/enums.py)
- [models.py](file:///d:/AI/memoryops-ai/services/api/app/domain/models.py)
- [api-contracts.md](file:///d:/AI/memoryops-ai/docs/api-contracts.md)

## Gaps
Feedback-driven reinforcement and active memory consolidation/pruning (compaction) are not yet implemented.

## Status
PARTIAL

## Next Unlock
Phase 3 planning to design memory feedback loops and validation sets.
