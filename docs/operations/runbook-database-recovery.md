# Operational Runbook: Database Recovery

**Incident Classification:** DB-RECOVERY-01  
**Severity:** Critical (Data Loss / System Outage)

---

## 1. Symptoms & Trigger Conditions

- Data corruption detected in memory store tables.
- Accidental cascade deletion of memory records or audit logs.
- Database container volume loss requiring recovery to the latest point-in-time snapshot.

---

## 2. Prerequisite Check

Locate the latest backup file in your repository or backup storage:
- Default path: `infra/db/backup.dump`
- Ensure you have network access to the Docker daemon.

Verify backup file integrity:
```bash
python infra/db/verify_backup.py
```
*Do not proceed if integrity verification fails.*

---

## 3. Recovery Procedure

### Step 1: Re-establish PostgreSQL container (if destroyed)
If the database container itself is lost or corrupted, recreate it:
```bash
docker rm -f memoryops-postgres
docker run -d --name memoryops-postgres -p 5433:5432 -e POSTGRES_PASSWORD=postgres pgvector/pgvector:pg16
```

### Step 2: Run Restore Automation
Execute the automated restore script to copy the backup file into the container, drop current connections, drop the database, recreate it, and restore the schema and tables:
```bash
python infra/db/restore.py
```

### Step 3: Run Database Migrations
Run migrations to ensure any schema updates applied after the backup are safely run on the restored database:
```bash
python infra/run_migrations.py
```

### Step 4: Verify Restoration Data
Check that tables are present and populated:
```bash
docker exec -it memoryops-postgres psql -U postgres -d memoryops_ai -c "SELECT COUNT(*) FROM memories;"
docker exec -it memoryops-postgres psql -U postgres -d memoryops_ai -c "SELECT COUNT(*) FROM memory_audit_logs;"
docker exec -it memoryops-postgres psql -U postgres -d memoryops_ai -c "SELECT COUNT(*) FROM lifecycle_run_history;"
```

### Step 5: Test API Connectivity & Retrieval
Run a quick curl or retrieve query to verify correct integration:
```bash
curl -X POST http://localhost:8000/api/v1/memories/search \
  -H "Content-Type: application/json" \
  -d '{"tenant_id": "test_tenant", "user_id": "test_user", "query": "test query"}'
```
