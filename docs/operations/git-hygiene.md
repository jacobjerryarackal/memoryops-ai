# Git Repository Hygiene Report

This report documents the audit, `.gitignore` corrections, credential security scans, and index untracking applied to ensure only intentional source code and configuration templates are tracked by Git.

---

## 1. Evaluation JSON Classification

We analyzed the three evaluation JSON files to separate generated outputs from compliance release evidence:

### A. Intentionally Maintained Release Evidence (Tracked)
*   **File:** [evaluation_evidence.json](file:///d:/AI/memoryops-ai/evals/evaluation_evidence.json)
*   **Classification:** Kept tracked.
*   **Rationale:** This file is explicitly referenced as official machine-readable evidence for compliance verification in the [Phase 09 Gate Checklist](file:///d:/AI/memoryops-ai/docs/phase-gates/phase-09-evaluation-systems.md). Keeping it tracked ensures static gate verification tools can validate metrics thresholds without needing execution environments.

### B. Generated Reproducible Outputs (Untracked & Ignored)
*   **Files:**
    *   `evals/scorecard.json`
    *   `evals/evaluation_results.json`
*   **Classification:** Removed from Git tracking index and added to `.gitignore`.
*   **Rationale:** Both files are purely generated metrics summaries. They are fully reproducible by running the evaluation executor:
    ```powershell
    python evals/runner.py
    ```
    This script parses the static golden dataset at `evals/data/golden_dataset.json` and outputs the structured scorecard.json and evaluation_results.json programmatically.

---

## 2. Git Ignore Rule Adjustments

We corrected the root [.gitignore](file:///d:/AI/memoryops-ai/.gitignore) to eliminate overriding issues:

1.  **Resolved Overrides:** Removed the broad `.env*` pattern at the bottom of the file which was inadvertently overriding the `!.env.example` whitelisting exception.
2.  **Explicit Environment Rules:** Confirmed the whitelisting parameters are exactly:
    ```gitignore
    .env
    .env.*
    !.env.example
    ```
3.  **Added Ignores:** Added explicit ignore blocks for:
    *   Reproducible evaluation outputs (`evals/scorecard.json`, `evals/evaluation_results.json`).
    *   Local test logs and caches (`pytest_output.txt`, `pytest_run_output.txt`, `pytest_output.log`).
    *   General certificate formats (`*.key`, `*.crt`, `*.pfx`).

---

## 3. Staged Untracking (Index Cleanup)

We unstaged the following cache and generated files from Git's version control tracking index (retaining local workspace copies intact):
*   `.env` (local dev setup config)
*   `evals/scorecard.json` (generated metric scorecard)
*   `evals/evaluation_results.json` (generated categorized results)
*   `pytest_output.txt` and `pytest_run_output.txt` (local run dumps)
*   `**/__pycache__/` and `.pytest_cache/` (python bytecodes and test state caches)

---

## 4. Security & Credentials Audit

We scanned the entire Git-tracked workspace for potential secret exposure:
*   **OpenAI Keys:** All matches for `sk-proj-` are verified to be mock keys (`sk-proj-123456789012345678901234`) inside testing mocks ([test_governance_service.py](file:///d:/AI/memoryops-ai/tests/test_governance_service.py)) or placeholder text in documentation.
*   **JWT Secrets:** The default jwt key in [config.py](file:///d:/AI/memoryops-ai/services/api/app/config.py) is a standard development string (`memoryops-jwt-secret-key-change-in-production`) designed to fail-fast in production if not overridden.
*   **Database Passwords:** Default values in [config.py](file:///d:/AI/memoryops-ai/services/api/app/config.py) (`postgres`/`postgres`) are local development configurations only.
*   **.env.example Verification:** Confirmed that [.env.example](file:///d:/AI/memoryops-ai/.env.example) contains only empty keys for active secrets (such as `OPENAI_API_KEY=` and `GEMINI_API_KEY=`) and default local placeholders.

**Audit Status:** `CLEAN`. No active production credentials or secrets are committed.

---

## 5. Verification Results

### A. Git Status Output
Staged files verification:
```powershell
git status --short
```
*   `D  .env` (untracked, local file preserved)
*   `D  evals/scorecard.json` (untracked, ignored)
*   `D  evals/evaluation_results.json` (untracked, ignored)
*   `M  .gitignore` (ignore rules updated)
*   `evals/evaluation_evidence.json` remains correctly tracked.

### B. Regression Check
All tests pass cleanly:
```
282 passed, 1 skipped, 2 warnings in 226.18s (0:03:46)
```
