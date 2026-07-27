# Operational Runbook: Connection Pool Starvation

**Incident Classification:** DB-POOL-01  
**Severity:** Critical (Service degradation / API timeouts)

---

## 1. Symptoms & Alerts

- API requests fail with `TimeoutError` or `asyncpg.exceptions.PoolTimeoutError`.
- Metrics indicate connection pool peak saturation at 100% capacity (e.g., active connections = `POSTGRES_MAX_POOL_SIZE`).
- Latency breakdown for `WriteService` and `RetrievalCoordinator` show massive spikes (exceeding connection timeout limits, default `10.0s`).

---

## 2. Diagnostics

Log in to the database container to inspect active pg_stat_activity:
```bash
docker exec -it memoryops-postgres psql -U postgres -d memoryops_ai
```

### Query A: Inspect Active Connections and States
```sql
SELECT pid, usename, client_addr, state, age(clock_timestamp(), query_start) as duration, query
FROM pg_stat_activity
WHERE state <> 'idle'
ORDER BY duration DESC;
```
*Identify queries running for longer than 2.0s.*

### Query B: Identify Blocked or Locking Transactions
```sql
SELECT
    blocked_locks.pid     AS blocked_pid,
    blocked_activity.query    AS blocked_statement,
    blocking_locks.pid    AS blocking_pid,
    blocking_activity.query   AS blocking_statement
FROM  pg_catalog.pg_locks         blocked_locks
JOIN pg_catalog.pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid
JOIN pg_catalog.pg_locks         blocking_locks 
    ON blocking_locks.locktype = blocked_locks.locktype
    AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database
    AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
    AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
    AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
    AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
    AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
    AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
    AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
    AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
    AND blocking_locks.pid != blocked_locks.pid
JOIN pg_catalog.pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid
WHERE NOT blocked_locks.granted;
```

---

## 3. Mitigation Procedures

### Step 1: Terminate Offending or Blocking Queries
If a query is stuck in a transaction or holding a lock:
```sql
-- Cancel the active query (graceful)
SELECT pg_cancel_backend(blocking_pid);

-- Terminate the backend connection (forced)
SELECT pg_terminate_backend(blocking_pid);
```

### Step 2: Scale the Pool Size Dynamically
If the starvation is caused by high traffic volume rather than slow queries/leaks:
1. Open the production environment configuration file `.env`.
2. Increase the connection pool limits:
   ```env
   POSTGRES_MIN_POOL_SIZE=5
   POSTGRES_MAX_POOL_SIZE=25
   POSTGRES_CONNECTION_TIMEOUT=15.0
   ```
3. Restart the MemoryOps API service:
   ```bash
   docker restart memoryops-api
   ```

### Step 3: Investigate Connection Leaks
If pool starvation occurs under low traffic, check for connection leaks in code:
- Ensure all repository calls are wrapped in `async with get_connection() as conn:` blocks.
- Verify no database connection is opened in raw background loops without context managers.
