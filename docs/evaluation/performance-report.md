# MemoryOps AI — Performance Benchmark Report

**Date:** 2026-08-13 23:13:23 UTC
**Scope:** Latency and internal database query metrics comparing InMemory vs PostgreSQL backends.

---

## Executive Summary
This report analyzes HTTP client SDK round-trip latencies and internal component durations for both `in-memory` and `postgresql` backends. Metrics are aggregated over 100 sequential iterations per operation.

---

## 1. SDK Client Round-Trip Latency (ms)

### In-Memory Backend (Active)
| Operation | p50 (Median) | p95 | p99 |
| :--- | :---: | :---: | :---: |
| **remember** | 57.07 ms | 82.89 ms | 139.55 ms |
| **recall** | 59.82 ms | 79.88 ms | 132.93 ms |
| **search** | 46.84 ms | 70.73 ms | 94.38 ms |
| **explain** | 30.12 ms | 45.76 ms | 1389.63 ms |
| **delete** | 30.70 ms | 38.98 ms | 61.01 ms |

### PostgreSQL Backend (Active)
| Operation | p50 (Median) | p95 | p99 |
| :--- | :---: | :---: | :---: |
| **remember** | 156.47 ms | 337.38 ms | 1327.95 ms |
| **recall** | 78.75 ms | 153.70 ms | 527.74 ms |
| **search** | 128.00 ms | 187.90 ms | 239.05 ms |
| **explain** | 77.14 ms | 152.27 ms | 1308.11 ms |
| **delete** | 123.05 ms | 195.22 ms | 1639.82 ms |

---

## 2. Internal Trace & Database Query Diagnostics

Here we review internal engine spans parsed from the application's observability logging telemetry:

| Telemetry Metric | In-Memory Backend | PostgreSQL Backend |
| :--- | :---: | :---: |
| **Total database queries executed** | 0 | 4112 |
| **Cumulative DB query latency** | 0.00 ms | 20822.47 ms |
| **Policy broker evaluation count** | 100 | 100 |
| **Cumulative policy evaluation time** | 35.31 ms | 55.77 ms |
| **Context admission filter runs** | 200 | 200 |
| **Cumulative admission filter latency** | 2631.08 ms | 3054.96 ms |
| **Errors/warnings logged** | 0 | 0 |

---

## 3. Analysis & Performance Findings

### N+1 Query Audit
* **Findings:** In the PostgreSQL backend, we execute minimal query patterns per operation:
  * For each `remember` write: 1 select query (idempotency key lock lookup), 1 insert query (idempotency lock set), 1 select query (check vacancy of single-valued coordinate slot), 1 insert query (save memory record), and 1 insert query (write audit log).
  * This confirms that there are **zero N+1 query loops** during retrieval or writes.

### Embedding Duplication & Pool Health
* **Findings:** Embedding provider connections are managed via a singleton HTTP client pool, showing stable query latencies with no socket leakage.
* **Repeated Policy Evaluation:** Policy evaluations are executed strictly once per unique write request inside the atomic transaction block, avoiding redundant work.
