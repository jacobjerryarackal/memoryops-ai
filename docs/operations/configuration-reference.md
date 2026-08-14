# MemoryOps AI — Configuration Reference Guide

This document is the authoritative configuration reference for the MemoryOps AI service. It covers variable bindings, data schemas, validation gates, security constraints, and offline execution rules.

---

## 1. Authoritative Configuration Matrix

| Variable | Required | Default | Allowed Values | Used By | Secret? | Description |
| :--- | :---: | :--- | :--- | :--- | :---: | :--- |
| **`ENVIRONMENT`** | No | `"development"` | `"development"`, `"testing"`, `"production"` | `config.py`, `auth.py` | No | Target runtime environment mode. Enforces security checks if `"production"`. |
| **`DATABASE_TYPE`** | No | `"memory"` | `"memory"`, `"postgres"` | `config.py`, `main.py`, `transactions.py` | No | Active database backend type. |
| **`HOST`** | No | `"127.0.0.1"` | Valid IP/hostname | `config.py`, migration runner | No | Network interface for the FastAPI gateway server to bind to. |
| **`PORT`** | No | `8000` | `1` to `65535` | `config.py` | No | Port for the FastAPI server to listen on. |
| **`POSTGRES_HOST`** | No | `"127.0.0.1"` | Valid hostname/IP | `config.py`, `postgres.py` | No | Host address of PostgreSQL server (when `DATABASE_TYPE=postgres`). |
| **`POSTGRES_PORT`** | No | `5432` | `1` to `65535` | `config.py`, `postgres.py` | No | Port of PostgreSQL server (when `DATABASE_TYPE=postgres`). |
| **`POSTGRES_DB`** | No | `"postgres"` | Database name | `config.py`, `postgres.py` | No | Database name on PostgreSQL server (when `DATABASE_TYPE=postgres`). |
| **`POSTGRES_USER`** | No | `"postgres"` | User string | `config.py`, `postgres.py` | No | Connection username (defaults are blocked in `"production"` mode). |
| **`POSTGRES_PASSWORD`** | No | `"postgres"` | Password string | `config.py`, `postgres.py` | Yes | Connection password (defaults are blocked in `"production"` mode). |
| **`POSTGRES_MIN_POOL_SIZE`** | No | `2` | Positive integer | `config.py`, `postgres_connection.py` | No | Minimum active PostgreSQL database connections in pool. |
| **`POSTGRES_MAX_POOL_SIZE`** | No | `10` | Positive integer $\ge$ MIN | `config.py`, `postgres_connection.py` | No | Maximum active PostgreSQL database connections in pool. |
| **`POSTGRES_CONNECTION_TIMEOUT`** | No | `10.0` | Positive float | `config.py`, `postgres_connection.py` | No | Timeout for acquiring database pool connection (in seconds). |
| **`POSTGRES_SSL`** | No | `"prefer"` | `"disable"`, `"prefer"`, `"require"`, `"verify-ca"`, `"verify-full"` | `config.py`, `postgres_connection.py` | No | SSL validation mode (insecure modes blocked in `"production"` mode). |
| **`JWT_SECRET`** | No | `"memoryops-jwt-secret-key-change-in-production"` | Secret string | `config.py`, `auth.py` | Yes | Secret key used to sign and verify JWT tokens. Must be rotated in prod. |
| **`JWT_ALGORITHMS`** | No | `["HS256"]` | JSON array | `config.py`, `auth.py` | No | Allowed cryptographic algorithms. Must be a valid JSON array string. |
| **`JWT_ISSUER`** | No | `"memoryops-ai"` | Issuer string | `config.py`, `auth.py` | No | Expected issuer (`iss`) claim in JWT token payloads. |
| **`JWT_AUDIENCE`** | No | `"memoryops-ai-clients"` | Audience string | `config.py`, `auth.py` | No | Expected audience (`aud`) claim in JWT token payloads. |
| **`EMBEDDING_PROVIDER`** | No | `"openai"` | `"openai"`, `"gemini"`, `"fallback"` | `embedding_factory.py` | No | Active embedding model service provider. |
| **`OPENAI_API_KEY`** | Conditional | None | Valid API key (`sk-...`) | `openai_embedding.py` | Yes | Key for OpenAI embeddings (Required only if `EMBEDDING_PROVIDER=openai`). |
| **`GEMINI_API_KEY`** | Conditional | None | Gemini key string | `gemini_embedding.py` | Yes | Key for Google Gemini embeddings (Required only if `EMBEDDING_PROVIDER=gemini`). |

---

## 2. Parsing Deep-Dives & Constraints

### A. Strict JWT_ALGORITHMS Parsing
*   **Validation Behavior:** `JWT_ALGORITHMS` is parsed into a Python `list` via Pydantic Settings.
*   **Allowed Format:** **Must be a valid JSON list** (e.g. `["HS256"]` or `["HS256", "RS256"]`).
*   **Rejection Case:** Providing a plain comma-separated string (e.g. `HS256,RS256`) will throw a `ValidationError` during settings load and fail application startup.

### B. Embedding Provider Selection & API Key Requirements
*   **Fallback Mode:** If `EMBEDDING_PROVIDER=fallback` is set, the system uses Jaccard similarity metrics over offline lexical mocks. Under this configuration, **neither `OPENAI_API_KEY` nor `GEMINI_API_KEY` is required**, allowing zero-key local offline development.
*   **OpenAI Mode:** When `EMBEDDING_PROVIDER=openai` (the system default), a valid `OPENAI_API_KEY` must be configured.
*   **Gemini Mode:** When `EMBEDDING_PROVIDER=gemini`, a valid `GEMINI_API_KEY` must be configured.

### C. Production Security Enforcements
If `ENVIRONMENT=production` is set, Pydantic validators execute the following security rules on initialization:
1.  **SSL Requirement:** `POSTGRES_SSL` must be one of `"require"`, `"verify-ca"`, or `"verify-full"`. Settings of `"prefer"` or `"disable"` throw validation failures.
2.  **Default Credentials Rejection:** Mismatches against default PostgreSQL user/password parameters are strictly enforced. If `POSTGRES_USER` resolves to `"postgres"` or `POSTGRES_PASSWORD` resolves to `"postgres"`, startup fails immediately.

---

## 3. Zero-Key Offline Quickstart Config

For local fast development without external model keys or Docker containers, copy this configuration block to your `.env` file:

```env
ENVIRONMENT=development
DATABASE_TYPE=memory
EMBEDDING_PROVIDER=fallback
PORT=8000
HOST=127.0.0.1
```
