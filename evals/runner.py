import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import uuid

# Set up path resolution so it can run standalone
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "services", "api")))

from app.domain import (
    MemoryRecord,
    MemoryType,
    MemoryStatus,
    Sensitivity,
    PolicyDecision,
    CandidateMemory,
)
from app.services import (
    Retriever,
    Ranker,
    ContextComposer,
    RetrievalCoordinator,
    EmbeddingService,
)
from app.services.retrieval_telemetry import RetrievalTelemetry
from app.repositories import InMemoryMemoryRepository
from app.policy import PolicyBroker

from evals.metrics import (
    calculate_lexical_token_overlap,
    calculate_precision_at_k,
    calculate_recall_at_k,
    calculate_reciprocal_rank,
    calculate_average_precision,
    calculate_tenant_leakage,
    calculate_user_leakage,
    calculate_inactive_leakage,
    calculate_deleted_leakage,
    check_budget_compliance,
)


class MockEmbeddingService(EmbeddingService):
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail

    async def generate_embedding(self, text: str) -> List[float]:
        if self.should_fail:
            raise Exception("Simulated embedding provider connection failure.")
        if not text or not text.strip():
            raise ValueError("text input cannot be empty or whitespace-only")
        # Return 1536-dimensional mock vector
        return [0.1] * 1536


class CaptureRetrievalTelemetry(RetrievalTelemetry):
    def __init__(self) -> None:
        self.emitted_payloads: List[Dict[str, Any]] = []

    def emit(self, event_payload: Dict[str, Any]) -> None:
        self.emitted_payloads.append(event_payload)


