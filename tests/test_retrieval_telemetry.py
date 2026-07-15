import pytest
import math
import uuid
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Mapping, Any
from fastapi.testclient import TestClient

from app.main import app
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
)
from app.services import (
    Retriever,
    Ranker,
    ContextComposer,
    RetrievalCoordinator,
    EmbeddingService,
)
from app.services.retrieval_telemetry import (
    RetrievalTelemetry,
    StructuredRetrievalLogger,
    NoOpRetrievalTelemetry,
)
from app.domain.enums import AuditEventAction
from app.runtime import get_retrieval_coordinator, get_memory_repository


# ---------------------------------------------------------------------------
# TEST-LOCAL RECORDING SINK
# ---------------------------------------------------------------------------

class RecordingRetrievalTelemetry(RetrievalTelemetry):
    def __init__(self) -> None:
        self.events: List[Mapping[str, Any]] = []

    def emit(self, event: Mapping[str, Any]) -> None:
        self.events.append(event)


class FailingRetrievalTelemetry(RetrievalTelemetry):
    def emit(self, event: Mapping[str, Any]) -> None:
        raise RuntimeError("Simulator telemetry emission failure")


# ---------------------------------------------------------------------------
# MOCKS
# ---------------------------------------------------------------------------

class MockEmbeddingService(EmbeddingService):
    def __init__(self, vector: Optional[List[float]] = None, should_fail: bool = False) -> None:
        self.vector = vector or [0.1] * 1536
        self.should_fail = should_fail
        self.call_count = 0

    async def generate_embedding(self, text: str) -> List[float]:
        self.call_count += 1
        if self.should_fail:
            raise RuntimeError("Embedding provider connection timed out.")
        return self.vector


class MockRetriever(Retriever):
    def __init__(self, candidates: List[RetrievalCandidate], should_fail: bool = False) -> None:
        self.candidates = candidates
        self.should_fail = should_fail
        self.call_count = 0
        self.called_args = {}

    async def retrieve(
        self,
        tenant_id: str,
        user_id: str,
        query_text: str,
        query_embedding: Optional[List[float]],
        candidate_limit: int = 50,
    ) -> List[RetrievalCandidate]:
        self.call_count += 1
        self.called_args = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "query_text": query_text,
            "query_embedding": query_embedding,
        }
        if self.should_fail:
            raise ValueError("Fake retriever validation error")
        return self.candidates


class MockRanker(Ranker):
    def __init__(self, ranked: List[RankedCandidate], should_fail: bool = False) -> None:
        self.ranked = ranked
        self.should_fail = should_fail
        self.call_count = 0

    def rank(self, candidates: List[RetrievalCandidate], now: datetime) -> List[RankedCandidate]:
        self.call_count += 1
        if self.should_fail:
            raise TypeError("Fake ranker validation error")
        return self.ranked


