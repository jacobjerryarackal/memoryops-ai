# Security Policy

## Supported Versions

We actively support and patch the following versions of MemoryOps AI:

| Version | Supported |
| :--- | :---: |
| v0.4.x (Phase 3 Release) | Yes |
| < v0.4.0 | No |

---

## Reporting a Vulnerability

If you discover a security vulnerability in this project, please do **not** open a public issue. Instead, report it privately to the maintainers:
*   **Email:** security@memoryops.ai
*   **Response Window:** You will receive a confirmation within 48 hours, along with a plan for remediation.

---

## Architectural Security Invariants

MemoryOps AI enforces several deterministic security constraints to prevent unauthorized data access and leaks:

### 1. Row-Level Security (RLS)
PostgreSQL storage uses row-level security policies (`tenant_user_isolation_policy`) to isolate data. Connections run under a restricted database role (`memoryops_app`) and configure session parameters dynamically.
```sql
CREATE POLICY tenant_user_isolation_policy ON memories
    USING (
        current_setting('app.bypass_rls', true) = 'true'
        OR (
            tenant_id = current_setting('app.current_tenant_id', true)
            AND tenant_id <> ''
            AND user_id = current_setting('app.current_user_id', true)
            AND user_id <> ''
        )
    );
```
Bypassing RLS requires superuser credentials or explicitly setting `app.bypass_rls = 'true'`.

### 2. Prohibited Secret Filtering
The Policy Broker runs regex checks against incoming write messages to reject API keys, credentials, and passwords before they are sent to the storage engine:
*   `openai_api_key_block`: Rejects keys matching `sk-[a-zA-Z0-9-]{48,}`.
*   `password_leakage_block`: Rejects plain text keys/passwords in chat prompts.

### 3. JWT Scope Gate
All HTTP routes under `/api/` (except public health checks) enforce token signature verification (HMAC-SHA256) and check required scopes:
*   `memory:write` for chat and write pipelines.
*   `memory:admin` for governance review queue mutations and logical deletions.
*   Scope check rules reject empty claims and restrict tenant cross-access.
