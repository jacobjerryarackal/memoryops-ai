# ADR-002 — Hybrid Retrieval and Deterministic Ranking

## Status

Accepted

## Context

MemoryOps AI must retrieve the memories most relevant to an application request.

Semantic similarity alone is insufficient for exact names, identifiers, and phrases.

Keyword retrieval alone cannot reliably identify paraphrases or semantically related memories.

Retrieval must also respect memory governance boundaries before memories are considered for ranking.

The initial retrieval architecture should remain explainable, measurable, and capable of degrading safely when memory retrieval is unavailable.

## Decision

Use hybrid retrieval combining semantic similarity and lexical matching.

Candidate memories will be ranked using a deterministic weighted scoring model.

The initial ranking model is:

    final_score =
        0.35 * semantic_score
      + 0.20 * keyword_score
      + 0.15 * importance_score
      + 0.10 * recency_score
      + 0.10 * confidence_score
      + 0.10 * reinforcement_score

Before ranking, candidate memories must be filtered by:

- tenant scope
- user scope
- active lifecycle status
- sensitivity and permission rules

Only eligible memories may enter the ranking pipeline.

The highest-ranked memories will be passed to a Context Composer.

The Context Composer must preserve source memory identifiers so downstream applications can identify which memories contributed to generated context.

Retrieval failures must degrade gracefully. Failure of the memory subsystem must not automatically prevent the application from producing a non-memory response.

## Alternatives Considered

### Vector-Only Retrieval

Simple and semantically aware.

Rejected because exact names, identifiers, and phrases may receive poor recall.

### Keyword-Only Retrieval

Provides strong exact-match behavior.

Rejected because it cannot reliably retrieve semantic paraphrases.

### Learned Reranker

A cross-encoder or LLM-based reranker may improve ranking quality.

Rejected for the initial architecture because it introduces additional latency, cost, and operational complexity.

A learned reranker may be introduced later behind the ranking interface.

## Trade-offs

Fixed ranking weights are transparent and easy to inspect.

However, they are manually selected rather than learned from user behavior.

Hybrid retrieval requires both semantic and lexical candidate signals, introducing additional retrieval work.

The additional complexity is accepted in exchange for improved recall and explainability.

## Consequences

The retrieval architecture will introduce the following responsibilities:

- Retriever
- Ranker
- Context Composer

The Retriever produces eligible candidate memories.

The Ranker produces a final score and score breakdown for each candidate.

The Context Composer selects and formats top-ranked memories for downstream applications.

Retrieval components must remain isolated behind interfaces so ranking strategies may evolve independently.

## Invariants

The retrieval system must preserve the following guarantees:

1. Cross-tenant memories must never enter the ranking pipeline.
2. Deleted or inactive memories must never be returned.
3. Permission-restricted memories must be filtered before ranking.
4. Retrieval failure must degrade safely.
5. Memory usage must remain traceable to source memory identifiers.

## Exit Strategy

The deterministic ranker may later be replaced by a learned reranker behind the same ranking interface.

Ranking weights should first be tuned using memory feedback and evaluation results before introducing additional models.