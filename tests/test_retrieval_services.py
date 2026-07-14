import pytest
import math
from datetime import datetime, timezone, timedelta
from uuid import uuid4, UUID
from typing import List, Tuple, Optional


from app.domain import (
    MemoryRecord,
    MemoryType,
    MemoryStatus,
    Sensitivity,
    PolicyDecision,
    RetrievalCandidate,
    ScoreBreakdown,
    RankedCandidate,
)
from app.services import Retriever, Ranker


class FakeRepository:
    def __init__(self, records_with_sim: List[Tuple[MemoryRecord, Optional[float]]]) -> None:
        self.records_with_sim = records_with_sim
        self.last_query = {}

    async def search_candidates(
        self,
        tenant_id: str,
        user_id: str,
        query_embedding: Optional[List[float]],
        limit: int = 50,
    ) -> List[Tuple[MemoryRecord, Optional[float]]]:
        self.last_query = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "query_embedding": query_embedding,
            "limit": limit,
        }
        return self.records_with_sim


def make_dummy_record(content: str = "Test memory", created_at: Optional[datetime] = None) -> MemoryRecord:
    return MemoryRecord(
        id=uuid4(),
        tenant_id="tenant_a",
        user_id="user_a",
        content=content,
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        sensitivity=Sensitivity.LOW,
        importance=5,
        confidence=1.0,
        reinforcement_count=0,
        source_kind="chat",
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test",
        created_at=created_at or datetime.now(timezone.utc),
    )


# ── Retriever Tests ───────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_retriever_standard_lexical_matching():
    record = make_dummy_record("Jacob is a Python engineer.")
    fake_repo = FakeRepository([(record, 0.85)])
    retriever = Retriever(fake_repo)

    candidates = await retriever.retrieve("tenant_a", "user_a", "Python engineer", [0.1] * 1536, 10)
    assert len(candidates) == 1
    assert candidates[0].matched_query_terms == 2
    assert candidates[0].total_unique_query_terms == 2


@pytest.mark.anyio
async def test_retriever_case_and_duplicate_matching():
    record = make_dummy_record("Jacob works as an engineer using Python.")
    fake_repo = FakeRepository([(record, 0.85)])
    retriever = Retriever(fake_repo)

    candidates = await retriever.retrieve("tenant_a", "user_a", "python PYTHON engineer", [0.1] * 1536, 10)
    assert len(candidates) == 1
    assert candidates[0].matched_query_terms == 2
    assert candidates[0].total_unique_query_terms == 2


@pytest.mark.anyio
async def test_retriever_punctuation_cleaning():
    record = make_dummy_record("Jacob is an AI engineer.")
    fake_repo = FakeRepository([(record, 0.85)])
    retriever = Retriever(fake_repo)

    candidates = await retriever.retrieve("tenant_a", "user_a", "AI-engineer", [0.1] * 1536, 10)
    assert len(candidates) == 1
    assert candidates[0].matched_query_terms == 2
    assert candidates[0].total_unique_query_terms == 2


@pytest.mark.anyio
async def test_retriever_no_stemming_matching():
    record = make_dummy_record("Jacob prefers Python.")
    fake_repo = FakeRepository([(record, 0.85)])
    retriever = Retriever(fake_repo)

    candidates = await retriever.retrieve("tenant_a", "user_a", "What is my preferred language?", [0.1] * 1536, 10)
    assert len(candidates) == 1
    assert candidates[0].matched_query_terms == 0
    assert candidates[0].total_unique_query_terms == 5


@pytest.mark.anyio
async def test_retriever_unicode_characters():
    record = make_dummy_record("Café in München.")
    fake_repo = FakeRepository([(record, 0.85)])
    retriever = Retriever(fake_repo)

    candidates = await retriever.retrieve("tenant_a", "user_a", "München café", [0.1] * 1536, 10)
    assert len(candidates) == 1
    assert candidates[0].matched_query_terms == 2
    assert candidates[0].total_unique_query_terms == 2


@pytest.mark.anyio
async def test_retriever_duplicate_only_query():
    record = make_dummy_record("python developer")
    fake_repo = FakeRepository([(record, 0.85)])
    retriever = Retriever(fake_repo)

    candidates = await retriever.retrieve("tenant_a", "user_a", "python python python", [0.1] * 1536, 10)
    assert len(candidates) == 1
    assert candidates[0].total_unique_query_terms == 1
    assert candidates[0].matched_query_terms == 1


