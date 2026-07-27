# Operational Runbook: Background Worker Recovery

**Incident Classification:** LFC-WORKER-01  
**Severity:** Medium (Degraded performance / Governance backlog)

---

## 1. Symptoms & Alerts

- Background lifecycle jobs (Compactor, Summarizer, Retention/Archiver) show a status of `FAILED` in logging or database records.
- Stale memories are not archived (retention policy backlog) or memory count exceeds optimal compactor limits.
- Scheduler logs contain messages such as `Error running job '...'` or database connection issues within lifecycle context.

---

## 2. Diagnostics

Query the lifecycle run history database table to inspect the status of background jobs:
```bash
docker exec -it memoryops-postgres psql -U postgres -d memoryops_ai
```

### Query A: Inspect Recent Background Runs
```sql
SELECT job_name, status, started_at, completed_at, error_message
FROM lifecycle_run_history
ORDER BY started_at DESC
LIMIT 15;
```

### Query B: Identify Stuck Background Jobs
If a job status remains `RUNNING` for longer than 30 minutes:
```sql
SELECT job_name, started_at, tenant_id, user_id
FROM lifecycle_run_history
WHERE status = 'running' AND started_at < NOW() - INTERVAL '30 minutes';
```

---

## 3. Remediation & Recovery

### Step 1: Recover Stuck Jobs
If a lifecycle job is hung:
1. Restart the background worker service to release event loop resource locks:
   ```bash
   docker restart memoryops-api
   ```
2. Confirm that the stuck job status has been set/restored or marked failed after restarting.

### Step 2: Fix Data-Specific Exceptions
If a job fails consistently with a validation or data parsing error:
1. Extract the `tenant_id` and `user_id` from the failed run history record.
2. Verify if the target user's memories contain corrupt structure or circular dependencies:
   ```sql
   SELECT id, content, status FROM memories WHERE tenant_id = 'failed_tenant' AND user_id = 'failed_user';
   ```
3. Exclude or correct the corrupt data records, then trigger a manual compaction run.

### Step 3: Trigger Job Manually
To verify a worker works after remediation, trigger the job manually using the API endpoint:
```bash
curl -X POST http://localhost:8000/api/v1/lifecycle/run \
  -H "Content-Type: application/json" \
  -d '{"job_name": "compactor", "tenant_id": "target_tenant", "user_id": "target_user"}'
```
Check that the run completes successfully (`status = COMPLETED`).
