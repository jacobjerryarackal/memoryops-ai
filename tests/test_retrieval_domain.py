import pytest
from uuid import uuid4
from pydantic import ValidationError
from app.domain import (
    MemoryRecord,
    MemoryType,
    MemoryStatus,
    Sensitivity,
    PolicyDecision,
    RetrievalCandidate,
    ScoreBreakdown,
    RankedCandidate,
    UsedMemory,
    UsedMemorySource,
    RetrievalMode,
)


def make_dummy_record() -> MemoryRecord:
    return MemoryRecord(
        id=uuid4(),
        tenant_id="tenant_a",
        user_id="user_a",
        content="Jacob is an AI Engineer.",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        sensitivity=Sensitivity.LOW,
        importance=8,
        confidence=0.92,
        reinforcement_count=1,
        source_kind="chat",
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="Durable technical preference.",
    )


# ── RetrievalCandidate Tests ──────────────────────────────────────────────────

def test_retrieval_candidate_valid_state():
    record = make_dummy_record()
    candidate = RetrievalCandidate(
        memory=record,
        cosine_similarity=0.85,
        matched_query_terms=2,
        total_unique_query_terms=3,
    )
    assert candidate.memory.id == record.id
    assert candidate.cosine_similarity == 0.85
    assert candidate.matched_query_terms == 2
    assert candidate.total_unique_query_terms == 3


def test_retrieval_candidate_allows_none_similarity():
    record = make_dummy_record()
    candidate = RetrievalCandidate(
        memory=record,
        cosine_similarity=None,
        matched_query_terms=1,
        total_unique_query_terms=2,
    )
    assert candidate.cosine_similarity is None


def test_retrieval_candidate_rejects_negative_terms():
    record = make_dummy_record()
    with pytest.raises(ValidationError):
        RetrievalCandidate(
            memory=record,
            cosine_similarity=0.85,
            matched_query_terms=-1,
            total_unique_query_terms=3,
        )

    with pytest.raises(ValidationError):
        RetrievalCandidate(
            memory=record,
            cosine_similarity=0.85,
            matched_query_terms=2,
            total_unique_query_terms=-1,
        )


def test_retrieval_candidate_rejects_matched_greater_than_total():
    record = make_dummy_record()
    with pytest.raises(ValidationError) as exc_info:
        RetrievalCandidate(
            memory=record,
            cosine_similarity=0.85,
            matched_query_terms=4,
            total_unique_query_terms=3,
        )
    assert "matched_query_terms cannot exceed total_unique_query_terms" in str(exc_info.value)


def test_retrieval_candidate_rejects_non_finite_similarity():
    record = make_dummy_record()
    for val in [float("nan"), float("inf"), float("-inf")]:
        with pytest.raises(ValidationError):
            RetrievalCandidate(
                memory=record,
                cosine_similarity=val,
                matched_query_terms=2,
                total_unique_query_terms=3,
            )


# ── ScoreBreakdown Tests ──────────────────────────────────────────────────────

def test_score_breakdown_accepts_valid_bounds():
    # Boundary 0.0
    bd0 = ScoreBreakdown(
        semantic_score=0.0,
        keyword_score=0.0,
        importance_score=0.0,
        recency_score=0.0,
        confidence_score=0.0,
        reinforcement_score=0.0,
    )
    assert bd0.semantic_score == 0.0

    # Boundary 1.0
    bd1 = ScoreBreakdown(
        semantic_score=1.0,
        keyword_score=1.0,
        importance_score=1.0,
        recency_score=1.0,
        confidence_score=1.0,
        reinforcement_score=1.0,
    )
    assert bd1.semantic_score == 1.0

    # Midpoints
    bd_mid = ScoreBreakdown(
        semantic_score=0.5,
        keyword_score=0.2,
        importance_score=0.8,
        recency_score=0.9,
        confidence_score=0.1,
        reinforcement_score=0.4,
    )
    assert bd_mid.semantic_score == 0.5


def test_score_breakdown_rejects_out_of_bounds():
    for field_name in [
        "semantic_score",
        "keyword_score",
        "importance_score",
        "recency_score",
        "confidence_score",
        "reinforcement_score",
    ]:
        # Under bound
        kwargs = {f: 0.5 for f in [
            "semantic_score", "keyword_score", "importance_score", 
            "recency_score", "confidence_score", "reinforcement_score"
        ]}
        kwargs[field_name] = -0.01
        with pytest.raises(ValidationError):
            ScoreBreakdown(**kwargs)

        # Over bound
        kwargs = {f: 0.5 for f in [
            "semantic_score", "keyword_score", "importance_score", 
            "recency_score", "confidence_score", "reinforcement_score"
        ]}
        kwargs[field_name] = 1.01
        with pytest.raises(ValidationError):
            ScoreBreakdown(**kwargs)


def test_score_breakdown_rejects_non_finite():
    for field_name in [
        "semantic_score",
        "keyword_score",
        "importance_score",
        "recency_score",
        "confidence_score",
        "reinforcement_score",
    ]:
        for val in [float("nan"), float("inf"), float("-inf")]:
            kwargs = {f: 0.5 for f in [
                "semantic_score", "keyword_score", "importance_score", 
                "recency_score", "confidence_score", "reinforcement_score"
            ]}
            kwargs[field_name] = val
            with pytest.raises(ValidationError):
                ScoreBreakdown(**kwargs)


