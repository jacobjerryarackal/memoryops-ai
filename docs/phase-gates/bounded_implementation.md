# MemoryOps AI — Bounded Implementation Workflow

This document defines the bounded implementation rules for modifying project source code once a phase gate is classified as READY and approved by the user.

## Step 1: Minimum Bounded Modifications
* Modify ONLY the files explicitly allowed/justified by the task scope.
* Never introduce speculative abstractions, unused interfaces, framework dependencies, or premature optimization.
* Keep changes focused; avoid unrelated styling cleanups, package reorganizations, or refactoring.

## Step 2: Invariant & Phase Gate Preservation
* Preserve the Phase 1 write path freeze.
* Preserve the Phase 2 read path retrieval weights, tie-breakers, and budgets unless explicitly authorized.
* Respect security constraints: no hardcoded secrets, no raw memory data leakage in logs.

## Step 3: Focused Test Addition
* Add focused unit/integration tests covering all target requirements in a separate test file or under an existing test file where appropriate.
* Do not rely on human console/stdout output scraping. Use test-local recorders, mock frameworks, or explicit schema asserts.

## Step 4: Verify Local correctness
1. Run the new focused tests:
   ```powershell
   pytest tests/your_focused_test_file.py
   ```
2. Run the complete regression suite:
   ```powershell
   pytest
   ```
3. Run Git diff check to verify that no trailing whitespace or check errors were introduced:
   ```powershell
   git diff --check
   ```
   Ensure the output is clean before ending your turn.
