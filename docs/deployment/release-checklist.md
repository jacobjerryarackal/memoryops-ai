# Release, Rollback & Production Verification Checklist

This document outlines the standard release gates, rollback steps, and post-deployment verification procedures.

---

## 1. Release Gating Checklist

Execute these steps *before* tagging a release as production-ready:

- [ ] **Run Regression Tests (Memory):** Ensure 100% pass rate.
  ```bash
  $env:DATABASE_TYPE="memory"; python -m pytest
  ```
- [ ] **Run Regression Tests (Postgres):** Ensure 100% pass rate.
  ```bash
  $env:DATABASE_TYPE="postgres"; python -m pytest
  ```
- [ ] **Run Performance Benchmarks:** Run the benchmark suite and confirm performance matches SLA requirements:
  ```bash
  python tests/run_benchmarks.py
  ```
- [ ] **Generate Pre-Deployment Backup:** Create a full snapshot of the production database before applying schema changes:
  ```bash
  python infra/db/backup.py
  python infra/db/verify_backup.py
  ```
- [ ] **Approve Release Documentation:** Ensure `CHANGELOG.md` is updated with version release details.

---

## 2. Rollback Checklist

If the deployment fails post-gating (e.g., error rate > 1%, memory leaks detected, or connection pool starvation occurs):

- [ ] **Step 1: Declare Incident & Stop Traffic:** Set load balancer routing to safe maintenance page or stop api tasks:
  ```bash
  docker stop memoryops-api
  ```
- [ ] **Step 2: Database Restore (DDL / Data Rollback):** Restore PostgreSQL schemas and data records to the pre-deployment backup:
  ```bash
  python infra/db/restore.py
  ```
- [ ] **Step 3: Revert Application Code:** Revert application to the previous docker image tag or git commit:
  ```bash
  git checkout tags/v1.X.X  # Previous version tag
  ```
- [ ] **Step 4: Restart Application Service:**
  ```bash
  docker start memoryops-api
  ```
- [ ] **Step 5: Verify Health:** Run the Production Verification Checklist (Section 3) to confirm system has recovered to its stable state.

---

## 3. Production Verification Checklist (Smoke Tests)

Run these checks immediately after completing a deployment (or rollback):

- [ ] **API Health Check:** Confirm health endpoint returns `200 OK`:
  ```bash
  curl http://localhost:8000/health
  ```
- [ ] **Write Path Validation:** Write a temporary memory record:
  ```bash
  curl -X POST http://localhost:8000/api/v1/memories \
    -H "Content-Type: application/json" \
    -d '{"tenant_id": "verify_tenant", "user_id": "verify_user", "content": "Deployment smoke test memory"}'
  ```
- [ ] **Read/Retrieval Path Validation:** Retrieve the written memory record:
  ```bash
  curl -X POST http://localhost:8000/api/v1/memories/search \
    -H "Content-Type: application/json" \
    -d '{"tenant_id": "verify_tenant", "user_id": "verify_user", "query": "smoke test"}'
  ```
- [ ] **Audit Trailing Check:** Confirm an audit log entry was created for the write action:
  ```sql
  SELECT action, reason FROM memory_audit_logs WHERE tenant_id = 'verify_tenant' AND user_id = 'verify_user';
  ```
- [ ] **Lifecycle Scheduling Check:** Confirm the background executor loop initializes successfully and checks in without raising exceptions.
