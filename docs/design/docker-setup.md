# Docker Persistence Environment Guide

This document describes how to set up, run, migrate, and connect to the Docker-based PostgreSQL persistence environment for MemoryOps AI local development.

---

## 1. Prerequisites

- **Docker Desktop** (or Docker Engine with Docker Compose v2) installed and running.
- **Python 3.11+** installed on the host machine.

---

## 2. Docker Compose Configuration

The project includes a `docker-compose.yml` file at the root of the repository that launches a PostgreSQL instance with the `pgvector` extension pre-installed.

### Environment Variable Mapping
The service loads standard environment variables from your local `.env` file:
* `POSTGRES_USER`: The superuser username (default: `postgres`).
* `POSTGRES_PASSWORD`: The superuser password (default: `postgres`).
* `POSTGRES_DB`: The database name created upon initialization (default: `memoryops_ai`).
* `POSTGRES_PORT`: The port bound to the host (default: `5432`).

---

## 3. Operations Workflow

### Startup
To start the database in the background, run the following command from the repository root:
```powershell
docker compose up -d
```

### Checking Database Health
The database service is configured with a healthcheck. To see if it is operational:
```powershell
docker compose ps
```
The status should say `healthy`.

### Shutdown
To stop the container without losing your data (persisted in a Docker volume):
```powershell
docker compose down
```

To stop and completely remove the data volume:
```powershell
docker compose down -v
```

---

## 4. Migration Workflow

Once the database container is running and healthy, apply the database schema by executing the migration runner script from the host machine:

```powershell
python infra/db/run_migrations.py
```

This script:
1. Checks for a `migrations_applied` tracking table.
2. Discovers SQL migration scripts located in `infra/db/migrations/`.
3. Runs unapplied migrations in transaction blocks and logs progress.

---

## 5. Application Connection Details

The Python application connects to PostgreSQL using the `asyncpg` driver.

When running the application services or tests on your host machine, configure your `.env` file with these values:

```env
DATABASE_TYPE=postgres
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=memoryops_ai
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
```

### Connection Manager (`services/api/app/repositories/postgres_connection.py`)
- The global `db_manager` initializes a connection pool using `asyncpg.create_pool`.
- It registers the `pgvector` handler automatically via the `init_connection` callback.