@pytest.mark.anyio
async def test_retriever_empty_normalized_query():
    record = make_dummy_record("some content")
    fake_repo = FakeRepository([(record, 0.85)])
    retriever = Retriever(fake_repo)

    candidates = await retriever.retrieve("tenant_a", "user_a", "   ---   ", [0.1] * 1536, 10)
    assert len(candidates) == 1
    assert candidates[0].total_unique_query_terms == 0
    assert candidates[0].matched_query_terms == 0


@pytest.mark.anyio
async def test_retriever_none_similarity_preservation():
    record = make_dummy_record("content")
    fake_repo = FakeRepository([(record, None)])
    retriever = Retriever(fake_repo)

    candidates = await retriever.retrieve("tenant_a", "user_a", "query", None, 10)
    assert len(candidates) == 1
    assert candidates[0].cosine_similarity is None


@pytest.mark.anyio
async def test_retriever_zero_similarity_preservation():
    record = make_dummy_record("content")
    fake_repo = FakeRepository([(record, 0.0)])
    retriever = Retriever(fake_repo)

    candidates = await retriever.retrieve("tenant_a", "user_a", "query", [0.1] * 1536, 10)
    assert len(candidates) == 1
    assert candidates[0].cosine_similarity == 0.0


@pytest.mark.anyio
async def test_retriever_repository_delegation():
    fake_repo = FakeRepository([])
    retriever = Retriever(fake_repo)

    embedding = [0.2] * 1536
    await retriever.retrieve("tenant_x", "user_y", "some query", embedding, 15)
    assert fake_repo.last_query == {
        "tenant_id": "tenant_x",
        "user_id": "user_y",
        "query_embedding": embedding,
        "limit": 15,
    }


@pytest.mark.anyio
async def test_retriever_empty_repository_results():
    fake_repo = FakeRepository([])
    retriever = Retriever(fake_repo)

    candidates = await retriever.retrieve("tenant_a", "user_a", "query", None, 10)
    assert candidates == []


# ── Ranker Tests ──────────────────────────────────────────────────────────────

def test_ranker_semantic_none_and_zero():
    ranker = Ranker()
    now = datetime.now(timezone.utc)
    rec1 = make_dummy_record("Rec 1")
    rec2 = make_dummy_record("Rec 2")

    c1 = RetrievalCandidate(memory=rec1, cosine_similarity=None, matched_query_terms=1, total_unique_query_terms=1)
    c2 = RetrievalCandidate(memory=rec2, cosine_similarity=0.0, matched_query_terms=1, total_unique_query_terms=1)

    ranked = ranker.rank([c1, c2], now)
    assert len(ranked) == 2
    assert ranked[0].score_breakdown.semantic_score == 0.0
    assert ranked[1].score_breakdown.semantic_score == 0.0


def test_ranker_cosine_clamping():
    ranker = Ranker()
    now = datetime.now(timezone.utc)
    rec1 = make_dummy_record("Rec 1")
    rec2 = make_dummy_record("Rec 2")

    c1 = RetrievalCandidate(memory=rec1, cosine_similarity=-0.6, matched_query_terms=1, total_unique_query_terms=1)
    c2 = RetrievalCandidate(memory=rec2, cosine_similarity=1.0000000002, matched_query_terms=1, total_unique_query_terms=1)

    ranked = ranker.rank([c1, c2], now)
    assert len(ranked) == 2
    
    # We sort by score descending. Let's find which one is which.
    for r in ranked:
        if r.memory.id == rec1.id:
            assert r.score_breakdown.semantic_score == 0.0
        elif r.memory.id == rec2.id:
            assert r.score_breakdown.semantic_score == 1.0


def test_ranker_keyword_score():
    ranker = Ranker()
    now = datetime.now(timezone.utc)
    rec = make_dummy_record()

    # Normal keyword ratio
    c1 = RetrievalCandidate(memory=rec, cosine_similarity=0.5, matched_query_terms=1, total_unique_query_terms=4)
    r1 = ranker.rank([c1], now)
    assert r1[0].score_breakdown.keyword_score == 0.25

    # Empty query keyword ratio
    c2 = RetrievalCandidate(memory=rec, cosine_similarity=0.5, matched_query_terms=0, total_unique_query_terms=0)
    r2 = ranker.rank([c2], now)
    assert r2[0].score_breakdown.keyword_score == 0.0


