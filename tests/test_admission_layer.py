import pytest
from datetime import datetime, timezone
from uuid import uuid4

from app.domain import MemoryRecord, MemoryStatus, MemoryType, PolicyDecision
from app.domain.retrieval import RetrievalCandidate, RankedCandidate, ScoreBreakdown
from app.services.retrieval import (
    ContextAdmissionLayer, PIIRedactionPolicy, LengthTruncationPolicy,
    ImportanceDownrankPolicy, KeywordDenyPolicy, RetrievalCoordinator,
    Retriever, Ranker, ContextComposer
)
from app.repositories.base import MemoryRepository


class DummyMemoryRepository(MemoryRepository):
    def __init__(self, records):
        self.records = records

    async def create(self, record):
        pass
    async def get_by_id(self, memory_id, tenant_id, user_id):
        pass
    async def update(self, record):
        pass
    async def delete(self, memory_id, tenant_id, user_id):
        pass
    async def list_by_status(self, tenant_id, user_id, status):
        pass
    async def list_active(self, tenant_id, user_id, limit):
        pass
    async def get_active_by_slot(self, tenant_id, user_id, memory_type, identity_slot):
        pass
    async def search_candidates(self, tenant_id, user_id, query_embedding, limit):
        # Return list of tuples: (record, similarity)
        return [(r, 0.9) for r in self.records]


class DummyEmbeddingService:
    async def generate_embedding(self, text):
        return [0.1] * 1536


@pytest.fixture
def mock_candidate():
    rec = MemoryRecord(
        id=uuid4(),
        tenant_id="tenant_a",
        user_id="user_a",
        content="Contact me at test@example.com or call 123-456-7890. API key=mysecrettoken12345",
        memory_type=MemoryType.SEMANTIC,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test",
        importance=2
    )
    return RankedCandidate(
        memory=rec,
        final_score=0.8,
        score_breakdown=ScoreBreakdown(
            semantic_score=0.8,
            keyword_score=0.5,
            importance_score=0.2,
            recency_score=0.9,
            confidence_score=0.9,
            reinforcement_score=0.5
        ),
        rank=1
    )


def test_pii_redaction(mock_candidate):
    policy = PIIRedactionPolicy()
    decision, val = policy.evaluate(mock_candidate)
    
    assert decision == "redact"
    assert "[EMAIL_REDACTED]" in val
    assert "[PHONE_REDACTED]" in val
    assert "[SECRET_REDACTED]" in val
    assert "test@example.com" not in val
    assert "123-456-7890" not in val


def test_length_truncation(mock_candidate):
    policy = LengthTruncationPolicy(max_length=15)
    decision, val = policy.evaluate(mock_candidate)
    
    assert decision == "truncate"
    assert val == "Contact me at t..."


def test_importance_downrank(mock_candidate):
    policy = ImportanceDownrankPolicy(threshold=3, penalty=0.3)
    decision, val = policy.evaluate(mock_candidate)
    
    assert decision == "downrank"
    assert val == "0.3"


def test_keyword_deny(mock_candidate):
    policy = KeywordDenyPolicy(forbidden_keywords=["api key", "forbidden"])
    decision, val = policy.evaluate(mock_candidate)
    
    assert decision == "deny"
    assert "api key" in val


def test_admission_layer_clones_records_to_prevent_pollution(mock_candidate):
    layer = ContextAdmissionLayer([PIIRedactionPolicy(), LengthTruncationPolicy(max_length=20)])
    admitted = layer.admit([mock_candidate])
    
    assert len(admitted) == 1
    assert admitted[0].memory.content == "Contact me at [EMAIL..."
    # Verify the original mock candidate content is unchanged
    assert mock_candidate.memory.content == "Contact me at test@example.com or call 123-456-7890. API key=mysecrettoken12345"


@pytest.mark.anyio
async def test_coordinator_integration_with_admission():
    # Setup dummy database with 2 candidates
    rec1 = MemoryRecord(
        id=uuid4(),
        tenant_id="t1",
        user_id="u1",
        content="This contains forbidden_word and email test@example.com",
        memory_type=MemoryType.SEMANTIC,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test",
        importance=8
    )
    rec2 = MemoryRecord(
        id=uuid4(),
        tenant_id="t1",
        user_id="u1",
        content="Safe memory content.",
        memory_type=MemoryType.SEMANTIC,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test",
        importance=1  # Low importance downranks
    )
    
    repo = DummyMemoryRepository([rec1, rec2])
    retriever = Retriever(repo)
    ranker = Ranker()
    composer = ContextComposer()
    
    # Configure admission layer
    policies = [
        KeywordDenyPolicy(["forbidden_word"]),
        PIIRedactionPolicy(),
        ImportanceDownrankPolicy(threshold=3, penalty=0.5)
    ]
    admission = ContextAdmissionLayer(policies)
    
    coordinator = RetrievalCoordinator(
        embedding_service=DummyEmbeddingService(),
        retriever=retriever,
        ranker=ranker,
        context_composer=composer,
        admission_layer=admission
    )
    
    context, used_memories, mode = await coordinator.retrieve_context(
        tenant_id="t1",
        user_id="u1",
        query_text="query"
    )
    
    # 1. rec1 must be dropped entirely due to forbidden keyword
    assert "forbidden_word" not in context
    assert len(used_memories) == 1
    
    # 2. rec2 should be the only used memory
    assert used_memories[0].memory_id == rec2.id
    assert "Safe memory content." in context
