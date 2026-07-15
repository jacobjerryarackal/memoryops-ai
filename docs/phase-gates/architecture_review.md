# MemoryOps AI — Architecture Review Workflow

This document defines the rules for performing a no-feature architectural verification and contract review on the codebase.

## Step 1: Compare Source against Authoritative Specifications
Cross-reference the active implementation in the repository against:
1. `docs/design/retrieval-spine.md` (or the actual retrieval spine path)
2. `docs/api-contracts.md`
3. ADRs (ADR-001 through ADR-007)
4. System Overview (`docs/architecture/system-overview.md`)

Verify:
* Explicit domain schema alignment.
* Proper repository isolation checks (tenant, user, status).
* Exact ranking formulas, weights, and stable sequential tie-breakers.
* Context selection budgets (characters and count limits) and skipped oversized memory behavior.
* Correct exception boundaries (embedding service failures fail back; downstream exceptions propagate; telemetry fails safely).

## Step 2: Identify Scope Drift and Gaps
* Check if any Phase 3/future features were accidentally implemented.
* Identify if any code updates altered frozen Phase 1 write path boundaries.
* Distinguish between documentation drift (discrepancy in doc text only) and implementation defects (actual code mismatch with specification).

## Step 3: Enforce Corrective Actions Only
* Do NOT implement new features during this review.
* Allow only the minimum bounded correction directly justified by a local specification violation.
* Add focused unit tests to prevent future regressions.
