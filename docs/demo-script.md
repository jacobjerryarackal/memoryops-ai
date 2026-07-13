# Demo Script — MemoryOps AI

This document defines the canonical demonstration flow for MemoryOps AI.

The goal is to prove the governed memory lifecycle in approximately three minutes.

The demo should show that MemoryOps AI can:

1. capture useful memory
2. retrieve and use memory
3. block prohibited memory
4. bypass persistent memory
5. forget memory
6. expose governance evidence

The demo must use the real governed memory pipeline.

Mocked screenshots or manually inserted database records are not valid demonstrations of system behavior.

---

# Demo Environment

The initial demo assumes:

```text
API
http://localhost:8000
```

Default demonstration scope:

```text
tenant_id = tenant_demo
user_id   = user_demo
```

Secondary isolation scope:

```text
tenant_id = tenant_acme
user_id   = user_acme
```

The API may run using the in-memory repository for local demonstrations.

PostgreSQL is not required to prove the initial governance flow.

---

# Demo 1 — Save Useful Memory

## Goal

Prove that useful information can be extracted, governed, and persisted.

## Request

```bash
curl -s http://localhost:8000/api/chat \
  -H "content-type: application/json" \
  -d '{
    "tenant_id": "tenant_demo",
    "user_id": "user_demo",
    "message": "Remember that I prefer production-grade AI architecture explanations with clear engineering decisions.",
    "temporary_chat": false
  }'
```

## Expected Pipeline

```text
Message
   ↓
Extractor
   ↓
Procedural Memory Candidate
   ↓
Policy Broker
   ↓
SAVE
   ↓
Write Service
   ↓
Repository
   ↓
Audit Service
```

## Expected Candidate

```text
Memory Type
procedural

Content
User prefers production-grade AI architecture explanations with clear engineering decisions.

Policy Decision
SAVE
```

## Expected Evidence

The response should contain a candidate memory with:

```text
decision = SAVE
memory_id = <generated identifier>
```

An audit event should exist:

```text
memory_created
```

The memory should appear in the active memory list.

## What This Proves

```text
Extraction does not write directly.

Policy authorizes persistence.

The Write Service executes the decision.

Persistence creates governance evidence.
```

---

# Demo 2 — Retrieve and Use Memory

## Goal

Prove that active memory can influence future application context.

## Request

```bash
curl -s http://localhost:8000/api/chat \
  -H "content-type: application/json" \
  -d '{
    "tenant_id": "tenant_demo",
    "user_id": "user_demo",
    "message": "Explain how I should think about designing an AI memory system.",
    "temporary_chat": false
  }'
```

## Expected Pipeline

```text
Query
   ↓
Tenant and User Scope
   ↓
Hybrid Retriever
   ↓
Deterministic Ranker
   ↓
Context Composer
   ↓
Application Response
```

## Expected Result

The preference stored during Demo 1 should be eligible for retrieval.

The response should contain:

```text
retrieval_mode = hybrid
```

or:

```text
retrieval_mode = fallback
```

when semantic retrieval is unavailable.

The response should expose:

```text
used_memories
```

The stored procedural memory should appear in the memory usage trace when selected for context.

## Expected Evidence

The used memory should preserve:

```text
memory_id
memory_type
score
reason
score_breakdown
```

## What This Proves

```text
Memory is scoped before ranking.

Only eligible memory enters retrieval.

Memory usage remains traceable.

Retrieval can degrade safely.
```

---

# Demo 3 — Block a Secret

## Goal

Prove that deterministic policy rules can prevent prohibited information from becoming persistent memory.

## Request

```bash
curl -s http://localhost:8000/api/chat \
  -H "content-type: application/json" \
  -d '{
    "tenant_id": "tenant_demo",
    "user_id": "user_demo",
    "message": "Remember that my API key is sk-test-123456789abcdefghij.",
    "temporary_chat": false
  }'
```

## Expected Pipeline

```text
Message
   ↓
Extractor
   ↓
Candidate Memory
   ↓
Policy Broker
   ↓
Secret Detection
   ↓
BLOCK
```

The pipeline must stop before memory persistence.

## Expected Result

The candidate memory should contain:

```text
decision = BLOCK
```

No memory identifier should represent a newly persisted secret memory.

The secret must not appear in the memory list.

## Expected Evidence

An audit event should exist:

```text
memory_blocked
```

The audit event must preserve the policy reason without copying the raw secret into audit metadata.

## What This Proves

```text
Policy executes before storage.

Hard safety rules are deterministic.

An LLM cannot override secret blocking.

Blocked information does not become memory.
```

---

# Demo 4 — Temporary Memory Bypass

## Goal

Prove that an application can explicitly bypass persistent memory.

## Request

```bash
curl -s http://localhost:8000/api/chat \
  -H "content-type: application/json" \
  -d '{
    "tenant_id": "tenant_demo",
    "user_id": "user_demo",
    "message": "Remember that I prefer casual one-line answers.",
    "temporary_chat": true
  }'
```

## Expected Pipeline

```text
Temporary Chat
      │
      ├── Skip persistent retrieval
      │
      └── Skip persistent writes
```

## Expected Result

The response should contain:

```text
temporary_chat = true
retrieval_mode = none
used_memories = []
```

The temporary preference must not appear in the persistent memory list.

## Expected Evidence

The system should record:

```text
temporary_chat_skipped
```

where required by the audit or operational contract.

## What This Proves

Temporary mode bypasses both sides of the memory system:

```text
READ
and
WRITE
```

It is not merely a write-disable flag.

---

# Demo 5 — Forget Memory

## Goal

Prove the logical deletion guarantee.

