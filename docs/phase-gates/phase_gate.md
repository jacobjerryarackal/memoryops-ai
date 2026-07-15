# MemoryOps AI — Pre-Implementation Phase Gate Workflow

This document defines the pre-implementation phase gate checklist. The agent must execute this workflow BEFORE making any modifications or proposing code changes.

## Step 1: Read Authoritative Local Sources
Read the following documents in order:
1. Product Blueprint (`docs/design/product-blueprint.md` or similar)
2. `ROADMAP.md`
3. Architecture Overview (`docs/architecture/system-overview.md` or similar)
4. Local ADRs (`infra/adr/`)
5. Locked Pipeline/Spine Specification (`docs/design/retrieval-spine.md` or similar)

## Step 2: Establish the Regression Baseline
Run the complete regression suite to establish the pre-change baseline:
```powershell
pytest
```
* Note the total number of collected and passed tests. If any tests fail, stop and investigate baseline drift.

## Step 3: Reconstruct the Implementation Boundary
Analyze the source code to map:
* The input/output parameters of target call sites.
* Class structures and runtime dependencies.
* Exception ownership at boundary interfaces.

## Step 4: Detect Missing Dependencies & Collisions
* Verify if all necessary helper classes, schemas, or database methods are present.
* Check for contract collisions with Phase 1 (write path) and Phase 2 (read path) frozen boundaries.

## Step 5: Classify Readiness Status
Based on findings, output one of the following statuses:
* **READY:** All design contracts are clear, dependencies are present, and there is no contradiction.
* **REQUIRES DESIGN CLARIFICATION:** Clarifying questions exist regarding weights, bounds, schemas, or error behavior. Do not use the `ask_question` tool; instead, document these in the implementation plan.
* **BLOCKED:** An architectural contradiction or missing dependency makes implementation impossible without violating local ADRs or spine specifications.

**RULE: DO NOT PROCEED TO IMPLEMENTATION OR CODE MODIFICATION WHEN BLOCKED.**
