import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
import uuid
import pytest

# Set up path resolution so it can run standalone
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "services", "api")))

from app.domain import (
    MemoryRecord,
    MemoryType,
    MemoryStatus,
    Sensitivity,
    PolicyDecision,
    CandidateMemory,
    RankedCandidate,
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
    def __init__(self, should_fail: bool = False, mock_vector: Optional[List[float]] = None) -> None:
        self.should_fail = should_fail
        self.mock_vector = mock_vector

    async def generate_embedding(self, text: str) -> List[float]:
        if self.should_fail:
            raise Exception("Simulated embedding provider connection failure.")
        if not text or not text.strip():
            raise ValueError("text input cannot be empty or whitespace-only")
        if self.mock_vector is not None:
            return self.mock_vector
        # Return 1536-dimensional mock vector
        return [0.1] * 1536


class CaptureRetrievalTelemetry(RetrievalTelemetry):
    def __init__(self) -> None:
        self.emitted_payloads: List[Dict[str, Any]] = []

    def emit(self, event_payload: Dict[str, Any]) -> None:
        self.emitted_payloads.append(event_payload)


class PytestResultCollector:
    def __init__(self):
        self.results = []

    def pytest_runtest_logreport(self, report):
        if report.when == "call":
            self.results.append({
                "nodeid": report.nodeid,
                "outcome": report.outcome,
                "duration": report.duration,
                "exception": str(report.longrepr) if report.failed else None
            })


def calculate_percentile(values: List[float], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = max(0, min(len(sorted_vals) - 1, int(len(sorted_vals) * percentile)))
    return sorted_vals[idx]


def map_pytest_to_category(nodeid: str) -> str:
    nodeid_lower = nodeid.lower()
    if "test_retrieval_" in nodeid_lower or "test_embedding" in nodeid_lower or "test_openai_embedding" in nodeid_lower or "test_evaluation_metrics" in nodeid_lower:
        return "retrieval"
    elif "test_governance_" in nodeid_lower or "test_policy" in nodeid_lower or "test_write_" in nodeid_lower:
        return "governance"
    elif "test_auth_" in nodeid_lower or "test_jwt_" in nodeid_lower or "test_rls_" in nodeid_lower:
        return "security"
    elif "test_deletion_" in nodeid_lower:
        return "deletion"
    elif "test_admission_" in nodeid_lower:
        return "admission"
    elif "test_lifecycle_" in nodeid_lower:
        return "lifecycle"
    elif "test_postgres_" in nodeid_lower or "test_transaction" in nodeid_lower:
        return "concurrency"
    elif "test_gateway" in nodeid_lower or "test_sdk" in nodeid_lower:
        return "end-to-end"
    else:
        if "test_postgres_repository.py" in nodeid_lower:
            return "concurrency"
        return "retrieval"


async def run_golden_dataset() -> Dict[str, Any]:
    dataset_path = os.path.join(os.path.dirname(__file__), "data", "golden_dataset.json")
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    test_cases = data.get("test_cases", [])
    total_cases = len(test_cases)
    passed_cases = 0
    failed_cases = 0

    results_table = []
    retrieve_latencies = []
    rank_latencies = []
    compose_latencies = []
    total_latencies = []

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

    fallback_cases_count = 0
    fallback_success_count = 0
    tie_breaking_cases_count = 0
    tie_breaking_success_count = 0
    temporary_chat_cases_count = 0
    temporary_chat_success_count = 0

    case_failures_evidence = []

    category_map = {
        "retrieval_relevance": "retrieval",
        "policy_validation": "governance",
        "cross_tenant_isolation": "security",
        "cross_user_isolation": "security",
        "status_exclusion": "admission",
        "budget_stress": "admission",
        "embedding_fallback": "admission",
        "temporary_chat": "admission",
        "admission_validation": "admission"
    }

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

    # Initialize local categorized results for golden dataset
    golden_categories = {
        cat: {"cases": 0, "passed": 0, "failed": 0, "critical_failures": []}
        for cat in ["retrieval", "governance", "security", "deletion", "admission", "lifecycle", "concurrency", "end-to-end"]
    }

    for case in test_cases:
        case_id = case["id"]
        category = case["category"]
        description = case["description"]
        tenant_id = case["tenant_id"]
        user_id = case["user_id"]
        query = case["query"]
        difficulty = case["difficulty"]

        target_report_category = category_map.get(category, "retrieval")

        repo = InMemoryMemoryRepository()

        for idx, seed in enumerate(case.get("seed_memories", [])):
            rec_id = uuid.UUID(int=idx + 1)
            fixed_now = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
            created_at = datetime.fromisoformat(seed["created_at"].replace("Z", "+00:00")) if "created_at" in seed else fixed_now
            updated_at = datetime.fromisoformat(seed["updated_at"].replace("Z", "+00:00")) if "updated_at" in seed else fixed_now
            
            status_val = MemoryStatus(seed.get("status", "active"))
            archived_at_ts = fixed_now if status_val == MemoryStatus.ARCHIVED else None
            deleted_at_ts = fixed_now if status_val == MemoryStatus.DELETED else None

            if "embedding" in seed:
                embedding_val = seed["embedding"]
                if len(embedding_val) < 1536:
                    embedding_val = embedding_val + [0.0] * (1536 - len(embedding_val))
            else:
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

        case_passed = False
        metrics_report = {}
        error_detail = None

        try:
            if category == "policy_validation":
                policy_case_count += 1
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
                if case.get("force_embedding_fail", False):
                    fallback_cases_count += 1
                if case.get("temporary_chat", False):
                    temporary_chat_cases_count += 1
                if case_id == "TC-RET-006":
                    tie_breaking_cases_count += 1

                query_embedding_val = case.get("query_embedding")
                if query_embedding_val is not None:
                    if len(query_embedding_val) < 1536:
                        query_embedding_val = query_embedding_val + [0.0] * (1536 - len(query_embedding_val))
                
                embed_service = MockEmbeddingService(
                    should_fail=case.get("force_embedding_fail", False),
                    mock_vector=query_embedding_val
                )
                
                retriever = Retriever(repo)
                ranker = Ranker()
                composer = ContextComposer()
                telemetry = CaptureRetrievalTelemetry()
                
                from app.services.retrieval import (
                    ContextAdmissionLayer, PIIRedactionPolicy, LengthTruncationPolicy,
                    ImportanceDownrankPolicy, KeywordDenyPolicy, ConfidenceDenyPolicy,
                    ConfidenceDownrankPolicy, SensitivityDenyPolicy
                )
                admission_policies = [
                    PIIRedactionPolicy(),
                    LengthTruncationPolicy(max_length=1000),
                    ImportanceDownrankPolicy(threshold=3, penalty=0.5),
                    KeywordDenyPolicy(forbidden_keywords=["nuclear", "weapon", "hazardous"]),
                    ConfidenceDenyPolicy(threshold=0.3),
                    ConfidenceDownrankPolicy(threshold=0.5, penalty=0.3),
                    SensitivityDenyPolicy()
                ]
                admission = ContextAdmissionLayer(admission_policies)

                coordinator = RetrievalCoordinator(
                    embedding_service=embed_service,
                    retriever=retriever,
                    ranker=ranker,
                    context_composer=composer,
                    telemetry=telemetry,
                    admission_layer=admission if category == "admission_validation" else None,
                )

                ctx, used_memories, mode = await coordinator.retrieve_context(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    query_text=query,
                    temporary_chat=case.get("temporary_chat", False),
                )

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

                retrieved_contents = [um.content for um in used_memories]
                expected_contents = case["expected_retrieved_contents"]

                k_val = len(expected_contents) if expected_contents else 10
                precision = calculate_precision_at_k(expected_contents, retrieved_contents, k=k_val)
                recall = calculate_recall_at_k(expected_contents, retrieved_contents, k=k_val)
                rr = calculate_reciprocal_rank(expected_contents, retrieved_contents)
                ap = calculate_average_precision(expected_contents, retrieved_contents)
                
                sum_precision_at_k += precision
                sum_recall_at_k += recall
                sum_reciprocal_rank += rr
                sum_average_precision += ap

                lexical_overlap = calculate_lexical_token_overlap(query, ctx) if ctx else 0.0
                sum_lexical_token_overlap += lexical_overlap

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

                budget_passed = check_budget_compliance(used_memories)
                if not budget_passed:
                    budget_overflow_runs += 1

                expected_mode = case.get("expected_retrieval_mode", "hybrid")
                mode_passed = (mode.value == expected_mode)
                if case.get("force_embedding_fail", False) and mode_passed:
                    fallback_success_count += 1
                if case.get("temporary_chat", False) and mode_passed and not ctx and not used_memories:
                    temporary_chat_success_count += 1

                if not expected_contents:
                    contents_match = (retrieved_contents == [])
                else:
                    contents_match = (retrieved_contents[:len(expected_contents)] == expected_contents)

                if case_id == "TC-RET-006" and contents_match:
                    tie_breaking_success_count += 1

                keyword_score_passed = True
                if "expected_keyword_score" in case:
                    expected_keyword = case["expected_keyword_score"]
                    actual_keyword = used_memories[0].score_breakdown.keyword_score if used_memories else 0.0
                    keyword_score_passed = (actual_keyword == expected_keyword)
                    metrics_report["Keyword Score Match"] = "PASS" if keyword_score_passed else f"FAIL ({actual_keyword:.2f} != {expected_keyword:.2f})"

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

        golden_categories[target_report_category]["cases"] += 1
        if case_passed:
            passed_cases += 1
            status_str = "PASS"
            golden_categories[target_report_category]["passed"] += 1
        else:
            failed_cases += 1
            status_str = "FAIL"
            golden_categories[target_report_category]["failed"] += 1
            fail_desc = error_detail or f"Metric expectations failed: {metrics_report}"
            golden_categories[target_report_category]["critical_failures"].append({
                "case_id": case_id,
                "query": query,
                "error": fail_desc
            })
            case_failures_evidence.append({
                "case_id": case_id,
                "category": category,
                "query": query,
                "error": fail_desc
            })

        results_table.append({
            "id": case_id,
            "category": category,
            "difficulty": difficulty,
            "status": status_str,
            "report": metrics_report,
            "error": error_detail
        })

    # Update Invariant Evidence Status
    for inv, cases_list in invariant_verifying_cases.items():
        inv_passed = True
        for c_id in cases_list:
            c_res = next((r for r in results_table if r["id"] == c_id), None)
            if not c_res or c_res["status"] != "PASS":
                inv_passed = False
                break
        invariant_status[inv] = "GREEN" if inv_passed else "FAILED"

    # Compute Golden dataset statistics
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

    # Compile Golden execution packet
    return {
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "failed_cases": failed_cases,
        "results_table": results_table,
        "retrieve_latencies": retrieve_latencies,
        "rank_latencies": rank_latencies,
        "compose_latencies": compose_latencies,
        "total_latencies": total_latencies,
        "mean_precision": mean_precision,
        "mean_recall": mean_recall,
        "mean_rr": mean_rr,
        "mean_ap": mean_ap,
        "mean_lex_overlap": mean_lex_overlap,
        "policy_acc": policy_acc,
        "tenant_leak_rate": tenant_leak_rate,
        "user_leak_rate": user_leak_rate,
        "inactive_leak_rate": inactive_leak_rate,
        "deleted_leak_rate": deleted_leak_rate,
        "budget_overflow_rate": budget_overflow_rate,
        "fallback_rate": fallback_rate,
        "tie_consistency": tie_consistency,
        "temp_chat_isolation": temp_chat_isolation,
        "case_failures_evidence": case_failures_evidence,
        "invariant_status": invariant_status,
        "invariant_verifying_cases": invariant_verifying_cases,
        "golden_categories": golden_categories,
        "retrieval_case_count": retrieval_case_count,
        "policy_case_count": policy_case_count,
        "passed_policy_count": passed_policy_count,
    }


def main():
    # 1. Run golden dataset evaluation asynchronously
    print("=" * 100)
    print("Running Golden Dataset Evaluation Scenarios...")
    print("=" * 100)
    golden = asyncio.run(run_golden_dataset())

    # 2. Run pytest synchronously in a clean environment without loop locks
    print("=" * 100)
    print("Executing full regression test suite via pytest...")
    print("=" * 100)
    collector = PytestResultCollector()
    pytest.main(["-q"], plugins=[collector])

    # 3. Combine categorized results
    categorized_results = {
        cat: {"cases": 0, "passed": 0, "failed": 0, "score": 0.0, "critical_failures": []}
        for cat in ["retrieval", "governance", "security", "deletion", "admission", "lifecycle", "concurrency", "end-to-end"]
    }

    # Add golden dataset outcomes
    for cat, metrics in golden["golden_categories"].items():
        categorized_results[cat]["cases"] += metrics["cases"]
        categorized_results[cat]["passed"] += metrics["passed"]
        categorized_results[cat]["failed"] += metrics["failed"]
        categorized_results[cat]["critical_failures"].extend(metrics["critical_failures"])

    # Add pytest outcomes
    for t_res in collector.results:
        node = t_res["nodeid"]
        outcome = t_res["outcome"]
        exc = t_res["exception"]
        
        if outcome == "skipped":
            continue
            
        pytest_cat = map_pytest_to_category(node)
        categorized_results[pytest_cat]["cases"] += 1
        if outcome == "passed":
            categorized_results[pytest_cat]["passed"] += 1
        else:
            categorized_results[pytest_cat]["failed"] += 1
            categorized_results[pytest_cat]["critical_failures"].append({
                "test_name": node,
                "error": exc or "Assertion failed or error during execution"
            })

    # Compute scores per category and globally
    overall_total = 0
    overall_passed = 0
    for cat, metrics in categorized_results.items():
        c_tot = metrics["cases"]
        c_pass = metrics["passed"]
        metrics["score"] = c_pass / max(c_tot, 1)
        overall_total += c_tot
        overall_passed += c_pass

    overall_pass_rate = overall_passed / max(overall_total, 1)

    # Output Results Table
    print(f"{'ID':<12} | {'Category':<22} | {'Difficulty':<10} | {'Status':<6} | {'Metrics Summary / Errors'}")
    print("-" * 100)
    for res in golden["results_table"]:
        metrics_summary = ", ".join(f"{k}: {v}" for k, v in res["report"].items())
        if res["error"]:
            metrics_summary = f"EXCEPTION: {res['error']}"
        print(f"{res['id']:<12} | {res['category']:<22} | {res['difficulty']:<10} | {res['status']:<6} | {metrics_summary}")

    print("=" * 100)
    print("Aggregate Statistics (Golden Dataset only):")
    print(f"Total Cases: {golden['total_cases']} | Passed: {golden['passed_cases']} | Failed: {golden['failed_cases']} | Pass Rate: {golden['passed_cases']/golden['total_cases']:.2%}")
    print("-" * 100)
    print(f"Mean Precision@K:                      {golden['mean_precision']:.2%}")
    print(f"Mean Recall@K:                         {golden['mean_recall']:.2%}")
    print(f"Mean Reciprocal Rank (MRR):            {golden['mean_rr']:.2%}")
    print(f"Mean Average Precision (AP):           {golden['mean_ap']:.2%}")
    print(f"Mean Lexical Token Overlap (Diag):     {golden['mean_lex_overlap']:.2%}")
    print(f"Policy Broker Accuracy:                {golden['policy_acc']:.2%}")
    print(f"Tenant Leakage Rate:                   {golden['tenant_leak_rate']:.2%}")
    print(f"User Leakage Rate:                     {golden['user_leak_rate']:.2%}")
    print(f"Inactive Memory Leakage Rate:          {golden['inactive_leak_rate']:.2%}")
    print(f"Deleted Memory Leakage Rate:           {golden['deleted_leak_rate']:.2%}")
    print(f"Budget Overflow Rate:                  {golden['budget_overflow_rate']:.2%}")
    print(f"Fallback Success Rate:                 {golden['fallback_rate']:.2%}")
    print(f"Deterministic Tie Ordering Rate:       {golden['tie_consistency']:.2%}")
    print(f"Temporary Chat Isolation Rate:         {golden['temp_chat_isolation']:.2%}")
    print("-" * 100)

    # Compute Latency Stats
    lat_report = {}
    for label, lat_list in [
        ("retrieve", golden["retrieve_latencies"]),
        ("rank", golden["rank_latencies"]),
        ("compose", golden["compose_latencies"]),
        ("total", golden["total_latencies"]),
    ]:
        p50 = calculate_percentile(lat_list, 0.50)
        p90 = calculate_percentile(lat_list, 0.90)
        p99 = calculate_percentile(lat_list, 0.99)
        lat_report[label] = {"p50": p50, "p90": p90, "p99": p99}
        print(f"Latency ({label:<8}): p50={p50:.2f}ms | p90={p90:.2f}ms | p99={p99:.2f}ms (Observational)")
    print("=" * 100)

    # Emit standard evaluation_evidence.json
    evidence = {
        "schema_version": "1.0.0",
        "dataset_version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "run_summary": {
            "total_cases": golden["total_cases"],
            "passed_cases": golden["passed_cases"],
            "failed_cases": golden["failed_cases"],
            "pass_rate": golden["passed_cases"] / golden["total_cases"]
        },
        "aggregate_metrics": {
            "mean_precision_at_k": golden["mean_precision"],
            "mean_recall_at_k": golden["mean_recall"],
            "mean_reciprocal_rank": golden["mean_rr"],
            "mean_average_precision": golden["mean_ap"],
            "mean_lexical_token_overlap": golden["mean_lex_overlap"],
            "policy_accuracy": golden["policy_acc"],
            "tenant_leakage_rate": golden["tenant_leak_rate"],
            "user_leakage_rate": golden["user_leak_rate"],
            "inactive_memory_leakage_rate": golden["inactive_leak_rate"],
            "deleted_memory_leakage_rate": golden["deleted_leak_rate"],
            "budget_overflow_rate": golden["budget_overflow_rate"],
            "fallback_success_rate": golden["fallback_rate"],
            "deterministic_ordering_consistency": golden["tie_consistency"],
            "temporary_chat_isolation_rate": golden["temp_chat_isolation"]
        },
        "latency_percentiles": lat_report,
        "case_failures": golden["case_failures_evidence"],
        "invariant_evidence": {
            inv: {"status": status, "verifying_cases": golden["invariant_verifying_cases"][inv]}
            for inv, status in golden["invariant_status"].items()
        }
    }
    evidence_path = os.path.join(os.path.dirname(__file__), "evaluation_evidence.json")
    with open(evidence_path, "w", encoding="utf-8") as f:
        json.dump(evidence, f, indent=2)
    print(f"Emitted structured machine-readable evidence to: {evidence_path}")

    # Emit new evaluation_results.json
    results_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "overall_pass_rate": overall_pass_rate,
        "total_cases": overall_total,
        "passed_cases": overall_passed,
        "failed_cases": overall_total - overall_passed,
        "categories": categorized_results
    }
    results_path = os.path.join(os.path.dirname(__file__), "evaluation_results.json")
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(results_payload, f, indent=2)
    print(f"Emitted categorized evaluation results to: {results_path}")

    # Quality Gates Verification
    QUALITY_GATES = {
        "mean_precision_at_k": {"threshold": 0.85, "op": "ge", "actual": golden["mean_precision"], "name": "Mean Precision@K"},
        "mean_recall_at_k": {"threshold": 0.80, "op": "ge", "actual": golden["mean_recall"], "name": "Mean Recall@K"},
        "mean_reciprocal_rank": {"threshold": 0.80, "op": "ge", "actual": golden["mean_rr"], "name": "Mean Reciprocal Rank (MRR)"},
        "tenant_leakage_rate": {"threshold": 0.0, "op": "le", "actual": golden["tenant_leak_rate"], "name": "Tenant Leakage Rate"},
        "user_leakage_rate": {"threshold": 0.0, "op": "le", "actual": golden["user_leak_rate"], "name": "User Leakage Rate"},
        "inactive_memory_leakage_rate": {"threshold": 0.0, "op": "le", "actual": golden["inactive_leak_rate"], "name": "Inactive Memory Leakage Rate"},
        "deleted_memory_leakage_rate": {"threshold": 0.0, "op": "le", "actual": golden["deleted_leak_rate"], "name": "Deleted Memory Leakage Rate"},
        "budget_overflow_rate": {"threshold": 0.0, "op": "le", "actual": golden["budget_overflow_rate"], "name": "Budget Overflow Rate"},
    }

    gates_failed = False
    gate_details = {}
    print("-" * 100)
    print("Programmatic Quality Gates Verification:")
    print("-" * 100)
    for key, gate in QUALITY_GATES.items():
        actual = gate["actual"]
        thresh = gate["threshold"]
        op = gate["op"]
        name = gate["name"]
        
        if op == "ge":
            passed = actual >= thresh
            symbol = ">="
        else:
            passed = actual <= thresh
            symbol = "<="
            
        status_str = "PASSED" if passed else "FAILED"
        if not passed:
            gates_failed = True
            
        gate_details[key] = {
            "name": name,
            "threshold": thresh,
            "operator": symbol,
            "actual": actual,
            "status": status_str
        }
        print(f"{name:<35} | Target: {symbol} {thresh:<6.2%} | Actual: {actual:<6.2%} | {status_str}")

    scorecard_status = "FAILED" if (gates_failed or golden["failed_cases"] > 0 or (overall_total - overall_passed) > 0) else "PASSED"

    # Emit standard scorecard.json
    scorecard_data = {
        "scorecard_status": scorecard_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "golden_dataset_metrics": {
            "total_cases": golden["total_cases"],
            "passed_cases": golden["passed_cases"],
            "failed_cases": golden["failed_cases"]
        },
        "gates": gate_details
    }
    scorecard_json_path = os.path.join(os.path.dirname(__file__), "scorecard.json")
    with open(scorecard_json_path, "w", encoding="utf-8") as f:
        json.dump(scorecard_data, f, indent=2)
    print(f"Emitted structured scorecard scorecard.json to: {scorecard_json_path}")

    # Emit standard docs/evaluation/scorecard.md
    docs_dir = os.path.join(os.path.dirname(__file__), "..", "docs", "evaluation")
    os.makedirs(docs_dir, exist_ok=True)
    scorecard_md_path = os.path.join(docs_dir, "scorecard.md")
    
    md_lines = [
        "# MemoryOps AI — Quality Evaluation Scorecard",
        "",
        f"**Run Timestamp:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"**Overall Status:** `{scorecard_status}`",
        "",
        "## Golden Dataset Test Run Summary",
        "",
        f"- **Total Cases:** {golden['total_cases']}",
        f"- **Passed Cases:** {golden['passed_cases']}",
        f"- **Failed Cases:** {golden['failed_cases']}",
        f"- **Golden Test Case Pass Rate:** {golden['passed_cases'] / golden['total_cases']:.2%}",
        "",
        "## Programmatic Quality Gates",
        "",
        "| Quality Gate Metric | Operator | Target Threshold | Actual Performance | Status |",
        "| :--- | :---: | :---: | :---: | :---: |"
    ]
    for key, val in gate_details.items():
        target_fmt = f"{val['threshold']:.2%}"
        actual_fmt = f"{val['actual']:.2%}"
        status_md = f"**{val['status']}**" if val["status"] == "FAILED" else f"{val['status']}"
        md_lines.append(f"| {val['name']} | `{val['operator']}` | {target_fmt} | {actual_fmt} | {status_md} |")

    with open(scorecard_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")
    print(f"Emitted markdown scorecard scorecard.md to: {scorecard_md_path}")

    # Emit new docs/evaluation/retrieval-evaluation.md
    eval_md_path = os.path.join(docs_dir, "retrieval-evaluation.md")
    eval_md_lines = [
        "# MemoryOps AI — Retrieval & Evaluation Report",
        "",
        f"**Run Timestamp:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"**Overall Status:** `{scorecard_status}`",
        f"**Overall Pass Rate:** {overall_pass_rate:.2%} ({overall_passed}/{overall_total} cases)",
        "",
        "## Categorized Evaluation Report",
        "",
        "| Category | Total Cases | Passed | Failed | Pass Rate |",
        "| :--- | :---: | :---: | :---: | :---: |"
    ]
    for cat in sorted(categorized_results.keys()):
        metrics = categorized_results[cat]
        pass_rate_fmt = f"{metrics['score']:.2%}"
        eval_md_lines.append(f"| {cat} | {metrics['cases']} | {metrics['passed']} | {metrics['failed']} | {pass_rate_fmt} |")

    eval_md_lines.extend([
        "",
        "## Critical Failures Details",
        ""
    ])
    
    failures_found = False
    for cat in sorted(categorized_results.keys()):
        failures = categorized_results[cat]["critical_failures"]
        if failures:
            failures_found = True
            eval_md_lines.append(f"### Category: {cat}")
            eval_md_lines.append("")
            for f_item in failures:
                case_repr = f_item.get("case_id") or f_item.get("test_name") or "Unknown"
                error_repr = f_item.get("error") or "Unknown error"
                eval_md_lines.append(f"- **Case:** `{case_repr}`")
                eval_md_lines.append(f"  - **Error:** {error_repr}")
            eval_md_lines.append("")

    if not failures_found:
        eval_md_lines.append("*No critical failures encountered.*")

    with open(eval_md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(eval_md_lines) + "\n")
    print(f"Emitted categorized evaluation report retrieval-evaluation.md to: {eval_md_path}")
    print("=" * 100)

    if scorecard_status == "FAILED":
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
