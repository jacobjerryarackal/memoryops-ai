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
    RetrievalMode,
    UsedMemory,
    UsedMemorySource,
)
from app.services import Retriever, Ranker, ContextComposer, RetrievalCoordinator, EmbeddingService


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


# ── ContextComposer Tests ─────────────────────────────────────────────────────

def test_composer_constructor_validation():
    # 1. Defaults
    composer = ContextComposer()
    assert composer.max_memories == 10
    assert composer.max_characters == 4000

    # 2. Valid custom bounds
    composer_custom = ContextComposer(max_memories=5, max_characters=100)
    assert composer_custom.max_memories == 5
    assert composer_custom.max_characters == 100

    # 3. Invalid values
    for val in [0, -1]:
        with pytest.raises(ValueError):
            ContextComposer(max_memories=val)
        with pytest.raises(ValueError):
            ContextComposer(max_characters=val)


def test_composer_selection_and_budgeting():
    # Helper to construct RankedCandidate
    def make_ranked(content: str, score: float, rank: int, semantic: float = 0.5, keyword: float = 0.5) -> RankedCandidate:
        rec = make_dummy_record(content)
        rec.source_kind = "chat"
        rec.source_excerpt = "excerpt"
        bd = ScoreBreakdown(
            semantic_score=semantic,
            keyword_score=keyword,
            importance_score=0.5,
            recency_score=0.5,
            confidence_score=0.5,
            reinforcement_score=0.5,
        )
        return RankedCandidate(memory=rec, final_score=score, score_breakdown=bd, rank=rank)

    composer = ContextComposer(max_memories=3, max_characters=25)

    cand1 = make_ranked("First short", 0.9, 1)  # len 11
    cand2 = make_ranked("Second candidate content", 0.8, 2)  # len 24 (oversized, exceeds 25 max)
    cand3 = make_ranked("Third text", 0.7, 3)  # len 10 (fits after cand2 skip: 11 + 10 = 21 <= 25)
    cand4 = make_ranked("Fourth", 0.6, 4)  # len 6 (fits? 21 + 6 = 27 > 25, skipped)

    context, used_memories = composer.compose_context([cand1, cand2, cand3, cand4])

    # Verify selection: cand1 and cand3 are selected (cand2 skipped as oversized, cand4 skipped as exceeding remaining budget)
    assert len(used_memories) == 2
    assert used_memories[0].content == "First short"
    assert used_memories[1].content == "Third text"

    # Verify rank preservation (reason templates use original ranks)
    assert "Rank #1" in used_memories[0].reason
    assert "Rank #3" in used_memories[1].reason

    # Verify exact Markdown prompt context formatting
    expected_context = "- (semantic) First short\n- (semantic) Third text"
    assert context == expected_context


def test_composer_exact_max_characters_fit():
    def make_ranked(content: str) -> RankedCandidate:
        rec = make_dummy_record(content)
        bd = ScoreBreakdown(
            semantic_score=0.5, keyword_score=0.5, importance_score=0.5,
            recency_score=0.5, confidence_score=0.5, reinforcement_score=0.5
        )
        return RankedCandidate(memory=rec, final_score=0.8, score_breakdown=bd, rank=1)

    composer = ContextComposer(max_memories=5, max_characters=15)
    cand = make_ranked("Exact length 15")  # len 15
    context, used_memories = composer.compose_context([cand])
    assert len(used_memories) == 1
    assert used_memories[0].content == "Exact length 15"


def test_composer_empty_scenarios():
    composer = ContextComposer()

    # 1. Empty input list
    c_empty, um_empty = composer.compose_context([])
    assert c_empty == ""
    assert um_empty == []

    # 2. None fit budget
    def make_ranked(content: str) -> RankedCandidate:
        rec = make_dummy_record(content)
        bd = ScoreBreakdown(
            semantic_score=0.5, keyword_score=0.5, importance_score=0.5,
            recency_score=0.5, confidence_score=0.5, reinforcement_score=0.5
        )
        return RankedCandidate(memory=rec, final_score=0.8, score_breakdown=bd, rank=1)

    composer_tight = ContextComposer(max_memories=5, max_characters=10)
    cand = make_ranked("This content is 23 characters")
    c_tight, um_tight = composer_tight.compose_context([cand])
    assert c_tight == ""
    assert um_tight == []


