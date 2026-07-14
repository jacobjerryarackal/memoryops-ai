import pytest
from pydantic import ValidationError
from app.domain import CandidateMemory, MemoryRecord, MemoryType, MemoryStatus, Sensitivity, PolicyDecision, PolicyResult

def test_candidate_memory_accepts_none():
    candidate = CandidateMemory(
        tenant_id="tenant_a",
        user_id="user_a",
        content="Hello world",
        memory_type=MemoryType.SEMANTIC,
        confidence=0.9,
        importance=5,
        sensitivity=Sensitivity.LOW,
        identity_slot=None
    )
    assert candidate.identity_slot is None


def test_memory_record_accepts_none():
    record = MemoryRecord(
        tenant_id="tenant_a",
        user_id="user_a",
        content="Hello world",
        memory_type=MemoryType.SEMANTIC,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="Passed checks",
        identity_slot=None
    )
    assert record.identity_slot is None


def test_candidate_memory_accepts_valid_canonical():
    valid_slots = [
        "profession",
        "residence",
        "technology_stack",
        "project_built",
        "explanation_style",
        "formatting_hashtags",
        "formatting_hyphens",
        "gims_2026",
        "a",  # Single character
    ]
    for slot in valid_slots:
        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="Hello world",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.9,
            importance=5,
            sensitivity=Sensitivity.LOW,
            identity_slot=slot
        )
        assert candidate.identity_slot == slot


def test_memory_record_accepts_valid_canonical():
    valid_slots = [
        "profession",
        "residence",
        "technology_stack",
        "project_built",
        "explanation_style",
        "formatting_hashtags",
        "formatting_hyphens",
        "gims_2026",
        "a",  # Single character
    ]
    for slot in valid_slots:
        record = MemoryRecord(
            tenant_id="tenant_a",
            user_id="user_a",
            content="Hello world",
            memory_type=MemoryType.SEMANTIC,
            initial_policy_decision=PolicyDecision.SAVE,
            initial_policy_reason="Passed checks",
            identity_slot=slot
        )
        assert record.identity_slot == slot


def test_whitespace_trimming():
    candidate = CandidateMemory(
        tenant_id="tenant_a",
        user_id="user_a",
        content="Hello world",
        memory_type=MemoryType.SEMANTIC,
        confidence=0.9,
        importance=5,
        sensitivity=Sensitivity.LOW,
        identity_slot="   profession  "
    )
    assert candidate.identity_slot == "profession"

    record = MemoryRecord(
        tenant_id="tenant_a",
        user_id="user_a",
        content="Hello world",
        memory_type=MemoryType.SEMANTIC,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="Passed checks",
        identity_slot=" \t residence \n "
    )
    assert record.identity_slot == "residence"


def test_invalid_slots():
    invalid_slots = [
        "Profession",
        "PROFESSION",
        "profession-name",
        "explanation style",
        "semantic:profession",
        "jacob:profession",
        "_profession",
        "",
        "   ",
        "1profession",
        "a" * 65  # Longer than 64 characters
    ]
    for slot in invalid_slots:
        with pytest.raises(ValidationError):
            CandidateMemory(
                tenant_id="tenant_a",
                user_id="user_a",
                content="Hello world",
                memory_type=MemoryType.SEMANTIC,
                confidence=0.9,
                importance=5,
                sensitivity=Sensitivity.LOW,
                identity_slot=slot
            )

        with pytest.raises(ValidationError):
            MemoryRecord(
                tenant_id="tenant_a",
                user_id="user_a",
                content="Hello world",
                memory_type=MemoryType.SEMANTIC,
                initial_policy_decision=PolicyDecision.SAVE,
                initial_policy_reason="Passed checks",
                identity_slot=slot
            )


def test_64_character_limit():
    valid_64 = "a" * 64
    candidate = CandidateMemory(
        tenant_id="tenant_a",
        user_id="user_a",
        content="Hello world",
        memory_type=MemoryType.SEMANTIC,
        confidence=0.9,
        importance=5,
        sensitivity=Sensitivity.LOW,
        identity_slot=valid_64
    )
    assert candidate.identity_slot == valid_64


def test_policy_result_behavior_remains_unchanged():
    # Verify PolicyResult validations still work exactly as before
    # Valid save decision with no target memory id is allowed
    pr = PolicyResult(decision=PolicyDecision.SAVE, reason="Passed")
    assert pr.decision == PolicyDecision.SAVE

    # Update decision requires target_memory_id
    with pytest.raises(ValidationError):
        PolicyResult(decision=PolicyDecision.UPDATE_EXISTING, reason="Passed")
