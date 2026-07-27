# Operational Runbook: Failed Migration Recovery

**Incident Classification:** DB-MIGRATE-01  
**Severity:** High (System Deployment Blocked / Part-Applied Schema)

---

## 1. Symptoms

- Deployment fails during the migration step.
- Database starts throwing errors about missing columns, duplicate indexes, or relation mismatches (e.g., `Relation "memories" already exists`).
- The application crashes on startup with initialization exceptions.

---

## 2. Diagnostics

Log in to PostgreSQL and inspect the applied migrations history table:
```bash
docker exec -it memoryops-postgres psql -U postgres -d memoryops_ai
```

### Query A: Check Applied Migration History
```sql
SELECT version, name, applied_at FROM schema_migrations ORDER BY version DESC;
```
*(Verify which migration version failed or is partially applied.)*

### Query B: Check for Active Locking Processes
If a migration is hanging, it might be waiting on a database lock:
```sql
SELECT pid, query, state, wait_event_type, wait_event FROM pg_stat_activity WHERE query LIKE '%ALTER%' OR query LIKE '%CREATE%';
```

---

## 3. Remediation & Recovery

Depending on the severity, choose one of the following paths:

### Path A: Automatic Restoration to Pre-Migration State (Recommended)
If the migration failed and corrupted the schema:
1. Stop the application services to prevent writes:
   ```bash
   docker stop memoryops-api
   ```
2. Restore the database using the latest pre-deployment backup:
   ```bash
   python infra/db/restore.py
   ```
3. Fix the buggy migration script in the codebase.
4. Start the migration runner again:
   ```bash
   python infra/run_migrations.py
   ```
5. Restart the application services:
   ```bash
   docker start memoryops-api
   ```

### Path B: Manual DDL Rollback (Partial Failure)
If the migration runner does not support automatic transactional rollbacks for certain DDL commands (like index creation):
1. Identify the partially created object (e.g., a index on `memories`).
2. Drop it manually:
   ```sql
   -- Examples:
   DROP INDEX IF EXISTS idx_memories_embedding_cosine;
   ALTER TABLE memories DROP COLUMN IF EXISTS new_field;
   ```
3. Delete the failed migration version record from the migrations tracker table to allow it to run again:
   ```sql
   DELETE FROM schema_migrations WHERE version = 'failed_version_number';
   ```
4. Fix the migration file, commit, and redeploy.
