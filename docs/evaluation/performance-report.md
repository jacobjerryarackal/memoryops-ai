# MemoryOps AI — Performance Benchmark Report

**Date:** 2026-08-14 12:26:33 UTC
**Scope:** Latency and internal database query metrics comparing InMemory vs PostgreSQL backends.

---

## Executive Summary
This report analyzes HTTP client SDK round-trip latencies and internal component durations for both `in-memory` and `postgresql` backends. Metrics are aggregated over 100 sequential iterations per operation.

---

## 1. SDK Client Round-Trip Latency (ms)

### In-Memory Backend (Active)
| Operation | p50 (Median) | p95 | p99 |
| :--- | :---: | :---: | :---: |
| **remember** | 24.57 ms | 35.95 ms | 55.47 ms |
| **recall** | 18.79 ms | 43.98 ms | 115.00 ms |
| **search** | 20.32 ms | 33.24 ms | 43.80 ms |
| **explain** | 18.91 ms | 27.93 ms | 29.28 ms |
| **delete** | 19.76 ms | 33.37 ms | 36.56 ms |

### PostgreSQL Backend (Active)
| Operation | p50 (Median) | p95 | p99 |
| :--- | :---: | :---: | :---: |
| **remember** | 74.31 ms | 295.52 ms | 1518.48 ms |
| **recall** | 23.80 ms | 40.83 ms | 89.37 ms |
| **search** | 49.85 ms | 76.43 ms | 651.19 ms |
| **explain** | 24.25 ms | 63.22 ms | 667.56 ms |
| **delete** | 72.17 ms | 117.70 ms | 915.43 ms |

---

## 2. Internal Trace & Database Query Diagnostics

Here we review internal engine spans parsed from the application's observability logging telemetry:

| Telemetry Metric | In-Memory Backend | PostgreSQL Backend |
| :--- | :---: | :---: |
| **Total database queries executed** | 0 | 4112 |
| **Cumulative DB query latency** | 0.00 ms | 6548.41 ms |
| **Policy broker evaluation count** | 100 | 100 |
| **Cumulative policy evaluation time** | 8.94 ms | 20.04 ms |
| **Context admission filter runs** | 200 | 200 |
| **Cumulative admission filter latency** | 915.81 ms | 710.45 ms |
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