## Step 1 — List Memories

```bash
curl -s \
  "http://localhost:8000/api/memories?tenant_id=tenant_demo&user_id=user_demo"
```

Identify the memory created during Demo 1.

## Step 2 — Delete the Memory

```bash
curl -s -X DELETE \
  http://localhost:8000/api/memories/<memory_id> \
  -H "content-type: application/json" \
  -d '{
    "tenant_id": "tenant_demo",
    "user_id": "user_demo"
  }'
```

## Expected Result

```text
status = deleted
deleted_at = <timestamp>
```

An audit event should exist:

```text
memory_deleted
```

## Step 3 — Ask the Same Question Again

```bash
curl -s http://localhost:8000/api/chat \
  -H "content-type: application/json" \
  -d '{
    "tenant_id": "tenant_demo",
    "user_id": "user_demo",
    "message": "Explain how I should think about designing an AI memory system.",
    "temporary_chat": false
  }'
```

## Expected Result

The deleted memory must not appear in:

```text
used_memories
```

It must not enter:

```text
semantic candidates
lexical candidates
ranking
context composition
```

## What This Proves

```text
DELETE
   ↓
Logical Forgetting
   ↓
Repository Exclusion
   ↓
No Future Context Influence
```

The demo proves logical forgetting from governed MemoryOps read paths.

It does not claim immediate physical byte erasure.

---

# Demo 6 — Inspect Governance Evidence

## Goal

Prove that memory lifecycle decisions remain inspectable.

## Audit Request

```bash
curl -s \
  "http://localhost:8000/api/audit?tenant_id=tenant_demo"
```

## Expected Events

The demonstration should expose lifecycle evidence similar to:

```text
memory_created
memory_retrieved
memory_blocked
temporary_chat_skipped
memory_deleted
```

The exact event order depends on request execution.

## Expected Audit Fields

Where applicable:

```text
tenant_id
user_id
memory_id
action
reason
metadata
created_at
```

## What This Proves

The system can answer:

```text
What happened?

Which memory was affected?

Why did the decision occur?

When did it occur?
```

Governance evidence is separate from operational telemetry.

---

# Bonus Demo — Tenant Isolation

## Goal

Prove that memory cannot cross tenant or user boundaries.

## Step 1 — Store Memory in the Secondary Scope

```bash
curl -s http://localhost:8000/api/chat \
  -H "content-type: application/json" \
  -d '{
    "tenant_id": "tenant_acme",
    "user_id": "user_acme",
    "message": "Remember that I prefer Rust for backend systems.",
    "temporary_chat": false
  }'
```

## Step 2 — Query the Primary Scope

```bash
curl -s \
  "http://localhost:8000/api/memories?tenant_id=tenant_demo&user_id=user_demo"
```

## Expected Result

The ACME memory must not appear.

## Step 3 — Ask a Related Question in the Primary Scope

```bash
curl -s http://localhost:8000/api/chat \
  -H "content-type: application/json" \
  -d '{
    "tenant_id": "tenant_demo",
    "user_id": "user_demo",
    "message": "Which backend language do I prefer?",
    "temporary_chat": false
  }'
```

## Expected Result

The `tenant_acme` memory must never appear in:

```text
candidate retrieval
ranking
used_memories
context composition
```

## What This Proves

Tenant isolation occurs before ranking.

A highly relevant cross-tenant memory is still ineligible memory.

---

# Three-Minute Demonstration Order

The recommended live demonstration sequence is:

```text
00:00 — Explain the problem

"Most AI memory systems treat memory as vector search.
MemoryOps treats memory as governed persistent state."

00:20 — Save memory

Show:
Extractor → Policy Broker → SAVE → memory_created

00:50 — Use memory

Ask a related question.
Show used_memories and the memory usage trace.

01:20 — Block a secret

Submit a fake API key.
Show BLOCK and prove no memory was created.

01:50 — Temporary chat

Submit a temporary preference.
Show no retrieval and no persistence.

02:10 — Delete memory

Delete the original preference.
Ask the same question again.
Show that the deleted memory is absent.

02:40 — Audit evidence

Open the audit stream.
Show the memory lifecycle events.

03:00 — End
```

---

# Demo Narrative

Use this explanation during the demonstration:

> Most memory systems start with embeddings and retrieval.
>
> MemoryOps AI starts one step earlier: should this information be allowed to become memory at all?
>
> The extractor can propose a memory, but it cannot persist one. Every candidate passes through a Policy Broker before the Write Service.
>
> Once memory is active, the read path retrieves only eligible memory within the correct tenant and user scope. Hybrid retrieval finds candidates, a deterministic ranker scores them, and the Context Composer preserves which memories influenced the application.
>
> Hard policy rules can block secret-like information before storage. Temporary interactions bypass both persistent reads and writes.
>
> When memory is deleted, the repository excludes it from every governed read path so it cannot influence future context.
>
> And every important lifecycle action produces governance evidence.
>
> MemoryOps AI treats memory as governed state, not just a vector database.

---

# Demo Rules

The demonstration must not claim capabilities that are not implemented.

Do not claim:

- physical byte erasure
- cryptographic deletion
- production authentication
- database Row-Level Security
- background lifecycle workers
- legal hold
- consent-aware memory
- production deployment

until those capabilities are implemented and validated.

A failed demo invariant is a system failure.

The demo must never be repaired by manually editing database state during presentation.

---

# Demo Principle

The demo is not designed to show the number of features in MemoryOps AI.

It is designed to prove six properties:

```text
Capture
Store
Retrieve
Govern
Forget
Explain
```

Every demonstration step must produce visible evidence of one or more of these properties.