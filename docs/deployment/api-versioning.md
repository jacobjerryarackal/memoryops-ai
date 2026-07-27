# API Versioning Policy

MemoryOps AI adopts a strict versioning strategy to ensure API contract compatibility, developer ease of integration, and seamless zero-downtime blue-green deployments.

---

## 1. Versioning Standards

### API URL Structure
All external REST API endpoints must include the major version prefix in the URL path:
`http://localhost:8000/api/v{major_version}/`

Example for Version 1:
- `POST /api/v1/memories`
- `GET /api/v1/memories/{memory_id}`

---

## 2. Backward Compatibility Guidelines

We classify changes to public API schemas according to Semantic Versioning principles:

### Compatible Changes (Patch / Minor Release)
These changes do not break existing clients and can be rolled out without version updates:
- Adding a new optional request field.
- Adding a new field to a response body.
- Adding a brand new API endpoint route.

### Breaking Changes (Major Release Required)
These changes disrupt existing integrations and require incrementing the major version (e.g., from `/api/v1/` to `/api/v2/`):
- Removing or renaming an existing endpoint parameter.
- Changing an existing field type (e.g., changing string to integer).
- Removing an endpoint route.
- Changing mandatory validation rules (e.g., making a previously optional field required).

---

## 3. Deprecation Cycle Policy

When an API endpoint must be retired or replaced:
1. **Deprecation Notice (Phase 1):** The endpoint continues to work but returns a deprecation warning HTTP header:
   `Warning: 299 - "Deprecated API. Will be removed in v(X+1)"`
2. **Grace Period (Phase 2):** Deprecated API endpoints are maintained for at least **two minor releases** before removal.
3. **Removal (Phase 3):** The endpoint is decommissioned in the next major version release.

---

## 4. Zero-Downtime Migration Policy

All database migrations must be designed for compatibility with two active application versions (the currently running version and the newly deploying version):
- **Rule 1:** Never rename a database column directly. Instead, add a new column, double-write to both, copy historical data, and then drop the old column.
- **Rule 2:** All database columns introduced in a migration must be either nullable or have a defined default value to prevent breaking older application versions.
