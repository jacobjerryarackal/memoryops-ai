# MemoryOps AI — Test Evidence Matrix

This matrix catalogs the validation boundaries, execution environments, and mock levels for every test file in the MemoryOps AI repository.

| Test File | Layer | Real Infrastructure? | Mocked Dependencies? | Security Boundary? | Regression Value |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `test_admission_layer.py` | Read / Retrieval | None (In-Memory) | Yes (`DummyMemoryRepository`, `DummyEmbeddingService`) | No (Simulates policy execution only) | High (Protects context-composition filtering logic) |
| `test_audit_service.py` | Governance / Audit | None (In-Memory) | Yes (`InMemoryAuditService`) | No | High (Ensures audit log deep copy & basic append logic) |
| `test_auth_gate.py` | API Gateway / Auth | None (In-Memory) | Yes (`MockBearerAuthService` overrides token format) | **Yes** (Validates token parsing, scopes, & admin checks) | High (Validates request-principal mapping logic) |
| `test_config.py` | Initialization | None (In-Memory) | Yes (Mocks environment variables via monkeypatch) | **Yes** (Validates production SSL and credential rejection) | High (Fail-fast validation for configuration) |
| `test_domain_models.py` | Domain Models | None (In-Memory) | None (Pure Pydantic schema validation) | No | Medium (Ensures Pydantic object constraints) |
| `test_embedding.py` <br> `test_embedding_fallback.py` <br> `test_embedding_providers.py` <br> `test_openai_embedding.py` | Embedding API | None (In-Memory) | Yes (Mocks HTTP calls via `httpx.MockTransport`) | No | High (Ensures request/response parsing for Gemini & OpenAI) |
| `test_evaluation_metrics.py` | Evaluation Engine | None (In-Memory) | None (Pure math helpers validation) | No | Medium (Protects NDCG, Recall, Precision metrics formula) |
| `test_gateway.py` | API Gateway / Routing | None (In-Memory) | Yes (FastAPI dependency overrides; mocks database & embedding) | No | High (Validates API routes, request schemas, & defaults) |
| `test_governance_api.py` | API Gateway / Governance | None (In-Memory) | Yes (Runs against process-lifetime in-memory `_shared_repository`) | No (Authentication gates are completely absent from routing) | High (Ensures routes trigger correct service errors) |
| `test_governance_service.py` | Governance Service | None (In-Memory) | Yes (InMemory repositories) | No (Validates logical transitions but no security gates) | High (Verifies state transition logic and legal hold gating) |
| `test_idempotency.py` | API Gateway / Idempotency | None (In-Memory) | Yes (Uses in-memory fallback cache to bypass database) | No | High (Verifies trace ID reuse in HTTP requests) |
| `test_lifecycle_behaviors.py` <br> `test_lifecycle_infrastructure.py` | Lifecycle Worker Logic | **Dual** (PostgreSQL in integration mode, else In-Memory) | Mocks in memory-mode; real DB in postgres-mode | No | High (Tests worker logic: retention, decay, reflection, compaction) |
| `test_negative_controls.py` | Evaluation Engine | None (In-Memory) | None (Uses dummy lists to verify metric output) | No | High (Ensures metric calculations trigger failures on leakages) |
| `test_observability.py` | Observability | **Dual** (PostgreSQL in integration mode, else In-Memory) | Mocks exporters via `test_mode` (collects events in array) | No | High (Ensures span and metrics trace propagation) |
| `test_policy.py` | Policy Broker | None (In-Memory) | None | **Yes** (Validates credential/secret-blocking policies) | High (Ensures secrets sk- and passwords are blocked) |
| `test_postgres_repository.py` | Storage / DB | **Yes** (Real PostgreSQL on port 5433) | None | No (Connects as owner/superuser `postgres` by default) | High (Verifies database schemas, unique keys, and updates) |
| `test_repository.py` | Storage / Memory DB | None (In-Memory) | None | No | High (Ensures in-memory database holds rules) |
| `test_retrieval_domain.py` <br> `test_retrieval_services.py` <br> `test_retrieval_telemetry.py` | Read / Retrieval | **Dual** (PostgreSQL in integration mode, else In-Memory) | Yes (Mocks embedding generator) | No | High (Ensures hybrid retrieval ranking, score tie-breaker) |
| `test_rls_adversarial.py` | Database Security | **Yes** (Real PostgreSQL on port 5433) | None | **Yes** (Asserts RLS isolation using non-superuser role) | High (Only test validating database RLS tenant boundaries) |
| `test_sdk.py` | Client SDK | None (In-Memory) | Yes (Mocks requests library calls via unittest patch) | No | High (Checks URL/header/payload structure assembly) |
| `test_transaction_rollback.py` <br> `test_transactions.py` | Storage Transactions | **Dual** (PostgreSQL in integration mode, else In-Memory) | None in PostgreSQL mode; mocks via snapshotting in-memory | No | High (Asserts transaction boundary commits and rollbacks) |
| `test_write_policies.py` <br> `test_write_service.py` | Write Path Service | **Dual** (PostgreSQL in integration mode, else In-Memory) | Mocks broker outcomes | No | High (Validates write-path outcomes and save/update/block actions) |