def calculate_percentile(values: List[float], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = max(0, min(len(sorted_vals) - 1, int(len(sorted_vals) * percentile)))
    return sorted_vals[idx]


async def run_evaluation():
    # Load Golden Dataset
    dataset_path = os.path.join(os.path.dirname(__file__), "data", "golden_dataset.json")
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    test_cases = data.get("test_cases", [])
    total_cases = len(test_cases)
    passed_cases = 0
    failed_cases = 0

    results_table = []
    
    # Latency trackers
    retrieve_latencies = []
    rank_latencies = []
    compose_latencies = []
    total_latencies = []

    # Aggregates trackers
    retrieval_case_count = 0
    policy_case_count = 0
    passed_policy_count = 0

    sum_precision_at_k = 0.0
    sum_recall_at_k = 0.0
    sum_reciprocal_rank = 0.0
    sum_average_precision = 0.0
    sum_lexical_token_overlap = 0.0

    tenant_leakage_runs = 0
    user_leakage_runs = 0
    inactive_leakage_runs = 0
    deleted_leakage_runs = 0
    budget_overflow_runs = 0

    # Custom targets trackers
    fallback_cases_count = 0
    fallback_success_count = 0
    tie_breaking_cases_count = 0
    tie_breaking_success_count = 0
    temporary_chat_cases_count = 0
    temporary_chat_success_count = 0

    case_failures_evidence = []

    # Invariant mappings to track tests
    invariant_verifying_cases = {
        "INV-001": ["TC-TEN-001"],
        "INV-002": ["TC-STA-001", "TC-STA-002", "TC-STA-003"],
        "INV-003": ["TC-STA-004"],
        "INV-004": ["TC-POL-001", "TC-POL-002", "TC-POL-003", "TC-POL-004"],
        "INV-008": ["TC-RET-006"],
        "INV-009": ["TC-BUD-001", "TC-BUD-002"],
        "INV-010": ["TC-TMP-001"],
        "INV-011": ["TC-ERR-001"]
    }
    invariant_status = {inv: "FAILED" for inv in invariant_verifying_cases}

    print("=" * 100)
    print(f"MemoryOps AI — Programmatic Quality Evaluation Suite ({total_cases} Scenarios)")
    print("=" * 100)

    for case in test_cases:
        case_id = case["id"]
        category = case["category"]
        description = case["description"]
        tenant_id = case["tenant_id"]
        user_id = case["user_id"]
        query = case["query"]
        difficulty = case["difficulty"]

        # 1. Initialize a fresh repository
        repo = InMemoryMemoryRepository()

        # 2. Seed memory records (using index-based UUIDs for deterministic tie-breaking)
        for idx, seed in enumerate(case.get("seed_memories", [])):
            rec_id = uuid.UUID(int=idx + 1)
            fixed_now = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
            created_at = datetime.fromisoformat(seed["created_at"].replace("Z", "+00:00")) if "created_at" in seed else fixed_now
            updated_at = datetime.fromisoformat(seed["updated_at"].replace("Z", "+00:00")) if "updated_at" in seed else fixed_now
            
            status_val = MemoryStatus(seed.get("status", "active"))
            archived_at_ts = fixed_now if status_val == MemoryStatus.ARCHIVED else None
            deleted_at_ts = fixed_now if status_val == MemoryStatus.DELETED else None

            # Conditionally set embedding vector based on schema has_embedding key
            embedding_val = [0.1] * 1536 if seed.get("has_embedding", True) else None

            record = MemoryRecord(
                id=rec_id,
                tenant_id=seed.get("tenant_id", tenant_id),
                user_id=seed.get("user_id", user_id),
                content=seed["content"],
                memory_type=MemoryType(seed.get("memory_type", "semantic")),
                status=status_val,
                sensitivity=Sensitivity(seed.get("sensitivity", "low")),
                importance=seed.get("importance", 5),
                confidence=seed.get("confidence", 1.0),
                reinforcement_count=seed.get("reinforcement_count", 0),
                source_kind=seed.get("source_kind", "chat"),
                source_excerpt=seed.get("source_excerpt"),
                initial_policy_decision=PolicyDecision.SAVE,
                initial_policy_reason="seeded for evaluation",
                identity_slot=seed.get("identity_slot"),
                embedding=embedding_val,
                created_at=created_at,
                updated_at=updated_at,
                archived_at=archived_at_ts,
                deleted_at=deleted_at_ts,
            )
            await repo.create(record)

        # 3. Branch execution based on test category
        case_passed = False
        metrics_report = {}
        error_detail = None

        try:
            if category == "policy_validation":
                policy_case_count += 1
                # Execute Policy Broker
                broker = PolicyBroker(repository=repo)
                candidate = CandidateMemory(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    content=query,
                    memory_type=MemoryType(case.get("memory_type", "semantic")),
                    confidence=case.get("confidence", 1.0),
                    importance=case.get("importance", 5),
                    sensitivity=Sensitivity(case.get("sensitivity", "low")),
                    source_kind="chat",
                    identity_slot=case.get("candidate_identity_slot")
                )
                
                result = await broker.evaluate(candidate)
                actual_decision = result.decision.value
                expected_decision = case["expected_policy_decision"]

                case_passed = (actual_decision == expected_decision)
                if case_passed:
                    passed_policy_count += 1

                metrics_report = {
                    "Expected Decision": expected_decision,
                    "Actual Decision": actual_decision,
                    "Decision Match": "PASS" if case_passed else "FAIL",
                }
            else:
                retrieval_case_count += 1
                # Track custom trackers
                if case.get("force_embedding_fail", False):
                    fallback_cases_count += 1
                if case.get("temporary_chat", False):
                    temporary_chat_cases_count += 1
                if case_id == "TC-RET-006":
                    tie_breaking_cases_count += 1

                # Execute Retrieval path
                embed_service = MockEmbeddingService(should_fail=case.get("force_embedding_fail", False))
                retriever = Retriever(repo)
                ranker = Ranker()
                composer = ContextComposer()
                telemetry = CaptureRetrievalTelemetry()
                
                coordinator = RetrievalCoordinator(
                    embedding_service=embed_service,
                    retriever=retriever,
                    ranker=ranker,
                    context_composer=composer,
                    telemetry=telemetry,
                )

                ctx, used_memories, mode = await coordinator.retrieve_context(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    query_text=query,
                    temporary_chat=case.get("temporary_chat", False),
                )

                # Collect latency metrics
                if telemetry.emitted_payloads:
                    payload = telemetry.emitted_payloads[-1]
                    latency_stats = payload.get("latency_ms", {})
                    ret_l = latency_stats.get("retrieve", 0.0)
                    ran_l = latency_stats.get("rank", 0.0)
                    com_l = latency_stats.get("compose", 0.0)
                    
                    retrieve_latencies.append(ret_l)
                    rank_latencies.append(ran_l)
                    compose_latencies.append(com_l)
                    total_latencies.append(ret_l + ran_l + com_l)

                # Compute Metrics
                retrieved_contents = [um.content for um in used_memories]
                expected_contents = case["expected_retrieved_contents"]

                # 1. Standard retrieval metrics
                precision = calculate_precision_at_k(expected_contents, retrieved_contents)
                recall = calculate_recall_at_k(expected_contents, retrieved_contents)
                rr = calculate_reciprocal_rank(expected_contents, retrieved_contents)
                ap = calculate_average_precision(expected_contents, retrieved_contents)
                
                sum_precision_at_k += precision
                sum_recall_at_k += recall
                sum_reciprocal_rank += rr
                sum_average_precision += ap

                # 2. Diagnostic lexical token overlap (non-gating)
                lexical_overlap = calculate_lexical_token_overlap(query, ctx) if ctx else 0.0
                sum_lexical_token_overlap += lexical_overlap

                # 3. Boundary Leakage Verification (cross-tenant, cross-user, inactive, deleted)
                underlying_records = []
                for um in used_memories:
                    db_rec = repo._records.get(um.memory_id)
                    if db_rec:
                        underlying_records.append(db_rec)
                
                tenant_leak = calculate_tenant_leakage(underlying_records, tenant_id)
                user_leak = calculate_user_leakage(underlying_records, user_id)
                inactive_leak = calculate_inactive_leakage(underlying_records)
                deleted_leak = calculate_deleted_leakage(underlying_records)

                if tenant_leak > 0:
                    tenant_leakage_runs += 1
                if user_leak > 0:
                    user_leakage_runs += 1
                if inactive_leak > 0:
                    inactive_leakage_runs += 1
                if deleted_leak > 0:
                    deleted_leakage_runs += 1

                # 4. Budget Compliance
                budget_passed = check_budget_compliance(used_memories)
                if not budget_passed:
                    budget_overflow_runs += 1

                # 5. Retrieval Mode Verification
                expected_mode = case.get("expected_retrieval_mode", "hybrid")
                mode_passed = (mode.value == expected_mode)
                if case.get("force_embedding_fail", False) and mode_passed:
                    fallback_success_count += 1
                if case.get("temporary_chat", False) and mode_passed and not ctx and not used_memories:
                    temporary_chat_success_count += 1

                # 6. Expected Content Matching
                contents_match = (retrieved_contents == expected_contents)
                if case_id == "TC-RET-006" and contents_match:
                    tie_breaking_success_count += 1

                # 7. Check keyword score if explicitly expected
                keyword_score_passed = True
                if "expected_keyword_score" in case:
                    expected_keyword = case["expected_keyword_score"]
                    actual_keyword = used_memories[0].score_breakdown.keyword_score if used_memories else 0.0
                    keyword_score_passed = (actual_keyword == expected_keyword)
                    metrics_report["Keyword Score Match"] = "PASS" if keyword_score_passed else f"FAIL ({actual_keyword:.2f} != {expected_keyword:.2f})"

                # Determine overall pass (Jaccard / Lexical token overlap is excluded from gating)
                case_passed = (
                    precision >= 0.99
                    and recall >= 0.99
                    and rr >= 0.99
                    and ap >= 0.99
                    and tenant_leak == 0
                    and user_leak == 0
                    and inactive_leak == 0
                    and deleted_leak == 0
                    and budget_passed
                    and mode_passed
                    and contents_match
                    and keyword_score_passed
                )

                metrics_report.update({
                    "P@K": f"{precision:.2f}",
                    "R@K": f"{recall:.2f}",
                    "RR": f"{rr:.2f}",
                    "AP": f"{ap:.2f}",
                    "LexOverlap": f"{lexical_overlap:.2f} (Diag)",
                    "Leakages": f"T:{tenant_leak} U:{user_leak} I:{inactive_leak} D:{deleted_leak}",
                    "Budget": "OK" if budget_passed else "OVERFLOW",
                    "Content": "PASS" if contents_match else "FAIL",
                })

        except Exception as e:
            case_passed = False
            error_detail = str(e)
            metrics_report = {"Error": error_detail}

        if case_passed:
            passed_cases += 1
            status_str = "PASS"
        else:
            failed_cases += 1
            status_str = "FAIL"
            case_failures_evidence.append({
                "case_id": case_id,
                "category": category,
                "query": query,
                "error": error_detail or f"Metric expectations failed: {metrics_report}"
            })

        results_table.append({
            "id": case_id,
            "category": category,
            "difficulty": difficulty,
            "status": status_str,
            "report": metrics_report,
            "error": error_detail
        })

    # Update Invariant Evidence Status based on case outcomes
    for inv, cases_list in invariant_verifying_cases.items():
        inv_passed = True
        for c_id in cases_list:
            # find if case passed
            c_res = next((r for r in results_table if r["id"] == c_id), None)
            if not c_res or c_res["status"] != "PASS":
                inv_passed = False
                break
        invariant_status[inv] = "GREEN" if inv_passed else "FAILED"

    # Compute Aggregates
    mean_precision = sum_precision_at_k / max(retrieval_case_count, 1)
    mean_recall = sum_recall_at_k / max(retrieval_case_count, 1)
    mean_rr = sum_reciprocal_rank / max(retrieval_case_count, 1)
    mean_ap = sum_average_precision / max(retrieval_case_count, 1)
    mean_lex_overlap = sum_lexical_token_overlap / max(retrieval_case_count, 1)

    policy_acc = passed_policy_count / max(policy_case_count, 1)
    tenant_leak_rate = tenant_leakage_runs / max(retrieval_case_count, 1)
    user_leak_rate = user_leakage_runs / max(retrieval_case_count, 1)
    inactive_leak_rate = inactive_leakage_runs / max(retrieval_case_count, 1)
    deleted_leak_rate = deleted_leakage_runs / max(retrieval_case_count, 1)
    budget_overflow_rate = budget_overflow_runs / max(retrieval_case_count, 1)

    fallback_rate = fallback_success_count / max(fallback_cases_count, 1)
    tie_consistency = tie_breaking_success_count / max(tie_breaking_cases_count, 1)
    temp_chat_isolation = temporary_chat_success_count / max(temporary_chat_cases_count, 1)

    # Render results table
    print(f"{'ID':<12} | {'Category':<22} | {'Difficulty':<10} | {'Status':<6} | {'Metrics Summary / Errors'}")
    print("-" * 100)
    for res in results_table:
        metrics_summary = ", ".join(f"{k}: {v}" for k, v in res["report"].items())
        if res["error"]:
            metrics_summary = f"EXCEPTION: {res['error']}"
        print(f"{res['id']:<12} | {res['category']:<22} | {res['difficulty']:<10} | {res['status']:<6} | {metrics_summary}")

    print("=" * 100)
    print("Aggregate Statistics:")
    print(f"Total Cases: {total_cases} | Passed: {passed_cases} | Failed: {failed_cases} | Pass Rate: {passed_cases/total_cases:.2%}")
    print("-" * 100)
    print(f"Mean Precision@K:                      {mean_precision:.2%}")
    print(f"Mean Recall@K:                         {mean_recall:.2%}")
    print(f"Mean Reciprocal Rank (MRR):            {mean_rr:.2%}")
    print(f"Mean Average Precision (AP):           {mean_ap:.2%}")
    print(f"Mean Lexical Token Overlap (Diag):     {mean_lex_overlap:.2%}")
    print(f"Policy Broker Accuracy:                {policy_acc:.2%}")
    print(f"Tenant Leakage Rate:                   {tenant_leak_rate:.2%}")
    print(f"User Leakage Rate:                     {user_leak_rate:.2%}")
    print(f"Inactive Memory Leakage Rate:          {inactive_leak_rate:.2%}")
    print(f"Deleted Memory Leakage Rate:           {deleted_leak_rate:.2%}")
    print(f"Budget Overflow Rate:                  {budget_overflow_rate:.2%}")
    print(f"Fallback Success Rate:                 {fallback_rate:.2%}")
    print(f"Deterministic Tie Ordering Rate:       {tie_consistency:.2%}")
    print(f"Temporary Chat Isolation Rate:         {temp_chat_isolation:.2%}")
    print("-" * 100)

    # Calculate Latency Percentiles per phase
    lat_report = {}
    for label, lat_list in [
        ("retrieve", retrieve_latencies),
        ("rank", rank_latencies),
        ("compose", compose_latencies),
        ("total", total_latencies),
    ]:
        p50 = calculate_percentile(lat_list, 0.50)
        p90 = calculate_percentile(lat_list, 0.90)
        p99 = calculate_percentile(lat_list, 0.99)
        lat_report[label] = {"p50": p50, "p90": p90, "p99": p99}
        print(f"Latency ({label:<8}): p50={p50:.2f}ms | p90={p90:.2f}ms | p99={p99:.2f}ms (Observational)")
    print("=" * 100)

    # Construct Evidence Artifact JSON
    evidence = {
        "schema_version": "1.0.0",
        "dataset_version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_summary": {
            "total_cases": total_cases,
            "passed_cases": passed_cases,
            "failed_cases": failed_cases,
            "pass_rate": passed_cases / total_cases
        },
        "aggregate_metrics": {
            "mean_precision_at_k": mean_precision,
            "mean_recall_at_k": mean_recall,
            "mean_reciprocal_rank": mean_rr,
            "mean_average_precision": mean_ap,
            "mean_lexical_token_overlap": mean_lex_overlap,
            "policy_accuracy": policy_acc,
            "tenant_leakage_rate": tenant_leak_rate,
            "user_leakage_rate": user_leak_rate,
            "inactive_memory_leakage_rate": inactive_leak_rate,
            "deleted_memory_leakage_rate": deleted_leak_rate,
            "budget_overflow_rate": budget_overflow_rate,
            "fallback_success_rate": fallback_rate,
            "deterministic_ordering_consistency": tie_consistency,
            "temporary_chat_isolation_rate": temp_chat_isolation
        },
        "latency_percentiles": lat_report,
        "case_failures": case_failures_evidence,
        "invariant_evidence": {
            inv: {"status": status, "verifying_cases": invariant_verifying_cases[inv]}
            for inv, status in invariant_status.items()
        }
    }

    evidence_path = os.path.join(os.path.dirname(__file__), "evaluation_evidence.json")
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2)

    print(f"Emitted structured machine-readable evidence to: {evidence_path}")
    print("=" * 100)

    if failed_cases > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(run_evaluation())
