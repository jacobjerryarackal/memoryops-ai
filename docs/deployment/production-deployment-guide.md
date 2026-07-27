# Production Deployment & Environment Setup Guide

This guide describes the procedures to set up the infrastructure, configure environment variables, deploy MemoryOps AI, and verify its deployment.

---

## 1. System Requirements

- **Runtime:** Python 3.11 or 3.12
- **Database Engine:** PostgreSQL 16+ with the `pgvector` extension installed.
- **Orchestration:** Docker & Docker Compose (or Kubernetes equivalent).

---

## 2. Infrastructure Setup & Database Containerization

MemoryOps AI requires a PostgreSQL instance. The recommended production starting configuration runs inside a Docker container:

```bash
# Start production-grade pgvector container
docker run -d \
  --name memoryops-postgres \
  --restart always \
  -p 5433:5432 \
  -v memoryops_data:/var/lib/postgresql/data \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  pgvector/pgvector:pg16
```

---

## 3. Environment Setup & Configuration

Configure the application by creating a `.env` file in the service root directory. Below are the mandatory configuration settings:

```env
# Database Type: 'postgres' for production, 'memory' for testing
DATABASE_TYPE=postgres

# PostgreSQL Connection Credentials
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5433
POSTGRES_DB=memoryops_ai
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres

# Connection Pool Metrics Gating
POSTGRES_MIN_POOL_SIZE=2
POSTGRES_MAX_POOL_SIZE=10
POSTGRES_CONNECTION_TIMEOUT=10.0

# Embedding Provider Configuration
OPENAI_API_KEY=sk-proj-... # Target API key
EMBEDDING_PROVIDER=openai
```

---

## 4. Deployment Steps

### Step 1: Clone and Install Dependencies
```bash
git clone https://github.com/jacobjerryarackal/memoryops-ai.git
cd memoryops-ai
pip install -r requirements.txt
```

### Step 2: Run Database Migrations
Always initialize or upgrade the database schema before starting the application:
```bash
python infra/run_migrations.py
```

### Step 3: Run the Application API Service
Start the FastAPI application using `uvicorn`:
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 5. Deployment Verification Checklist

Once the services are running, run these quick sanity checks:
- Verify `/health` endpoint returns `200 OK`:
  `curl http://localhost:8000/health`
- Verify DB schema version:
  `docker exec -it memoryops-postgres psql -U postgres -d memoryops_ai -c "SELECT * FROM schema_migrations;"`
- Validate embedding provider connectivity by querying a mock write request.