def test_ranker_importance_and_confidence():
    ranker = Ranker()
    now = datetime.now(timezone.utc)
    rec = make_dummy_record()
    rec.importance = 8
    rec.confidence = 0.95

    c = RetrievalCandidate(memory=rec, cosine_similarity=0.5, matched_query_terms=1, total_unique_query_terms=1)
    ranked = ranker.rank([c], now)
    assert ranked[0].score_breakdown.importance_score == 0.8
    assert ranked[0].score_breakdown.confidence_score == 0.95


def test_ranker_recency_score():
    ranker = Ranker()
    now = datetime.now(timezone.utc)
    rec = make_dummy_record()

    # Age 0
    rec.updated_at = now
    c_zero = RetrievalCandidate(memory=rec, cosine_similarity=0.5, matched_query_terms=1, total_unique_query_terms=1)
    r_zero = ranker.rank([c_zero], now)
    assert r_zero[0].score_breakdown.recency_score == 1.0

    # Age 30 days
    rec.updated_at = now - timedelta(days=30)
    c_30 = RetrievalCandidate(memory=rec, cosine_similarity=0.5, matched_query_terms=1, total_unique_query_terms=1)
    r_30 = ranker.rank([c_30], now)
    assert pytest.approx(r_30[0].score_breakdown.recency_score, rel=1e-5) == math.exp(-1)

    # Age 60 days
    rec.updated_at = now - timedelta(days=60)
    c_60 = RetrievalCandidate(memory=rec, cosine_similarity=0.5, matched_query_terms=1, total_unique_query_terms=1)
    r_60 = ranker.rank([c_60], now)
    assert pytest.approx(r_60[0].score_breakdown.recency_score, rel=1e-5) == math.exp(-2)


def test_ranker_fractional_days_recency():
    ranker = Ranker()
    now = datetime.now(timezone.utc)
    rec = make_dummy_record()

    # 15 days (fractional)
    rec.updated_at = now - timedelta(days=15)
    c = RetrievalCandidate(memory=rec, cosine_similarity=0.5, matched_query_terms=1, total_unique_query_terms=1)
    ranked = ranker.rank([c], now)
    assert pytest.approx(ranked[0].score_breakdown.recency_score, rel=1e-5) == math.exp(-0.5)


def test_ranker_future_timestamp_handling():
    ranker = Ranker()
    now = datetime.now(timezone.utc)
    rec = make_dummy_record()
    # 5 minutes in the future
    rec.updated_at = now + timedelta(minutes=5)

    c = RetrievalCandidate(memory=rec, cosine_similarity=0.5, matched_query_terms=1, total_unique_query_terms=1)
    ranked = ranker.rank([c], now)
    # Bounded interpretation: future timestamp treated as age_days = 0.0 -> recency_score = 1.0
    assert ranked[0].score_breakdown.recency_score == 1.0


def test_ranker_reinforcement_score():
    ranker = Ranker()
    now = datetime.now(timezone.utc)
    rec = make_dummy_record()

    # Reinforcement 0
    rec.reinforcement_count = 0
    c_zero = RetrievalCandidate(memory=rec, cosine_similarity=0.5, matched_query_terms=1, total_unique_query_terms=1)
    r_zero = ranker.rank([c_zero], now)
    assert r_zero[0].score_breakdown.reinforcement_score == 0.0

    # Reinforcement 5
    rec.reinforcement_count = 5
    c_five = RetrievalCandidate(memory=rec, cosine_similarity=0.5, matched_query_terms=1, total_unique_query_terms=1)
    r_five = ranker.rank([c_five], now)
    assert pytest.approx(r_five[0].score_breakdown.reinforcement_score, rel=1e-5) == 1 - math.exp(-1)


def test_ranker_final_weighted_score_calculation():
    ranker = Ranker()
    now = datetime.now(timezone.utc)
    rec = make_dummy_record()
    rec.importance = 5         # importance_score = 0.5
    rec.confidence = 1.0       # confidence_score = 1.0
    rec.reinforcement_count = 0 # reinforcement_score = 0.0
    rec.updated_at = now        # recency_score = 1.0

    # similarity = 0.8  -> semantic = 0.8
    # matched/total = 2/2 -> keyword = 1.0
    c = RetrievalCandidate(memory=rec, cosine_similarity=0.8, matched_query_terms=2, total_unique_query_terms=2)
    ranked = ranker.rank([c], now)

    expected_score = (
        0.35 * 0.8   # semantic
        + 0.20 * 1.0 # keyword
        + 0.15 * 0.5 # importance
        + 0.10 * 1.0 # recency
        + 0.10 * 1.0 # confidence
        + 0.10 * 0.0 # reinforcement
    ) # 0.28 + 0.20 + 0.075 + 0.10 + 0.10 = 0.755
    assert pytest.approx(ranked[0].final_score, rel=1e-5) == expected_score


