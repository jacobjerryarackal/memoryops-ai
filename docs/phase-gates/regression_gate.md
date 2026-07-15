# MemoryOps AI — Regression Gate Workflow

This document defines the regression validation steps to run after completing any code change or architectural correction.

## Step 1: Execute Local Validations
1. Run any new/modified focused tests.
2. Run the complete test suite:
   ```powershell
   pytest
   ```
3. Run the git check:
   ```powershell
   git diff --check
   ```

## Step 2: Produce an Evidence Report
Record:
1. **Regression Baseline Delta:** The exact test counts (baseline vs. current).
2. **Changed Files:** Path links of modified and added files.
3. **Architecture Impact:** Brief notes on how the change aligns with existing ADRs and specifications.
4. **Phase Freeze Impact:** Confirm that no frozen boundaries (Phase 1 write-path, Phase 2 read-path retrieval invariants) were compromised.
5. **Remaining Gaps:** Identify any remaining non-blocking items or gaps deferred to later phases.