def test_composer_reason_generation_logic():
    composer = ContextComposer()

    def make_ranked(score: float, semantic: float, keyword: float, rank: int) -> RankedCandidate:
        rec = make_dummy_record()
        bd = ScoreBreakdown(
            semantic_score=semantic,
            keyword_score=keyword,
            importance_score=0.5,
            recency_score=0.5,
            confidence_score=0.5,
            reinforcement_score=0.5,
        )
        return RankedCandidate(memory=rec, final_score=score, score_breakdown=bd, rank=rank)

    # Case A: Semantic-dominant (0.35 * 0.9 = 0.315 > 0.20 * 0.5 = 0.10)
    cand_sem = make_ranked(0.85, 0.9, 0.5, 1)
    _, um_sem = composer.compose_context([cand_sem])
    assert "Semantically relevant to the query" in um_sem[0].reason
    assert "(Score: 0.85)" in um_sem[0].reason

    # Case B: Lexical-dominant (0.20 * 0.9 = 0.18 > 0.35 * 0.3 = 0.105)
    cand_lex = make_ranked(0.62, 0.3, 0.9, 2)
    _, um_lex = composer.compose_context([cand_lex])
    assert "Lexically relevant to the query" in um_lex[0].reason
    assert "(Score: 0.62)" in um_lex[0].reason

    # Case C: Fallback Lexical-dominant (semantic=0.0, keyword=0.8 -> keyword is higher)
    cand_fall = make_ranked(0.42, 0.0, 0.8, 1)
    _, um_fall = composer.compose_context([cand_fall])
    assert "Lexically relevant to the query" in um_fall[0].reason
    assert "(Score: 0.42)" in um_fall[0].reason

    # Case D: Balanced contribution (0.35 * 0.4 = 0.14 == 0.20 * 0.7 = 0.14)
    cand_bal = make_ranked(0.60, 0.4, 0.7, 3)
    _, um_bal = composer.compose_context([cand_bal])
    assert "Balanced relevance context" in um_bal[0].reason
    assert "(Score: 0.60)" in um_bal[0].reason


# ── RetrievalCoordinator Tests ────────────────────────────────────────────────

class MockEmbeddingService(EmbeddingService):
    def __init__(self, vector: Optional[List[float]] = None, should_fail: bool = False) -> None:
        self.vector = vector or [0.1] * 1536
        self.should_fail = should_fail
        self.called_text = None

    async def generate_embedding(self, text: str) -> List[float]:
        self.called_text = text
        if self.should_fail:
            raise RuntimeError("Fake embedding provider error")
        return self.vector


class MockRetriever:
    def __init__(self, candidates: List[RetrievalCandidate], should_fail: bool = False) -> None:
        self.candidates = candidates
        self.should_fail = should_fail
        self.called_args = {}

    async def retrieve(
        self,
        tenant_id: str,
        user_id: str,
        query_text: str,
        query_embedding: Optional[List[float]],
        candidate_limit: int = 50,
    ) -> List[RetrievalCandidate]:
        self.called_args = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "query_text": query_text,
            "query_embedding": query_embedding,
            "candidate_limit": candidate_limit,
        }
        if self.should_fail:
            raise ValueError("Fake retriever validation error")
        return self.candidates


class MockRanker:
    def __init__(self, ranked: List[RankedCandidate], should_fail: bool = False) -> None:
        self.ranked = ranked
        self.should_fail = should_fail
        self.called_args = {}

    def rank(self, candidates: List[RetrievalCandidate], now: datetime) -> List[RankedCandidate]:
        self.called_args = {"candidates": candidates, "now": now}
        if self.should_fail:
            raise TypeError("Fake ranker validation error")
        return self.ranked