def test_ranker_no_fallback_weight_renormalization():
    ranker = Ranker()
    now = datetime.now(timezone.utc)
    rec = make_dummy_record()
    rec.importance = 5
    rec.confidence = 1.0
    rec.reinforcement_count = 0
    rec.updated_at = now

    # Fallback mode: similarity is None -> semantic_score = 0.0
    c = RetrievalCandidate(memory=rec, cosine_similarity=None, matched_query_terms=2, total_unique_query_terms=2)
    ranked = ranker.rank([c], now)

    expected_score = (
        0.35 * 0.0   # semantic (0.0 contribution)
        + 0.20 * 1.0 # keyword
        + 0.15 * 0.5 # importance
        + 0.10 * 1.0 # recency
        + 0.10 * 1.0 # confidence
        + 0.10 * 0.0 # reinforcement
    ) # 0.0 + 0.20 + 0.075 + 0.10 + 0.10 = 0.475
    assert pytest.approx(ranked[0].final_score, rel=1e-5) == expected_score


def test_ranker_no_pre_sort_rounding():
    ranker = Ranker()
    now = datetime.now(timezone.utc)

    # Let's create two records that result in very close but distinct final scores
    rec1 = make_dummy_record("Rec 1")
    rec2 = make_dummy_record("Rec 2")

    c1 = RetrievalCandidate(memory=rec1, cosine_similarity=0.800002, matched_query_terms=1, total_unique_query_terms=1)
    c2 = RetrievalCandidate(memory=rec2, cosine_similarity=0.800001, matched_query_terms=1, total_unique_query_terms=1)

    ranked = ranker.rank([c1, c2], now)
    assert ranked[0].memory.id == rec1.id
    assert ranked[1].memory.id == rec2.id


def test_ranker_tie_breaking_created_at():
    ranker = Ranker()
    now = datetime.now(timezone.utc)

    # Identical score factors but different creation times
    rec_old = make_dummy_record("Old", created_at=now - timedelta(hours=1))
    rec_new = make_dummy_record("New", created_at=now)

    c_old = RetrievalCandidate(memory=rec_old, cosine_similarity=0.8, matched_query_terms=1, total_unique_query_terms=1)
    c_new = RetrievalCandidate(memory=rec_new, cosine_similarity=0.8, matched_query_terms=1, total_unique_query_terms=1)

    # Ranker sorts created_at DESC (newer first)
    ranked = ranker.rank([c_old, c_new], now)
    assert ranked[0].memory.id == rec_new.id
    assert ranked[1].memory.id == rec_old.id


def test_ranker_tie_breaking_uuid_alphabetical():
    ranker = Ranker()
    now = datetime.now(timezone.utc)
    ct = now - timedelta(hours=1)

    rec_a = make_dummy_record("Rec A", created_at=ct)
    rec_b = make_dummy_record("Rec B", created_at=ct)

    # Enforce known UUID sorting order
    uuid_str_a = "00000000-0000-0000-0000-000000000001"
    uuid_str_b = "00000000-0000-0000-0000-000000000002"
    rec_a.id = UUID(uuid_str_a)
    rec_b.id = UUID(uuid_str_b)


    c_a = RetrievalCandidate(memory=rec_a, cosine_similarity=0.8, matched_query_terms=1, total_unique_query_terms=1)
    c_b = RetrievalCandidate(memory=rec_b, cosine_similarity=0.8, matched_query_terms=1, total_unique_query_terms=1)

    # Ranker sorts id ASC (lexicographical smaller first)
    ranked = ranker.rank([c_a, c_b], now)
    assert ranked[0].memory.id == rec_a.id
    assert ranked[1].memory.id == rec_b.id


def test_ranker_rank_assignment_and_empty():
    ranker = Ranker()
    now = datetime.now(timezone.utc)
    
    # 1. Empty candidates
    assert ranker.rank([], now) == []

    # 2. Sequential rank assignment
    rec1 = make_dummy_record("Rec 1")
    rec2 = make_dummy_record("Rec 2")
    c1 = RetrievalCandidate(memory=rec1, cosine_similarity=0.9, matched_query_terms=1, total_unique_query_terms=1)
    c2 = RetrievalCandidate(memory=rec2, cosine_similarity=0.8, matched_query_terms=1, total_unique_query_terms=1)

    ranked = ranker.rank([c1, c2], now)
    assert ranked[0].rank == 1
    assert ranked[1].rank == 2
