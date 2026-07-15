import pytest
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
from app.domain.enums import MemoryStatus


def test_lexical_token_overlap():
    q = "Python engineer"
    c = "Jacob is a Python engineer."
    # normalized Q = {"python", "engineer"} -> size 2
    # normalized C = {"jacob", "is", "a", "python", "engineer"} -> size 5
    # intersection = {"python", "engineer"} -> size 2
    # union = {"jacob", "is", "a", "python", "engineer"} -> size 5
    # Jaccard = 2 / 5 = 0.40
    score = calculate_lexical_token_overlap(q, c)
    assert score == pytest.approx(0.40)


def test_lexical_token_overlap_no_overlap():
    q = "rust developer"
    c = "Jacob is a python engineer."
    assert calculate_lexical_token_overlap(q, c) == 0.0


def test_lexical_token_overlap_empty():
    assert calculate_lexical_token_overlap("", "Jacob is a python engineer.") == 0.0
    assert calculate_lexical_token_overlap("Python", "") == 0.0


def test_precision_at_k():
    expected = ["A", "B"]
    retrieved = ["A", "C", "B"]
    # Precision@2 = relevant in top 2 / 2 = 1 / 2 = 0.5
    assert calculate_precision_at_k(expected, retrieved, k=2) == 0.5
    # Precision@3 = relevant in top 3 / 3 = 2 / 3 = 0.6666
    assert calculate_precision_at_k(expected, retrieved, k=3) == pytest.approx(2/3)


def test_precision_at_k_empty():
    assert calculate_precision_at_k([], []) == 1.0
    assert calculate_precision_at_k([], ["A"]) == 0.0


def test_recall_at_k():
    expected = ["A", "B"]
    retrieved = ["A", "C", "B"]
    # Recall@2 = relevant in top 2 / expected = 1 / 2 = 0.5
    assert calculate_recall_at_k(expected, retrieved, k=2) == 0.5
    # Recall@3 = relevant in top 3 / expected = 2 / 2 = 1.0
    assert calculate_recall_at_k(expected, retrieved, k=3) == 1.0


def test_recall_at_k_empty():
    assert calculate_recall_at_k([], []) == 1.0
    assert calculate_recall_at_k([], ["A"]) == 0.0


def test_reciprocal_rank():
    expected = ["A", "B"]
    retrieved = ["C", "A", "B"]
    # First relevant item is "A" at index 1 (rank 2).
    # RR = 1 / 2 = 0.5
    assert calculate_reciprocal_rank(expected, retrieved, k=3) == 0.5

    # If first is relevant
    assert calculate_reciprocal_rank(expected, ["A", "C"], k=2) == 1.0

    # If none is relevant
    assert calculate_reciprocal_rank(expected, ["C", "D"], k=2) == 0.0


def test_reciprocal_rank_empty():
    assert calculate_reciprocal_rank([], []) == 1.0
    assert calculate_reciprocal_rank([], ["A"]) == 0.0


def test_average_precision():
    expected = ["A", "B"]
    retrieved = ["A", "C", "B"]
    # At rank 1: P@1 = 1/1 = 1.0. relevance(1) = 1
    # At rank 2: P@2 = 1/2 = 0.5. relevance(2) = 0
    # At rank 3: P@3 = 2/3 = 0.67. relevance(3) = 1
    # Sum = 1.0 * 1 + 0.5 * 0 + 0.6666 * 1 = 1.6666
    # denominator = min(len(expected), k) = min(2, 5) = 2
    # AP = 1.6666 / 2 = 0.8333
    score = calculate_average_precision(expected, retrieved, k=5)
    assert score == pytest.approx(1.66666 / 2, rel=1e-4)


def test_average_precision_empty():
    assert calculate_average_precision([], []) == 1.0
    assert calculate_average_precision([], ["A"]) == 0.0


def test_tenant_leakage():
    records = [
        {"tenant_id": "tenant_a", "user_id": "user_a"},
        {"tenant_id": "tenant_b", "user_id": "user_a"},
    ]
    assert calculate_tenant_leakage(records, "tenant_a") == 1


def test_user_leakage():
    records = [
        {"tenant_id": "tenant_a", "user_id": "user_a"},
        {"tenant_id": "tenant_a", "user_id": "user_b"},
    ]
    assert calculate_user_leakage(records, "user_a") == 1


def test_inactive_leakage():
    records = [
        {"tenant_id": "tenant_a", "user_id": "user_a", "status": MemoryStatus.ACTIVE},
        {"tenant_id": "tenant_a", "user_id": "user_a", "status": MemoryStatus.PENDING},
        {"tenant_id": "tenant_a", "user_id": "user_a", "status": MemoryStatus.ARCHIVED},
        {"tenant_id": "tenant_a", "user_id": "user_a", "status": MemoryStatus.DELETED},  # Excluded from inactive leakage (counted by deleted leakage)
    ]
    assert calculate_inactive_leakage(records) == 2


def test_deleted_leakage():
    records = [
        {"tenant_id": "tenant_a", "user_id": "user_a", "status": MemoryStatus.ACTIVE},
        {"tenant_id": "tenant_a", "user_id": "user_a", "status": MemoryStatus.DELETED},
    ]
    assert calculate_deleted_leakage(records) == 1


def test_budget_compliance_clean():
    memories = [
        {"content": "Hello"},
        {"content": "World"},
    ]
    assert check_budget_compliance(memories, max_memories=10, max_characters=20) is True


def test_budget_compliance_count_overflow():
    memories = [{"content": "x"} for _ in range(5)]
    assert check_budget_compliance(memories, max_memories=4, max_characters=10) is False


def test_budget_compliance_char_overflow():
    memories = [{"content": "very long content here"}]
    assert check_budget_compliance(memories, max_memories=10, max_characters=10) is False
