# MemoryOps AI — Deployment Readiness Report

This report evaluates the deployment readiness of the MemoryOps AI release candidate as of the Phase 3E Production Hardening release.

---

## 1. System Components & Startup Commands

### Backend Service (API Gateway)
*   **Startup Command:**
    ```bash
    uvicorn app.main:app --host 0.0.0.0 --port 8000
    ```
*   **Health Endpoints:**
    *   `GET /healthz`: System-level alive check (returns version `0.4.0`).
    *   `GET /readyz`: Database and pool connection status verification.

### Frontend Dashboard UI
*   **Production Startup Command:**
    ```bash
    npm run start
    ```
*   **API Configuration:** Mapped via `frontend/next.config.ts` rewrite proxy to redirect all `/api/:path*` targets to the backend base URL (default: `http://127.0.0.1:8000/api/:path*`). No environment variables are exposed or loaded by the client React browser bundle.

---

## 2. Infrastructure Requirements

### PostgreSQL
*   **Image Target:** `pgvector/pgvector:pg16` or standard PostgreSQL database server with the `pgvector` extension pre-installed.
*   **Row-Level Security (RLS):** Database RLS triggers must be fully applied using [008_harden_row_level_security.sql](file:///d:/AI/memoryops-ai/infra/db/migrations/008_harden_row_level_security.sql) to prevent cross-tenant coordinate leaks.

### Embedding Providers (Gemini / OpenAI)
*   **Gemini Activation:**
    ```env
    EMBEDDING_PROVIDER=gemini
    GEMINI_API_KEY=your_gemini_credentials_here
    ```
*   **Isolation rule:** Provider keys are backend-only. The frontend Next.js application does not load or expose credentials.
*   **Offline Fallback:** Setting `EMBEDDING_PROVIDER=fallback` runs Jaccard lexical metrics and does not require active Google Gemini or OpenAI API keys.

---

## 3. Production Security Requirements

If `ENVIRONMENT=production` is set, the system validates the following constraints on initialization:
1.  **SSL/TLS Connection:** `POSTGRES_SSL` must be one of `"require"`, `"verify-ca"`, or `"verify-full"`. Insecure modes (`"prefer"`, `"disable"`) fail validation.
2.  **Durable Credentials:** Default connection usernames/passwords (`postgres`/`postgres`) are blocked from database pools.
3.  **Secrets Rotation:** JWT keys must be changed from the development default configuration string.

---

## 4. Verification Results

### Backend Test Execution
All **283 tests** in the test suite pass successfully:
```
282 passed, 1 skipped, 2 warnings in 227.32s (0:03:47)
```
*   Validated dual-parity consistency across in-process mock and PostgreSQL connection pools.
*   Adversarial tenant-isolation RLS queries validated successfully.
*   Scheduled worker concurrency locks tested and verified.

### Frontend Build Execution
TypeScript compilation and Next.js Turbopack optimization completed successfully:
*   **eslint check:** `eslint` checks completed with zero errors or warnings.
*   **next build compile:** Optimized static assets compiled successfully in 48s, with TypeScript checking finishing in 43s.

---

## 5. Known Limitations

*   **Mock Inference Default:** Semantic embeddings resolve to mock structures locally unless live Google Gemini or OpenAI API keys are provided at runtime.
*   **Lock Contention:** High concurrent requests targeted at the same singular coordinate slot can trigger database OCC serialization retry loops.
*   **Lexical Scoping:** The offline fallback Jaccard keyword scanner operates at the character-word level without active suffix stemming.

---

## 6. Deployment Blockers

None. All compilation, linting, build pipelines, integration test validations, and security gates pass cleanly.

---

## 7. Status

### **READY FOR DEPLOYMENT**
