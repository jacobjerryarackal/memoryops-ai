# Operational Runbook: Production Incident Checklist

**Incident Classification:** INC-GEN-01  
**Severity:** All Severity Levels

This checklist defines the operational protocol to triage, mitigate, and resolve production incidents in the MemoryOps AI environment.

---

## Phase 1: Detection & Triage (T + 5 Minutes)

- [ ] **Verify Alert Validity:** Confirm the incident is real (e.g., check metrics dashboard, server logs, or API endpoints).
- [ ] **Determine System Impact:**
  - [ ] Complete Outage: API completely unreachable (Severity 1).
  - [ ] Degraded State: Slow response times / Pool exhaustion / Worker failures (Severity 2).
  - [ ] Minor Issue: Edge-case failures / telemetry missing (Severity 3).
- [ ] **Check Service Logs:** Inspect container stdout:
  ```bash
  docker logs --tail 100 memoryops-api
  ```
- [ ] **Establish Communication:** Open an incident channel (Slack, Teams, or status page) and announce the investigation.

---

## Phase 2: Isolation & Mitigation (T + 15 Minutes)

- [ ] **Check Database Connectivity:**
  - If database is down: Refer to **[Database Recovery Runbook](runbook-database-recovery.md)**.
- [ ] **Check Connection Pool Capacity:**
  - If pool is saturated: Refer to **[Connection Starvation Runbook](runbook-connection-pool-starvation.md)**.
- [ ] **Check Recent Deployments:**
  - If a deployment occurred recently, check if a database schema migration failed. Refer to **[Failed Migration Runbook](runbook-failed-migration-recovery.md)**.
- [ ] **Hot-Fix Rollback (If needed):**
  - If a recent code update caused the failure, execute the deployment rollback procedure immediately.

---

## Phase 3: Resolution & Verification (T + 30 Minutes)

- [ ] **Verify Core API Performance:** Test API endpoints with mock request:
  ```bash
  curl -I http://localhost:8000/health
  ```
- [ ] **Verify Lifecycle Scheduling:** Ensure background tasks run without error.
- [ ] **Confirm Resolve status:** Announce incident resolution on the communication channels.

---

## Phase 4: Post-Mortem & Preventative Actions (Post-Incident)

- [ ] **Analyze Root Cause:** Document the sequence of events and why the mitigation resolved it.
- [ ] **Identify Improvements:** Determine if new tests, code changes, or telemetry are needed.
- [ ] **Update Runbooks:** Refine these runbooks if actual incident steps diverged from documentation.