# ── RankedCandidate Tests ─────────────────────────────────────────────────────

def test_ranked_candidate_accepts_valid_state():
    record = make_dummy_record()
    bd = ScoreBreakdown(
        semantic_score=0.8,
        keyword_score=0.6,
        importance_score=0.5,
        recency_score=0.9,
        confidence_score=0.92,
        reinforcement_score=0.2,
    )
    rc = RankedCandidate(
        memory=record,
        final_score=0.72,
        score_breakdown=bd,
        rank=1,
    )
    assert rc.memory.id == record.id
    assert rc.final_score == 0.72
    assert rc.rank == 1


def test_ranked_candidate_rejects_out_of_bounds_score():
    record = make_dummy_record()
    bd = ScoreBreakdown(
        semantic_score=0.8,
        keyword_score=0.6,
        importance_score=0.5,
        recency_score=0.9,
        confidence_score=0.92,
        reinforcement_score=0.2,
    )
    with pytest.raises(ValidationError):
        RankedCandidate(
            memory=record,
            final_score=-0.1,
            score_breakdown=bd,
            rank=1,
        )

    with pytest.raises(ValidationError):
        RankedCandidate(
            memory=record,
            final_score=1.1,
            score_breakdown=bd,
            rank=1,
        )


def test_ranked_candidate_rejects_non_finite_score():
    record = make_dummy_record()
    bd = ScoreBreakdown(
        semantic_score=0.8,
        keyword_score=0.6,
        importance_score=0.5,
        recency_score=0.9,
        confidence_score=0.92,
        reinforcement_score=0.2,
    )
    for val in [float("nan"), float("inf"), float("-inf")]:
        with pytest.raises(ValidationError):
            RankedCandidate(
                memory=record,
                final_score=val,
                score_breakdown=bd,
                rank=1,
            )


def test_ranked_candidate_rejects_rank_less_than_one():
    record = make_dummy_record()
    bd = ScoreBreakdown(
        semantic_score=0.8,
        keyword_score=0.6,
        importance_score=0.5,
        recency_score=0.9,
        confidence_score=0.92,
        reinforcement_score=0.2,
    )
    with pytest.raises(ValidationError):
        RankedCandidate(
            memory=record,
            final_score=0.75,
            score_breakdown=bd,
            rank=0,
        )


# ── UsedMemory Tests ──────────────────────────────────────────────────────────

def test_used_memory_valid_state():
    bd = ScoreBreakdown(
        semantic_score=0.8,
        keyword_score=0.6,
        importance_score=0.5,
        recency_score=0.9,
        confidence_score=0.92,
        reinforcement_score=0.2,
    )
    source = UsedMemorySource(kind="chat", excerpt="Remember Python")
    mid = uuid4()
    um = UsedMemory(
        memory_id=mid,
        content="Jacob prefers Python.",
        memory_type=MemoryType.PROCEDURAL,
        score=0.82,
        reason="Relevant technical preference.",
        score_breakdown=bd,
        source=source,
    )
    assert um.memory_id == mid
    assert um.content == "Jacob prefers Python."
    assert um.memory_type == MemoryType.PROCEDURAL
    assert um.score == 0.82
    assert um.reason == "Relevant technical preference."
    assert um.source.kind == "chat"
    assert um.source.excerpt == "Remember Python"


def test_used_memory_rejects_out_of_bounds_score():
    bd = ScoreBreakdown(
        semantic_score=0.8,
        keyword_score=0.6,
        importance_score=0.5,
        recency_score=0.9,
        confidence_score=0.92,
        reinforcement_score=0.2,
    )
    source = UsedMemorySource(kind="chat", excerpt="Remember Python")
    with pytest.raises(ValidationError):
        UsedMemory(
            memory_id=uuid4(),
            content="Jacob prefers Python.",
            memory_type=MemoryType.PROCEDURAL,
            score=-0.01,
            reason="Reason",
            score_breakdown=bd,
            source=source,
        )


def test_used_memory_rejects_non_finite_score():
    bd = ScoreBreakdown(
        semantic_score=0.8,
        keyword_score=0.6,
        importance_score=0.5,
        recency_score=0.9,
        confidence_score=0.92,
        reinforcement_score=0.2,
    )
    source = UsedMemorySource(kind="chat", excerpt="Remember Python")
    for val in [float("nan"), float("inf"), float("-inf")]:
        with pytest.raises(ValidationError):
            UsedMemory(
                memory_id=uuid4(),
                content="Jacob prefers Python.",
                memory_type=MemoryType.PROCEDURAL,
                score=val,
                reason="Reason",
                score_breakdown=bd,
                source=source,
            )


# ── RetrievalMode Tests ───────────────────────────────────────────────────────

def test_retrieval_mode_values():
    assert RetrievalMode.HYBRID == "hybrid"
    assert RetrievalMode.FALLBACK == "fallback"
    assert RetrievalMode.NONE == "none"