class MockContextComposer:
    def __init__(self, context: str, used_memories: List[UsedMemory], should_fail: bool = False) -> None:
        self.context = context
        self.used_memories = used_memories
        self.should_fail = should_fail
        self.called_args = {}

    def compose_context(self, candidates: List[RankedCandidate]) -> Tuple[str, List[UsedMemory]]:
        self.called_args = {"candidates": candidates}
        if self.should_fail:
            raise IndexError("Fake composer budget error")
        return self.context, self.used_memories


@pytest.mark.anyio
async def test_coordinator_temporary_chat_bypass():
    embed_service = MockEmbeddingService()
    retriever = MockRetriever([])
    ranker = MockRanker([])
    composer = MockContextComposer("context", [])

    coordinator = RetrievalCoordinator(
        embedding_service=embed_service,
        retriever=retriever,
        ranker=ranker,
        context_composer=composer,
    )

    ctx, um, mode = await coordinator.retrieve_context(
        tenant_id="tenant_x",
        user_id="user_y",
        query_text="bypass query",
        temporary_chat=True,
    )

    assert ctx == ""
    assert um == []
    assert mode == RetrievalMode.NONE

    # Verify no downstream component is called
    assert embed_service.called_text is None
    assert not retriever.called_args
    assert not ranker.called_args
    assert not composer.called_args


@pytest.mark.anyio
async def test_coordinator_hybrid_success():
    embed_vector = [0.5] * 1536
    embed_service = MockEmbeddingService(vector=embed_vector)

    dummy_cand = RetrievalCandidate(memory=make_dummy_record("test"), cosine_similarity=0.9, matched_query_terms=1, total_unique_query_terms=1)
    retriever = MockRetriever([dummy_cand])

    dummy_ranked = RankedCandidate(
        memory=dummy_cand.memory,
        final_score=0.95,
        score_breakdown=ScoreBreakdown(
            semantic_score=0.9, keyword_score=0.9, importance_score=0.5,
            recency_score=0.5, confidence_score=0.5, reinforcement_score=0.5
        ),
        rank=1,
    )
    ranker = MockRanker([dummy_ranked])

    dummy_used = UsedMemory(
        memory_id=dummy_cand.memory.id,
        content="test",
        memory_type=dummy_cand.memory.memory_type,
        score=0.95,
        reason="test reason",
        score_breakdown=dummy_ranked.score_breakdown,
        source=UsedMemorySource(kind="chat", excerpt=None),
    )
    composer = MockContextComposer("composed text", [dummy_used])

    coordinator = RetrievalCoordinator(
        embedding_service=embed_service,
        retriever=retriever,
        ranker=ranker,
        context_composer=composer,
    )

    ctx, um, mode = await coordinator.retrieve_context(
        tenant_id="tenant_a",
        user_id="user_b",
        query_text="normal query",
        temporary_chat=False,
    )

    # 1. Verify returns
    assert ctx == "composed text"
    assert um == [dummy_used]
    assert mode == RetrievalMode.HYBRID

    # 2. Verify propagation
    assert embed_service.called_text == "normal query"
    assert retriever.called_args["query_embedding"] == embed_vector
    assert retriever.called_args["tenant_id"] == "tenant_a"
    assert retriever.called_args["user_id"] == "user_b"
    assert retriever.called_args["query_text"] == "normal query"
    assert ranker.called_args["candidates"] == [dummy_cand]
    assert isinstance(ranker.called_args["now"], datetime)
    assert ranker.called_args["now"].tzinfo == timezone.utc
    assert composer.called_args["candidates"] == [dummy_ranked]


