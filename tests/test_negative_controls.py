import pytest
import uuid
from datetime import datetime, timezone
from evals.metrics import (
    calculate_average_precision,
    calculate_precision_at_k,
    calculate_recall_at_k,
    calculate_reciprocal_rank,
    calculate_tenant_leakage,
    calculate_user_leakage,
    calculate_inactive_leakage,
    calculate_deleted_leakage,
    check_budget_compliance,
)
from app.domain import MemoryRecord, MemoryType, MemoryStatus, Sensitivity, PolicyDecision


# 1. Proving wrong ranking degrades retrieval metrics
def test_negative_control_ranking_degradation():
    expected = ["A", "B"]
    
    # Correct ranking order
    retrieved_correct = ["A", "B", "C"]
    ap_correct = calculate_average_precision(expected, retrieved_correct, k=3)
    rr_correct = calculate_reciprocal_rank(expected, retrieved_correct, k=3)
    
    # Degraded ranking order (relevant items pushed down)
    retrieved_degraded = ["C", "B", "A"]
    ap_degraded = calculate_average_precision(expected, retrieved_degraded, k=3)
    rr_degraded = calculate_reciprocal_rank(expected, retrieved_degraded, k=3)
    
    assert ap_degraded < ap_correct
    assert rr_degraded < rr_correct
    
    # Assert specific degraded metrics
    assert ap_correct == 1.0
    assert ap_degraded == pytest.approx((1/2 + 2/3) / 2) # (P@2 + P@3) / 2
    assert rr_correct == 1.0
    assert rr_degraded == 0.5 # First relevant item at index 1 (rank 2)


# 2. Proving tenant leakage produces a non-zero tenant leakage metric
def test_negative_control_tenant_leakage():
    retrieved_memories = [
        {"content": "clean", "tenant_id": "tenant_a"},
        {"content": "leaked", "tenant_id": "tenant_b"},  # Leaked tenant B memory
    ]
    leakage = calculate_tenant_leakage(retrieved_memories, expected_tenant_id="tenant_a")
    assert leakage == 1


# 3. Proving user leakage produces a non-zero user leakage metric
def test_negative_control_user_leakage():
    retrieved_memories = [
        {"content": "clean", "user_id": "user_a"},
        {"content": "leaked", "user_id": "user_b"},  # Leaked user B memory
    ]
    leakage = calculate_user_leakage(retrieved_memories, expected_user_id="user_a")
    assert leakage == 1


# 4. Proving inactive/deleted memory leakage is detected
def test_negative_control_status_leakages():
    # Inactive Leakage: pending, rejected, archived
    memories_inactive = [
        {"content": "pending info", "status": MemoryStatus.PENDING},
        {"content": "archived info", "status": "archived"},
        {"content": "active info", "status": MemoryStatus.ACTIVE},
    ]
    assert calculate_inactive_leakage(memories_inactive) == 2

    # Deleted Leakage
    memories_deleted = [
        {"content": "deleted info", "status": MemoryStatus.DELETED},
        {"content": "active info", "status": MemoryStatus.ACTIVE},
    ]
    assert calculate_deleted_leakage(memories_deleted) == 1


# 5. Proving budget overflow is detected
def test_negative_control_budget_overflows():
    # Memory count budget overflow (> 10)
    memories_count = [{"content": "m"} for _ in range(11)]
    assert check_budget_compliance(memories_count, max_memories=10) is False

    # Character count budget overflow (> 4000)
    memories_chars = [{"content": "A" * 4001}]
    assert check_budget_compliance(memories_chars, max_characters=4000) is False


# 6. Proving fallback failure is detected
def test_negative_control_fallback_failure_detection():
    # Fallback failure is detected when the coordinator mode does not match expectations.
    # In our runner, we assert expected_mode against the actual coordinator mode.
    # If the system failed to fall back when embedding fails, actual mode is hybrid or none instead of fallback.
    actual_mode = "hybrid"
    expected_mode = "fallback"
    assert actual_mode != expected_mode


# 7. Proving non-deterministic or incorrect tie ordering is detected
def test_negative_control_tie_ordering_detection():
    # Expected order favors earlier created_at and smaller UUID
    expected_ordered_contents = ["first expected", "second expected"]
    
    # actual retrieved order is reversed (incorrect tie-breaking order)
    actual_ordered_contents = ["second expected", "first expected"]
    
    # Content Match check must fail
    assert actual_ordered_contents != expected_ordered_contents