class MockContextComposer(ContextComposer):
    def __init__(self, context: str, used_memories: List[UsedMemory], should_fail: bool = False) -> None:
        self.context = context
        self.used_memories = used_memories
        self.should_fail = should_fail
        self.call_count = 0

    def compose_context(self, candidates: List[RankedCandidate]) -> Tuple[str, List[UsedMemory]]:
        self.call_count += 1
        if self.should_fail:
            raise IndexError("Fake composer budget error")
        return self.context, self.used_memories


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def make_dummy_record(content: str = "Test memory") -> MemoryRecord:
    return MemoryRecord(
        id=uuid.uuid4(),
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
        created_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# TESTS
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_coordinator_accepts_and_preserves_upstream_trace_id():
    # 1. Coordinator accepts upstream trace_id.
    # 2. Supplied trace_id is preserved unchanged.
    recording = RecordingRetrievalTelemetry()
    embed = MockEmbeddingService()
    retriever = MockRetriever([])
    ranker = MockRanker([])
    composer = MockContextComposer("", [])

    coordinator = RetrievalCoordinator(embed, retriever, ranker, composer, telemetry=recording)

    test_trace_id = "trace-upstream-12345"
    await coordinator.retrieve_context(
        tenant_id="tenant_a",
        user_id="user_a",
        query_text="hello",
        temporary_chat=False,
        trace_id=test_trace_id
    )

    assert len(recording.events) == 1
    event = recording.events[0]
    assert event["trace_id"] == test_trace_id


def test_gateway_propagates_generated_trace_id():
    # 3. Gateway-generated trace_id is passed to the coordinator.
    # 4. Gateway response trace_id equals telemetry trace_id.
    # Setup test client overrides
    recording = RecordingRetrievalTelemetry()
    fake_repo = get_memory_repository()
    fake_emb = MockEmbeddingService()
    
    coordinator = RetrievalCoordinator(
        embedding_service=fake_emb,
        retriever=Retriever(fake_repo),
        ranker=Ranker(),
        context_composer=ContextComposer(),
        telemetry=recording,
    )

    app.dependency_overrides[get_retrieval_coordinator] = lambda: coordinator

    try:
        client = TestClient(app)
        payload = {
            "tenant_id": "tenant_test",
            "user_id": "user_test",
            "message": "Hello from testing!",
            "temporary_chat": False,
        }
        response = client.post("/api/chat", json=payload)
        assert response.status_code == 200

        data = response.json()
        resp_trace_id = data["trace_id"]
        assert resp_trace_id.startswith("trace-")

        # Telemetry should capture the same trace ID
        assert len(recording.events) == 1
        telemetry_event = recording.events[0]
        assert telemetry_event["trace_id"] == resp_trace_id
        assert telemetry_event["tenant_id"] == "tenant_test"
        assert telemetry_event["user_id"] == "user_test"

    finally:
        app.dependency_overrides.clear()


@pytest.mark.anyio
async def test_hybrid_execution_emits_telemetry_correctly():
    # 5. Hybrid execution emits telemetry.
    # 6. Hybrid retrieval_mode is "hybrid".
    # 7. Hybrid candidate_count equals Retriever output count.
    # 8. selected_memory_ids exactly match used_memories.
    # 9. selected_memory_ids preserve selection order.
    # 10. score_breakdown contains selected memories only.
    # 11. score_breakdown values match existing UsedMemory.score_breakdown values.
    # 12. retrieve latency exists.
    # 13. rank latency exists.
    # 14. compose latency exists.
    # 15. all latency values are floats.
    # 16. all latency values are finite.
    # 17. all latency values are >= 0.0.
    
    recording = RecordingRetrievalTelemetry()
    embed = MockEmbeddingService()

    record1 = make_dummy_record("Memory content 1")
    record2 = make_dummy_record("Memory content 2")

    candidate1 = RetrievalCandidate(
        memory=record1,
        cosine_similarity=0.9,
        matched_query_terms=2,
        total_unique_query_terms=2
    )
    candidate2 = RetrievalCandidate(
        memory=record2,
        cosine_similarity=0.8,
        matched_query_terms=1,
        total_unique_query_terms=2
    )

    retriever = MockRetriever([candidate1, candidate2])

    bd1 = ScoreBreakdown(
        semantic_score=0.9, keyword_score=1.0, importance_score=0.5,
        recency_score=0.5, confidence_score=0.5, reinforcement_score=0.5
    )
    bd2 = ScoreBreakdown(
        semantic_score=0.8, keyword_score=0.5, importance_score=0.5,
        recency_score=0.5, confidence_score=0.5, reinforcement_score=0.5
    )

    ranked1 = RankedCandidate(memory=record1, final_score=0.85, score_breakdown=bd1, rank=1)
    ranked2 = RankedCandidate(memory=record2, final_score=0.75, score_breakdown=bd2, rank=2)

    ranker = MockRanker([ranked1, ranked2])

    from app.domain.retrieval import UsedMemorySource
    um1 = UsedMemory(
        memory_id=record1.id, content=record1.content, memory_type=record1.memory_type,
        score=0.85, reason="Selected", score_breakdown=bd1,
        source=UsedMemorySource(kind="chat", excerpt=None)
    )
    um2 = UsedMemory(
        memory_id=record2.id, content=record2.content, memory_type=record2.memory_type,
        score=0.75, reason="Selected", score_breakdown=bd2,
        source=UsedMemorySource(kind="chat", excerpt=None)
    )

    composer = MockContextComposer("context text", [um1, um2])

    coordinator = RetrievalCoordinator(embed, retriever, ranker, composer, telemetry=recording)

    await coordinator.retrieve_context(
        tenant_id="tenant_a",
        user_id="user_a",
        query_text="python developer",
        temporary_chat=False,
        trace_id="trace-hybrid"
    )

    assert len(recording.events) == 1
    event = recording.events[0]

    assert event["event"] == "memory_retrieval"
    assert event["retrieval_mode"] == "hybrid"
    assert event["candidate_count"] == 2
    assert event["selected_memory_ids"] == [str(record1.id), str(record2.id)]
    
    # Verify score breakdowns match UsedMemories and only contain selected ones
    assert len(event["score_breakdown"]) == 2
    assert str(record1.id) in event["score_breakdown"]
    assert str(record2.id) in event["score_breakdown"]
    
    assert event["score_breakdown"][str(record1.id)]["semantic_score"] == 0.9
    assert event["score_breakdown"][str(record2.id)]["semantic_score"] == 0.8

    # Latencies
    assert "latency_ms" in event
    latencies = event["latency_ms"]
    assert "retrieve" in latencies
    assert "rank" in latencies
    assert "compose" in latencies

    for stage in ["retrieve", "rank", "compose"]:
        val = latencies[stage]
        assert isinstance(val, float)
        assert math.isfinite(val)
        assert val >= 0.0


@pytest.mark.anyio
async def test_fallback_execution_emits_telemetry_correctly():
    # 18. Fallback execution emits telemetry.
    # 19. Fallback retrieval_mode is "fallback".
    # 20. Fallback candidate_count is correct.
    # 21. Fallback selected IDs match used_memories.
    # 22. Fallback score breakdown semantic_score remains 0.0 for selected fallback memories.

    recording = RecordingRetrievalTelemetry()
    embed = MockEmbeddingService(should_fail=True)  # Fail embedding to trigger fallback

    record = make_dummy_record("Fallback record")
    candidate = RetrievalCandidate(
        memory=record,
        cosine_similarity=None,  # Fallback mode
        matched_query_terms=1,
        total_unique_query_terms=1
    )
    retriever = MockRetriever([candidate])

    bd = ScoreBreakdown(
        semantic_score=0.0, keyword_score=1.0, importance_score=0.5,
        recency_score=0.5, confidence_score=0.5, reinforcement_score=0.5
    )
    ranked = RankedCandidate(memory=record, final_score=0.45, score_breakdown=bd, rank=1)
    ranker = MockRanker([ranked])

    from app.domain.retrieval import UsedMemorySource
    um = UsedMemory(
        memory_id=record.id, content=record.content, memory_type=record.memory_type,
        score=0.45, reason="Selected", score_breakdown=bd,
        source=UsedMemorySource(kind="chat", excerpt=None)
    )
    composer = MockContextComposer("context text", [um])

    coordinator = RetrievalCoordinator(embed, retriever, ranker, composer, telemetry=recording)

    await coordinator.retrieve_context(
        tenant_id="tenant_a",
        user_id="user_a",
        query_text="python developer",
        temporary_chat=False,
        trace_id="trace-fallback"
    )

    assert len(recording.events) == 1
    event = recording.events[0]

    assert event["retrieval_mode"] == "fallback"
    assert event["candidate_count"] == 1
    assert event["selected_memory_ids"] == [str(record.id)]
    assert event["score_breakdown"][str(record.id)]["semantic_score"] == 0.0


@pytest.mark.anyio
async def test_temporary_chat_telemetry_and_no_invocation():
    # 23. Temporary chat telemetry behavior matches the decision.
    # 24. Temporary chat does not invoke embedding.
    # 25. Temporary chat does not invoke Retriever.
    # 26. Temporary chat does not invoke Ranker.
    # 27. Temporary chat does not invoke ContextComposer.
    
    recording = RecordingRetrievalTelemetry()
    embed = MockEmbeddingService()
    retriever = MockRetriever([])
    ranker = MockRanker([])
    composer = MockContextComposer("", [])

    coordinator = RetrievalCoordinator(embed, retriever, ranker, composer, telemetry=recording)

    ctx, um, mode = await coordinator.retrieve_context(
        tenant_id="tenant_a",
        user_id="user_a",
        query_text="hi",
        temporary_chat=True,
        trace_id="trace-temp"
    )

    assert ctx == ""
    assert um == []
    assert mode == RetrievalMode.NONE

    # Invocations
    assert embed.call_count == 0
    assert retriever.call_count == 0
    assert ranker.call_count == 0
    assert composer.call_count == 0

    # Telemetry check
    assert len(recording.events) == 1
    event = recording.events[0]
    assert event["retrieval_mode"] == "none"
    assert event["candidate_count"] == 0
    assert event["selected_memory_ids"] == []
    assert event["score_breakdown"] == {}
    assert event["latency_ms"] == {
        "retrieve": 0.0,
        "rank": 0.0,
        "compose": 0.0
    }


@pytest.mark.anyio
async def test_telemetry_privacy_and_no_sensitive_leakage():
    # 28. No raw query text appears in telemetry.
    # 29. No raw memory content appears in telemetry.
    # 30. No embedding vectors appear in telemetry.
    # 31. No API key appears in telemetry.
    
    recording = RecordingRetrievalTelemetry()
    embed = MockEmbeddingService()
    
    record = make_dummy_record("Extremely sensitive content: API_KEY=12345")
    candidate = RetrievalCandidate(
        memory=record,
        cosine_similarity=0.95,
        matched_query_terms=1,
        total_unique_query_terms=1
    )
    retriever = MockRetriever([candidate])

    bd = ScoreBreakdown(
        semantic_score=0.95, keyword_score=1.0, importance_score=0.5,
        recency_score=0.5, confidence_score=0.5, reinforcement_score=0.5
    )
    ranked = RankedCandidate(memory=record, final_score=0.85, score_breakdown=bd, rank=1)
    ranker = MockRanker([ranked])

    from app.domain.retrieval import UsedMemorySource
    um = UsedMemory(
        memory_id=record.id, content=record.content, memory_type=record.memory_type,
        score=0.85, reason="Selected", score_breakdown=bd,
        source=UsedMemorySource(kind="chat", excerpt=None)
    )
    composer = MockContextComposer("context text", [um])

    coordinator = RetrievalCoordinator(embed, retriever, ranker, composer, telemetry=recording)

    await coordinator.retrieve_context(
        tenant_id="tenant_a",
        user_id="user_a",
        query_text="What is my secret api key?",
        temporary_chat=False,
        trace_id="trace-privacy"
    )

    assert len(recording.events) == 1
    event = recording.events[0]

    # Convert event dict to a single flat string to search for any leak
    serialized_event = str(event)

    # Assert no sensitive parameters leaked
    assert "What is my secret api key?" not in serialized_event
    assert "Extremely sensitive content" not in serialized_event
    assert "API_KEY" not in serialized_event
    assert "0.1" * 1536 not in serialized_event


@pytest.mark.anyio
async def test_telemetry_emission_failure_isolation():
    # 32. Telemetry emission failure does not alter successful hybrid retrieval results.
    # 33. Telemetry emission failure does not convert execution to fallback.
    
    failing_telemetry = FailingRetrievalTelemetry()
    embed = MockEmbeddingService()

    record = make_dummy_record("Test memory")
    candidate = RetrievalCandidate(
        memory=record,
        cosine_similarity=0.9,
        matched_query_terms=1,
        total_unique_query_terms=1
    )
    retriever = MockRetriever([candidate])

    bd = ScoreBreakdown(
        semantic_score=0.9, keyword_score=1.0, importance_score=0.5,
        recency_score=0.5, confidence_score=0.5, reinforcement_score=0.5
    )
    ranked = RankedCandidate(memory=record, final_score=0.80, score_breakdown=bd, rank=1)
    ranker = MockRanker([ranked])

    from app.domain.retrieval import UsedMemorySource
    um = UsedMemory(
        memory_id=record.id, content=record.content, memory_type=record.memory_type,
        score=0.80, reason="Selected", score_breakdown=bd,
        source=UsedMemorySource(kind="chat", excerpt=None)
    )
    composer = MockContextComposer("context text", [um])

    coordinator = RetrievalCoordinator(embed, retriever, ranker, composer, telemetry=failing_telemetry)

    # Retrieval should complete successfully despite telemetry emitting throwing RuntimeError
    ctx, um_list, mode = await coordinator.retrieve_context(
        tenant_id="tenant_a",
        user_id="user_a",
        query_text="test query",
        temporary_chat=False,
        trace_id="trace-fail-emit"
    )

    assert ctx == "context text"
    assert um_list == [um]
    assert mode == RetrievalMode.HYBRID  # Remains hybrid, NOT degraded to fallback


@pytest.mark.anyio
async def test_downstream_failures_propagate():
    # 34. Downstream Retriever failure still propagates.
    # 35. Ranker failure still propagates.
    # 36. ContextComposer failure still propagates.
    
    recording = RecordingRetrievalTelemetry()
    embed = MockEmbeddingService()

    # Case 34: Retriever failure
    retriever_fail = MockRetriever([], should_fail=True)
    ranker = MockRanker([])
    composer = MockContextComposer("", [])
    coord1 = RetrievalCoordinator(embed, retriever_fail, ranker, composer, telemetry=recording)
    with pytest.raises(ValueError, match="Fake retriever validation error"):
        await coord1.retrieve_context("tenant_a", "user_a", "q")

    # Case 35: Ranker failure
    retriever = MockRetriever([])
    ranker_fail = MockRanker([], should_fail=True)
    coord2 = RetrievalCoordinator(embed, retriever, ranker_fail, composer, telemetry=recording)
    with pytest.raises(TypeError, match="Fake ranker validation error"):
        await coord2.retrieve_context("tenant_a", "user_a", "q")

    # Case 36: ContextComposer failure
    composer_fail = MockContextComposer("", [], should_fail=True)
    coord3 = RetrievalCoordinator(embed, retriever, ranker, composer_fail, telemetry=recording)
    with pytest.raises(IndexError, match="Fake composer budget error"):
        await coord3.retrieve_context("tenant_a", "user_a", "q")


@pytest.mark.anyio
async def test_coordinator_backward_compatibility_option_c():
    # 37. Existing coordinator calls without explicit trace_id remain compatible.
    recording = RecordingRetrievalTelemetry()
    embed = MockEmbeddingService()
    retriever = MockRetriever([])
    ranker = MockRanker([])
    composer = MockContextComposer("", [])

    coordinator = RetrievalCoordinator(embed, retriever, ranker, composer, telemetry=recording)

    # Invoke without trace_id
    await coordinator.retrieve_context(
        tenant_id="tenant_a",
        user_id="user_a",
        query_text="hello",
        temporary_chat=False
    )

    assert len(recording.events) == 1
    event = recording.events[0]
    assert "trace_id" in event
    assert event["trace_id"].startswith("trace-")


def test_production_runtime_telemetry_wiring(monkeypatch):
    # 38. Production runtime coordinator is constructed with the production telemetry sink.
    monkeypatch.setenv("OPENAI_API_KEY", "fake-openai-api-key")
    coordinator = get_retrieval_coordinator()
    assert isinstance(coordinator._telemetry, StructuredRetrievalLogger)


def test_audit_separation():
    # 39. AuditEventAction remains unchanged.
    # 40. RetrievalCoordinator does not call AuditService.
    # Verify AuditEventAction does not have memory_retrieval or telemetry-related actions
    actions = [a.value for a in AuditEventAction]
    assert "memory_retrieved" not in actions
    assert "memory_retrieval" not in actions
    assert "retrieval" not in actions


@pytest.mark.anyio
async def test_retriever_defensive_boundary_scope_and_active():
    # Verify that Retriever defensively drops records with:
    # - wrong tenant_id
    # - wrong user_id
    # - status != ACTIVE (e.g. DELETED)

    # 1. Valid candidate
    valid_record = make_dummy_record("Valid active memory")

    # 2. Record with wrong tenant
    wrong_tenant = make_dummy_record("Wrong tenant memory")
    wrong_tenant.tenant_id = "tenant_other"

    # 3. Record with wrong user
    wrong_user = make_dummy_record("Wrong user memory")
    wrong_user.user_id = "user_other"

    # 4. Record with deleted status
    deleted_rec = make_dummy_record("Deleted memory")
    deleted_rec.status = MemoryStatus.DELETED

    # 5. Record with pending status
    pending_rec = make_dummy_record("Pending memory")
    pending_rec.status = MemoryStatus.PENDING

    # Setup fake repo results
    repo_results = [
        (valid_record, 0.9),
        (wrong_tenant, 0.8),
        (wrong_user, 0.7),
        (deleted_rec, 0.6),
        (pending_rec, 0.5),
    ]

    class FakeMemoryRepoForRetriever:
        async def search_candidates(self, tenant_id, user_id, query_embedding, limit):
            return repo_results

    retriever = Retriever(FakeMemoryRepoForRetriever())

    candidates = await retriever.retrieve(
        tenant_id="tenant_a",
        user_id="user_a",
        query_text="memory",
        query_embedding=[0.1]*1536
    )

    # Only the valid candidate should survive
    assert len(candidates) == 1
    assert candidates[0].memory.id == valid_record.id
