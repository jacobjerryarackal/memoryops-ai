# Known Design & Operational Limitations

This document lists the verified architectural limitations and boundaries of the MemoryOps AI system.

---

## 1. Mocked LLM Answer Generation
MemoryOps AI is designed as a **memory operating system and control plane**, not a general-purpose chatbot. 
*   **Limitation:** While the `/api/chat` endpoint handles the complete RAG loop (retrieval -> context composition -> write candidate extraction), actual conversational text responses are determined by mocked/placeholder logic unless integrated with an external agent orchestration framework.
*   **Design Rationale:** This separates the deterministic state governance (rules, validation, audit logs) from probabilistic model inference.

---

## 2. Lexical Fallback Quality
When the embedding provider (Gemini or OpenAI) is unavailable or times out, the Retrieval Coordinator degrades gracefully by falling back to lexical search.
*   **Limitation:** Lexical search uses word overlap metrics (Jaccard similarity). It does **not** understand semantic synonyms. Retrieval precision and recall may drop significantly during fallback periods.

---

## 3. Optimistic Concurrency Control (OCC) Bounds
Memory mutations are protected by a Pydantic and database-level `version` check.
*   **Limitation:** If two concurrent transactions attempt to write or mutate the same memory record, one will succeed and the other will raise a `ValueError` (concurrency mismatch). The system does not automatically queue or retry concurrent mutations; it delegates retries to the calling client (or SDK).

---

## 4. Legal Holds and Physical Deletion
A legal hold on a memory record prevents both logical deletion (via `/api/memories/{id}`) and background worker compaction.
*   **Limitation:** A legal hold is enforced programmatically in the application layer and through RLS/constraints. It cannot prevent superusers (admins with direct DB credentials) from performing raw SQL deletions.

---

## 5. Strict Tenant Isolation
Row-level security policies (`tenant_user_isolation_policy`) prevent all cross-tenant sharing.
*   **Limitation:** There is no mechanism to share global memories (e.g., system-wide knowledge bases) across tenants at the database level. Each tenant is strictly siloed.
