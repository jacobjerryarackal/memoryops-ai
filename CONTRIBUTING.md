# Contributing to MemoryOps AI

We welcome contributions to MemoryOps. Please follow this guide to set up your local development environment, run validation checks, and verify changes.

---

## Developer Setup

### 1. Prerequisites
*   Python 3.11+
*   Docker & Docker Compose (for PostgreSQL/pgvector storage)

### 2. Environment Setup
Clone the repository and install all dependencies:
```bash
git clone https://github.com/jacobjerryarackal/memoryops-ai.git
cd memoryops-ai
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

Set up your environment variables:
```bash
cp .env.example .env
# Edit .env to add keys or customize ports
```

---

## Database Operations

### 1. Startup Container
```bash
docker compose up -d
```

### 2. Run Migrations
Whenever database schemas change or when setting up the database from scratch:
```bash
python infra/db/run_migrations.py
```

---

## Quality & Verification Gates

Before submitting any code changes, verify your code against the validation suite:

### 1. Run Tests
Ensure all unit and integration tests pass:
```bash
python -m pytest
```
Alternatively, use the Makefile target:
```bash
make test
```

### 2. Lint and Format Checks
Verify coding standards:
```bash
make verify
```

### 3. Run Evaluations & Benchmarks
Run the evaluation suite against the golden dataset:
```bash
make evaluate
```
Run the performance benchmark suite:
```bash
make benchmark
```

---

## Development Workflow: Phase Gates

We enforce a dual-layer quality gate process described in `docs/phase-gates/README.md`.
1.  **Phase Gate Checklist:** Run `pytest` to establish the baseline before making changes.
2.  **Bounded Implementation:** Keep edits focused and do not introduce out-of-scope abstractions.
3.  **Architecture Review:** Verify that database migrations, schemas, and RLS rules are aligned.
4.  **Regression Gate:** Regenerate local metrics and document the changes in the release report.