@pytest.mark.anyio
async def test_coordinator_fallback_on_embedding_exception():
    embed_service = MockEmbeddingService(should_fail=True)

    dummy_cand = RetrievalCandidate(memory=make_dummy_record("test"), cosine_similarity=None, matched_query_terms=1, total_unique_query_terms=1)
    retriever = MockRetriever([dummy_cand])

    dummy_ranked = RankedCandidate(
        memory=dummy_cand.memory,
        final_score=0.45,
        score_breakdown=ScoreBreakdown(
            semantic_score=0.0, keyword_score=0.9, importance_score=0.5,
            recency_score=0.5, confidence_score=0.5, reinforcement_score=0.5
        ),
        rank=1,
    )
    ranker = MockRanker([dummy_ranked])
    composer = MockContextComposer("fallback text", [])

    coordinator = RetrievalCoordinator(
        embedding_service=embed_service,
        retriever=retriever,
        ranker=ranker,
        context_composer=composer,
    )

    ctx, um, mode = await coordinator.retrieve_context(
        tenant_id="tenant_a",
        user_id="user_b",
        query_text="fail query",
        temporary_chat=False,
    )

    # Verify fallback mode and outputs
    assert ctx == "fallback text"
    assert um == []
    assert mode == RetrievalMode.FALLBACK

    # Verify query_embedding=None was passed to Retriever
    assert retriever.called_args["query_embedding"] is None
    assert ranker.called_args["candidates"] == [dummy_cand]


@pytest.mark.anyio
async def test_coordinator_narrow_exception_propagation():
    # Downstream exceptions should propagate and not be swallowed or converted to fallback.
    embed_service = MockEmbeddingService()

    # Case A: Retriever raises ValueError
    retriever_fail = MockRetriever([], should_fail=True)
    ranker = MockRanker([])
    composer = MockContextComposer("context", [])
    coordinator_retriever_fail = RetrievalCoordinator(embed_service, retriever_fail, ranker, composer)

    with pytest.raises(ValueError, match="Fake retriever validation error"):
        await coordinator_retriever_fail.retrieve_context("t", "u", "q")

    # Case B: Ranker raises TypeError
    retriever = MockRetriever([])
    ranker_fail = MockRanker([], should_fail=True)
    coordinator_ranker_fail = RetrievalCoordinator(embed_service, retriever, ranker_fail, composer)

    with pytest.raises(TypeError, match="Fake ranker validation error"):
        await coordinator_ranker_fail.retrieve_context("t", "u", "q")

    # Case C: Composer raises IndexError
    composer_fail = MockContextComposer("", [], should_fail=True)
    coordinator_composer_fail = RetrievalCoordinator(embed_service, retriever, ranker, composer_fail)

    with pytest.raises(IndexError, match="Fake composer budget error"):
        await coordinator_composer_fail.retrieve_context("t", "u", "q")


@pytest.mark.anyio
async def test_coordinator_invalid_vector_dimension_propagates():
    # If the embedding service returns an invalid dimension, it does not raise.
    # The Coordinator must proceed to call Retriever. If Retriever/Repository raises a ValueError, it propagates.
    invalid_vector = [0.1] * 100
    embed_service = MockEmbeddingService(vector=invalid_vector)

    class DimensionRejectingRetriever:
        async def retrieve(self, tenant_id, user_id, query_text, query_embedding, candidate_limit=50):
            if query_embedding is not None and len(query_embedding) != 1536:
                raise ValueError("query_embedding must be exactly 1536 dimensions")
            return []

    retriever = DimensionRejectingRetriever()
    ranker = MockRanker([])
    composer = MockContextComposer("", [])

    coordinator = RetrievalCoordinator(embed_service, retriever, ranker, composer)

    with pytest.raises(ValueError, match="query_embedding must be exactly 1536 dimensions"):
        await coordinator.retrieve_context("t", "u", "q")


@pytest.mark.anyio
async def test_coordinator_empty_results_preserve_modes():
    # HYBRID with 0 results remains HYBRID
    embed_service = MockEmbeddingService()
    retriever = MockRetriever([])
    ranker = MockRanker([])
    composer = MockContextComposer("", [])

    coordinator = RetrievalCoordinator(embed_service, retriever, ranker, composer)
    _, _, mode_hybrid = await coordinator.retrieve_context("t", "u", "q")
    assert mode_hybrid == RetrievalMode.HYBRID

    # FALLBACK with 0 results remains FALLBACK
    embed_fail = MockEmbeddingService(should_fail=True)
    coordinator_fail = RetrievalCoordinator(embed_fail, retriever, ranker, composer)
    _, _, mode_fallback = await coordinator_fail.retrieve_context("t", "u", "q")
    assert mode_fallback == RetrievalMode.FALLBACK
