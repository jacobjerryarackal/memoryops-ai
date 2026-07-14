# Retrieval Spine

## 1. Status and Scope

**Status:** `LOCKED` (Phase 2 MVP Design Spine)

This document serves as the implementation blueprint and contract specification for the Phase 2 Retrieval and Context Composition read path in MemoryOps AI. It governs the internal read-path pipeline, data models, tokenization rules, score ranking parameters, tie-breaking behavior, context budgets, and serialization schemas for the Phase 2 MVP. 

It does not govern write-path admissions, migrations, pgvector index creations, background compaction workers, or final answer evaluations.

---

## 2. Authoritative Inputs

The design spine is constrained by the following authoritative documents in order of precedence:
1. **Local System Overview:** [system-overview.md](file:///d:/AI/memoryops-ai/docs/architecture/system-overview.md)
2. **Local API Contracts:** [api-contracts.md](file:///d:/AI/memoryops-ai/docs/api-contracts.md) (specifically used memory response fields and weights)
3. **Local ADRs:**
   * [ADR-002-retrieval.md](file:///d:/AI/memoryops-ai/infra/adr/ADR-002-retrieval.md) (ranking signals and weights)
   * [ADR-004-observability.md](file:///d:/AI/memoryops-ai/infra/adr/ADR-004-observability.md) (telemetry and spans)
   * [ADR-005-deletion-guarantee.md](file:///d:/AI/memoryops-ai/infra/adr/ADR-005-deletion-guarantee.md) (logical active-only query boundaries)
   * [ADR-006-memory-identity-and-write-path-mutation.md](file:///d:/AI/memoryops-ai/infra/adr/ADR-006-memory-identity-and-write-path-mutation.md) (embedding invalidation invariants)
4. **Reference Repository (Comparative Evidence):** `patibandlavenkatamanideep/memoryops-ai` source files, specifically [retriever.py](file:///d:/AI/memoryops-ai/tmp_manideep/services/api/app/services/retriever.py) and [ranker.py](file:///d:/AI/memoryops-ai/tmp_manideep/services/api/app/services/ranker.py). Manideep is comparative evidence only; local specifications remain authoritative.

---

## 3. Locked Retrieval Pipeline

The Phase 2 MVP read path operates as a single-candidate-pool pipeline. There are no duplicate candidate union or collapse stages, and no independent full-text search database queries are executed.

```
Incoming Query (Message)
  │
  ▼
[Retrieval Coordinator] ──(Generates query embedding)
  │
  ▼
[Retriever] ──(Queries active DB rows; computes keyword counts in Python)
  │
  ▼
[Deterministic Ranker] ──(Normalizes signals; applies weights; deterministically sorts)
  │
  ▼
[Context Composer] ──(Applies budget; filters; formats context; serializes UsedMemory)
```

### 1. Retrieval Coordinator
* **Responsibility:** Coordinates the turn's read flow, calls the embedding generator, retriever, ranker, and composer, and sets up trace spans.
* **Input Concept:** `tenant_id`, `user_id`, `message` (query string), `trace_id`, `retrieval_mode`.
* **Output Concept:** Prompt context string and serializable list of `UsedMemory` records.
* **Exclusions:** Excludes database querying, scoring, and text formatting.

### 2. Retriever
* **Responsibility:** Fetches a bounded pool of active memories from the repository. Calculates raw lexical keyword match statistics in memory in Python.
* **Input Concept:** `tenant_id`, `user_id`, `query_text`, `query_embedding`.
* **Output Concept:** List of candidates containing the `MemoryRecord`, `cosine_similarity` (or `None`), `matched_query_terms`, and `total_unique_query_terms`.
* **Exclusions:** Excludes final scoring, sorting, and context budgeting.

### 3. Deterministic Ranker
* **Responsibility:** Evaluates normalized scores for the 6 signals and computes the final weighted ranking score.
* **Input Concept:** List of candidates from the Retriever, time `now`.
* **Output Concept:** Sorted list of `RankedCandidate` records.
* **Exclusions:** Excludes scope verification, token budgets, and text formatting.

### 4. Context Composer
* **Responsibility:** Limits ranked memories to budget, formats them as plain Markdown bullets, and serializes `UsedMemory` schemas.
* **Input Concept:** List of `RankedCandidate` records, context budget constraints.
* **Output Concept:** Formatted context string and list of `UsedMemory` records.
* **Exclusions:** Excludes scoring and sorting.

---

## 4. Retrieval Eligibility Invariant

The active-memory retrieval boundary strictly enforces:
* `record.tenant_id == tenant_id`
* `record.user_id == user_id`
* `record.status == MemoryStatus.ACTIVE`

Any records with status `PENDING`, `REJECTED`, `ARCHIVED`, or `DELETED` are structurally excluded from retrieval queries. 

### Deletion Implications
Soft-deleted records (`status == 'deleted'`) are excluded at the repository query layer. The Retriever defensively validates that all incoming database rows satisfy the scope and active invariants, dropping any violating records before they reach the Ranker.

---

## 5. Lexical Evidence Contract

### Query Normalization
A raw query string is normalized using the following sequential pipeline:
1. **Unicode Normalization:** NFKC compatibility normalization.
2. **Case Normalization:** Case folded to lowercase (`.lower()`).
3. **Punctuation Cleaning:** Replace all non-alphanumeric characters with spaces.
4. **Tokenization:** Split by whitespace. Remove empty tokens.
5. **Stopwords:** Preserved (no stopword filtering is applied).
6. **Stemming/Lemmatization:** Preserved (no suffix-stripping is applied).

### Memory Normalization
The `MemoryRecord.content` is normalized using the identical query normalization pipeline.

### Unique Query Terms (`total_unique_query_terms`)
Uniqueness is applied to the list of normalized query tokens.
$$\text{total\_unique\_query\_terms} = |\text{set}(Q)|$$

### Matched Query Terms (`matched_query_terms`)
The count of unique normalized query terms that appear as exact matches in the unique set of normalized memory content tokens.
$$\text{matched\_query\_terms} = |\text{set}(Q) \cap \text{set}(M)|$$

### Lexical Scoring Formula
The keyword score is calculated as:
$$\text{keyword\_score} = \frac{\text{matched\_query\_terms}}{\max(\text{total\_unique\_query\_terms}, 1)}$$

### Lexical Examples

> [!NOTE]
> All examples below represent *Phase 2 Design Clarifications* locking lexical matching rules.

#### Example 1 (Standard Match)
* **Query:** `"Python engineer"`
* **Memory:** `"Jacob is a Python engineer."`
* **Normalized Q:** `{"python", "engineer"}`
* **Normalized M:** `{"jacob", "is", "a", "python", "engineer"}`
* **Intersection:** `{"python", "engineer"}`
* **Stats:** `matched = 2`, `total_unique = 2`, `keyword_score = 1.0`

#### Example 2 (Casing and Duplication)
* **Query:** `"python PYTHON engineer"`
* **Memory:** `"Jacob works as an engineer using Python."`
* **Normalized Q:** `{"python", "engineer"}`
* **Normalized M:** `{"jacob", "works", "as", "an", "engineer", "using", "python"}`
* **Intersection:** `{"python", "engineer"}`
* **Stats:** `matched = 2`, `total_unique = 2`, `keyword_score = 1.0`

#### Example 3 (Punctuation Splitting)
* **Query:** `"AI-engineer"`
* **Memory:** `"Jacob is an AI engineer."`
* **Normalized Q:** `{"ai", "engineer"}`
* **Normalized M:** `{"jacob", "is", "an", "ai", "engineer"}`
* **Intersection:** `{"ai", "engineer"}`
* **Stats:** `matched = 2`, `total_unique = 2`, `keyword_score = 1.0`

#### Example 4 (No Stemming Match)
* **Query:** `"What is my preferred language?"`
* **Memory:** `"Jacob prefers Python."`
* **Normalized Q:** `{"what", "is", "my", "preferred", "language"}`
* **Normalized M:** `{"jacob", "prefers", "python"}`
* **Intersection:** `{}` (empty; `"preferred"` does not equal `"prefers"`)
* **Stats:** `matched = 0`, `total_unique = 5`, `keyword_score = 0.0`

#### Example 5 (Non-ASCII Characters)
* **Query:** `"München café"`
* **Memory:** `"Café in München."`
* **Normalized Q:** `{"münchen", "café"}`
* **Normalized M:** `{"café", "in", "münchen"}`
* **Intersection:** `{"münchen", "café"}`
* **Stats:** `matched = 2`, `total_unique = 2`, `keyword_score = 1.0`

---

## 6. Semantic Fallback Contract

* **Bypassed / Disabled Retrieval:** If the request gateway sets `temporary_chat = True`, the read loop is bypassed, returning `retrieval_mode = "none"` with empty context and empty `used_memories`.
* **Embedding Failure Fallback:** If query embedding generation raises an exception, the coordinator logs a fallback warning, sets `query_embedding = []`, and falls back to active-memory retrieval.
* **Retrieval Mode Outcome:**
  * Normal run: `retrieval_mode = "hybrid"`.
  * Degraded run: `retrieval_mode = "fallback"`.
* **Signal values in Fallback:**
  * When `query_embedding` is empty, candidates are retrieved based on active status, and `cosine_similarity` defaults to `0.0`, resulting in `semantic_score = 0.0`.
  * The fixed ranking weights (`0.35` semantic, etc.) remain unchanged. No weight redistribution occurs.

---

## 7. Deterministic Ranking Contract

### Normalized Signals
* `semantic_score = clamp(cosine_similarity, 0.0, 1.0)`
* `keyword_score = matched_query_terms / max(total_unique_query_terms, 1)`
* `importance_score = importance / 10`
* `confidence_score = clamp(confidence, 0.0, 1.0)`
* `recency_score = exp(-age_days / 30)` (decay from `updated_at` to request time `now`)
* `reinforcement_score = 1 - exp(-reinforcement_count / 5)`

### Weights
$$\text{final\_score} = 0.35 \times s_{\text{semantic}} + 0.20 \times s_{\text{keyword}} + 0.15 \times s_{\text{importance}} + 0.10 \times s_{\text{recency}} + 0.10 \times s_{\text{confidence}} + 0.10 \times s_{\text{reinforcement}}$$

### Deterministic Tie-Breaking (Phase 2 Design Clarification)
If two candidates achieve the identical `final_score`, ties are broken using the following strict sorting keys in order:
1. `final_score` DESC (primary score)
2. `created_at` DESC (secondary key: favoring newer records by original creation time)
3. `id` ASC (tertiary key: lexicographical sort of UUID string to guarantee stable, database-independent results)

#### Rationale
Using `created_at` instead of `updated_at` as the secondary sorting key prevents double-counting recency for updated items, since the Ranker's primary score already evaluates recency based on `updated_at`. Using `id ASC` ensures identical candidate sets always sort identically. Tie-breaking does not alter `final_score`.

---

## 8. Ranked Candidate Boundary

The following information must survive the Ranker and enter downstream stages:
* **Memory State:** The `MemoryRecord` instance (for content and metadata verification).
* **Final Score:** `final_score: float` (rounded to 4 decimal places).
* **Score Breakdown:** Pydantic model containing the 6 normalized float scores.
* **Rank Position:** `rank: int` (1-indexed order position).

`RankedCandidate` does not contain a natural language relevance reason.

---

## 9. Context Selection Contract

### Budgets (Phase 2 Design Clarification)
Context selection restricts prompt injection size using a dual-bound budget:
* `max_memories = 10` (maximum memories allowed).
* `max_characters = 4000` (maximum cumulative character count of selected memory content).

Character count is selected as the budget unit to remain provider-independent and avoid importing tokenizer library dependencies.

### Selection Ordering
Candidates are consumed strictly in rank order (`RankedCandidate` sorted by `final_score DESC` then tie-breakers).

### Oversized Memory Behavior
If adding the next ranked memory would cause the cumulative character count to exceed `max_characters`, that memory is **skipped**, and selection continues to subsequent lower-ranked memories to see if a smaller one fits the remaining budget. No memory content truncation is performed, as truncating content changes natural language meaning.

### Empty Selection
If no candidates fit within the character budget, or the candidate list is empty, context selection returns an empty list, resulting in empty context `""` and `used_memories = []`.

### Context Examples

#### Case 1 (Under Budget)
* `max_memories = 3`, `max_characters = 500`. Candidates: 2 records (lengths: 100, 150 characters).
* **Selection:** Record 1 (100 char), Record 2 (150 char) admitted.
* **Result:** 2 memories selected.

#### Case 2 (Count Limit Reached)
* `max_memories = 2`, `max_characters = 500`. Candidates: 3 records (lengths: 100, 100, 100 characters).
* **Selection:** Top 2 records admitted. Record 3 is ignored due to count limit.
* **Result:** 2 memories selected.

#### Case 3 (Character Bound Skip)
* `max_memories = 5`, `max_characters = 150`. Candidates:
  * Rank 1 (100 char): selected (remaining = 50)
  * Rank 2 (80 char): skipped (exceeds 50)
  * Rank 3 (40 char): selected (remaining = 10)
* **Result:** Rank 1 and Rank 3 selected. Rank 2 omitted.

#### Case 4 (Oversized Skip)
* `max_characters = 50`. Candidates: Rank 1 (120 char).
* **Selection:** Rank 1 skipped entirely.
* **Result:** Empty context.

---

## 10. Context Composition Contract

The Context Composer formats the selected list of memory records into a single text block for LLM context injection.
* **Formatting:** Markdown bulleted list where each line is prefixed by its memory type:
  `"- ({memory_type.value}) {content}"`
* **Exclusions:** Memory UUIDs, scores, reasons, or source excerpts are **never** injected into the model context block.

---

## 11. `used_memories` Contract

The public API contract requires returning `used_memories[]` in the chat response. 
* **Semantic Definition:** `used_memories` represents exactly the list of memories that were selected and injected into the context block.
* **Reason Field (Phase 2 Design Clarification):** The Context Composer generates a deterministic string for `UsedMemory.reason` based on the dominant ranking signal:
  * If `0.35 * semantic_score > 0.20 * keyword_score` (and semantic is not 0):
    `reason = f"Selected (Rank #{rank}): Semantically relevant to the query (Score: {final_score:.2f})."`
  * If `0.20 * keyword_score > 0.35 * semantic_score` (and keyword is not 0):
    `reason = f"Selected (Rank #{rank}): Lexically relevant to the query (Score: {final_score:.2f})."`
  * If signals are equal or in fallback/none mode:
    `reason = f"Selected (Rank #{rank}): Balanced relevance context (Score: {final_score:.2f})."`

### Reason Examples

#### Case 1 (Semantic-Dominant)
* Rank = 1, final_score = 0.85, semantic = 0.9, keyword = 0.5.
* **Reason:** `"Selected (Rank #1): Semantically relevant to the query (Score: 0.85)."`

#### Case 2 (Keyword-Dominant)
* Rank = 2, final_score = 0.62, semantic = 0.3, keyword = 0.9.
* **Reason:** `"Selected (Rank #2): Lexically relevant to the query (Score: 0.62)."`

#### Case 3 (Fallback Mode)
* Rank = 1, final_score = 0.42, semantic = 0.0, keyword = 0.8.
* **Reason:** `"Selected (Rank #1): Balanced relevance context (Score: 0.42)."`

#### Case 4 (Balanced Contribution)
* Rank = 3, final_score = 0.60, semantic = 0.6, keyword = 0.6.
* **Reason:** `"Selected (Rank #3): Balanced relevance context (Score: 0.60)."`

---

## 12. Retrieval Mode Contract

* **hybrid:** Semantic query embedding succeeded and cosine similarity search was executed alongside lexical matching.
* **fallback:** Semantic query embedding failed and retrieval degraded to lexical matching over active candidate records.
* **none:** Retrieval was bypassed (e.g., `temporary_chat = True`) or no retrieval path was executed.

---

## 13. Telemetry Compatibility Boundary

The read path will expose the following metadata structure to the structured operational logger (separately from audit trails):
* `trace_id`
* `retrieval_mode` (executed mode)
* `candidate_count` (number of records returned by the repository query)
* `selected_memory_ids` (list of UUIDs actually injected into context)
* `score_breakdown` (scores and breakdown dictionary of selected candidates)
* `latency_ms` (individual span durations of retrieve, rank, and compose)

No retrieval events are added to the governance `AuditEventAction` enum or write to `memory_audit_logs`.

---

## 14. Explicit Non-Goals

The following items are out of scope for the Phase 2 MVP and must not be implemented:
* **BM25 or tf-idf term weights**
* **PostgreSQL GIN indexes or full-text query schemas**
* **An independent database-level lexical candidate query**
* **A candidate union collapse stage**
* **Generic AdmissionGate or RecallGate classes**
* **LLM-generated retrieval reasons**
* **Post-generation answer attribution mechanisms**
* **Database persistence of retrieval traces**

---

## 15. Implementation Dependencies

To implement this design, Phase 2 will proceed in the following dependency order:
1. **Step 4 — Read-Path Domain Contracts:** Add Pydantic schemas for `UsedMemory`, `ScoreBreakdown`, `RankedCandidate`, and read-path interfaces to `domain/`.
2. **Step 5 — Candidate Repository Contract:** Extend `MemoryRepository` and `InMemoryMemoryRepository` with the `search_candidates` query interface (returning active records and cosine similarity).
3. **Step 6 — Retriever & Ranker Implementation:** Implement the Python classes for the Retriever (including Python keyword counts) and Ranker (ranking math and tie-breakers).
4. **Step 7 — Context Selection & Composition:** Implement the Context Composer (character budgets and Markdown formatting).
5. **Step 8 — Gateway Integration:** Wire the read path into the gateway `/api/chat` endpoint and verify the API response contract.
