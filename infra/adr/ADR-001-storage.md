# ADR-001 — Storage Engine for Memory Records

## Status

Accepted

## Context

MemoryOps AI requires a storage architecture capable of persisting governed memory state.

Memory records are not limited to text and embeddings. The system must also maintain typed memory data, lifecycle status, tenant ownership, provenance, audit events, feedback, and operational settings.

The storage architecture must support semantic retrieval while preserving consistency between a memory and its governance state.

The system should also remain runnable and testable without requiring external infrastructure.

## Decision

Use PostgreSQL with pgvector as the canonical system of record for long-term memory and governance data.

Storage access will occur through a repository abstraction.

The initial repository implementations will be:

- `postgres` — PostgreSQL and pgvector-backed persistence.
- `memory` — in-process storage for local development and tests.

Application services must depend on the repository interface rather than a concrete storage implementation.

## Alternatives Considered

### Dedicated Vector Database

Examples include Qdrant, Pinecone, and Weaviate.

A dedicated vector database provides specialized vector search capabilities but separates embeddings from relational governance state.

This introduces synchronization concerns between memory lifecycle state and the vector index.

Rejected for the initial architecture.

### SQLite and FAISS

Provides a simple local architecture.

However, the approach provides a weaker path toward multi-tenant isolation, row-level security, and concurrent service workloads.

Rejected for the production architecture.

### PostgreSQL Without pgvector

PostgreSQL can store structured memory records and governance state.

Without pgvector, semantic similarity would need to be implemented outside the database.

Rejected because semantic retrieval is a core system requirement.

## Trade-offs

PostgreSQL and pgvector keep structured memory state and embeddings within one canonical system.

This simplifies consistency between memory lifecycle state and retrieval data.

pgvector is less specialized than a dedicated vector database for large-scale approximate nearest-neighbor workloads.

The repository abstraction introduces an additional interface layer but allows storage implementations to evolve without coupling application services to a database.

## Consequences

Database schemas and migrations will live under `infra/db/migrations`.

Repository implementations must preserve the same behavioral guarantees.

At minimum:

- tenant scope must be respected
- deleted memories must not be returned
- lifecycle state must remain consistent
- repository operations must expose predictable semantics

The in-memory repository must mirror the behavioral contract of the PostgreSQL implementation.

## Exit Strategy

If pgvector becomes a retrieval bottleneck, a dedicated vector index may be introduced behind the storage boundary.

PostgreSQL will remain the canonical system of record for memory and governance state.

Vector infrastructure may evolve without requiring the memory lifecycle services to be rewritten.