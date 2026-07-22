import os
import pytest
import httpx
import uuid
from typing import List
from fastapi.testclient import TestClient

from app.main import app
from app.runtime import get_retrieval_coordinator
from app.domain import MemoryRecord, MemoryStatus, MemoryType, Sensitivity, PolicyDecision
from app.repositories.memory import InMemoryMemoryRepository
from app.services.retrieval import RetrievalCoordinator, Retriever, Ranker, ContextComposer
from app.services.embedding import EmbeddingService
from app.domain.enums import RetrievalMode

client = TestClient(app)


# ---------------------------------------------------------------------------
# TEST-LOCAL FAKES
# ---------------------------------------------------------------------------

class FakeEmbeddingService(EmbeddingService):
    def __init__(self, vector: List[float] = None, fail: bool = False):
        self.vector = vector or [0.1] * 1536
        self.fail = fail
        self.call_count = 0

    async def generate_embedding(self, text: str) -> List[float]:
        self.call_count += 1
        if self.fail:
            raise RuntimeError("Fake embedding generation failed.")
        return self.vector


# ---------------------------------------------------------------------------
# AUTO-CLEANUP FIXTURES
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def setup_gateway_dependencies():
    # Setup a default coordinator with a fake embedding service and an empty repo
    # so that basic validation/request tests don't contact OpenAI or raise ValueError
    fake_repo = InMemoryMemoryRepository()
    fake_emb = FakeEmbeddingService()
    coordinator = RetrievalCoordinator(
        embedding_service=fake_emb,
        retriever=Retriever(fake_repo),
        ranker=Ranker(),
        context_composer=ContextComposer(),
    )

    app.dependency_overrides[get_retrieval_coordinator] = lambda: coordinator
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# TEST CASES
# ---------------------------------------------------------------------------

def test_gateway_app_importable_and_routes_exposed():
    # 1. Verify app importable
    assert app is not None

    # 2. Verify POST /api/chat is present in routes
    routes = [route.path for route in app.routes]
    assert "/api/chat" in routes


def test_gateway_chat_valid_request():
    payload = {
        "tenant_id": "tenant_test",
        "user_id": "user_test",
        "message": "Hello from testing!",
        "temporary_chat": False,
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "assistant_message" in data
    assert data["assistant_message"] == "Understood."
    assert "used_memories" in data
    assert data["used_memories"] == []
    assert "candidate_memories" in data
    assert data["candidate_memories"] == []
    assert "audit_event_ids" in data
    assert data["audit_event_ids"] == []
    assert "temporary_chat" in data
    assert data["temporary_chat"] is False
    assert "retrieval_mode" in data
    assert data["retrieval_mode"] == "hybrid"  # Default test coordinator setup returns hybrid
    assert "trace_id" in data
    assert isinstance(data["trace_id"], str)
    assert data["trace_id"].startswith("trace-")


def test_gateway_chat_request_defaults_and_temporary_chat():
    # 1. temporary_chat omission defaults to False
    payload_omitted = {
        "tenant_id": "tenant_test",
        "user_id": "user_test",
        "message": "Hello without temporary_chat",
    }
    response_omitted = client.post("/api/chat", json=payload_omitted)
    assert response_omitted.status_code == 200
    assert response_omitted.json()["temporary_chat"] is False

    # 2. explicit temporary_chat = True accepted
    payload_true = {
        "tenant_id": "tenant_test",
        "user_id": "user_test",
        "message": "Hello with temporary_chat",
        "temporary_chat": True,
    }
    response_true = client.post("/api/chat", json=payload_true)
    assert response_true.status_code == 200
    assert response_true.json()["temporary_chat"] is True
    # If temporary_chat is True, coordinator bypasses retrieval and returns none
    assert response_true.json()["retrieval_mode"] == "none"


def test_gateway_chat_message_validation():
    # 1. Missing message
    payload_missing = {
        "tenant_id": "tenant_test",
        "user_id": "user_test",
    }
    response_missing = client.post("/api/chat", json=payload_missing)
    assert response_missing.status_code == 422

    # 2. Empty message
    payload_empty = {
        "tenant_id": "tenant_test",
        "user_id": "user_test",
        "message": "",
    }
    response_empty = client.post("/api/chat", json=payload_empty)
    assert response_empty.status_code == 422
    assert "message cannot be empty or whitespace-only" in response_empty.text

    # 3. Whitespace-only message
    payload_spaces = {
        "tenant_id": "tenant_test",
        "user_id": "user_test",
        "message": "     ",
    }
    response_spaces = client.post("/api/chat", json=payload_spaces)
    assert response_spaces.status_code == 422
    assert "message cannot be empty or whitespace-only" in response_spaces.text


def test_gateway_chat_whitespace_preservation():
    # Leading/trailing whitespace on valid message must be preserved
    payload = {
        "tenant_id": "tenant_test",
        "user_id": "user_test",
        "message": "  Hello World  ",
        "temporary_chat": False,
    }
    # We test that the request model itself does not mutate the message
    from app.routes.chat import ChatRequest
    req = ChatRequest(**payload)
    assert req.message == "  Hello World  "


def test_production_get_retrieval_coordinator_missing_key(monkeypatch):
    # Ensure OPENAI_API_KEY is not in environment
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # Requesting the production dependency should resolve successfully without throwing
    coordinator = get_retrieval_coordinator()
    assert coordinator is not None
    assert coordinator._embedding_service._api_key is None


@pytest.mark.anyio
async def test_gateway_integration_hybrid_mode():
    # Setup custom integration pipeline with fresh repo
    repo = InMemoryMemoryRepository()

    # Seed active memory with matching 1536-dim embedding vector
    vec_a = [1.0] + [0.0] * 1535
    record = MemoryRecord(
        tenant_id="tenant_test",
        user_id="user_test",
        content="Jacob loves Python.",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        embedding=vec_a,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="testing"
    )
    await repo.create(record)

    fake_emb = FakeEmbeddingService(vector=vec_a)
    coordinator = RetrievalCoordinator(
        embedding_service=fake_emb,
        retriever=Retriever(repo),
        ranker=Ranker(),
        context_composer=ContextComposer(),
    )
    app.dependency_overrides[get_retrieval_coordinator] = lambda: coordinator

    payload = {
        "tenant_id": "tenant_test",
        "user_id": "user_test",
        "message": "Python coding preferences",
        "temporary_chat": False,
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["retrieval_mode"] == "hybrid"
    assert len(data["used_memories"]) == 1
    assert data["used_memories"][0]["content"] == "Jacob loves Python."
    assert data["used_memories"][0]["memory_type"] == "semantic"
    assert data["used_memories"][0]["score"] > 0.0
    assert "score_breakdown" in data["used_memories"][0]


@pytest.mark.anyio
async def test_gateway_integration_fallback_mode():
    # Setup custom integration pipeline with fresh repo
    repo = InMemoryMemoryRepository()

    # Seed active memory for lexical matching
    record = MemoryRecord(
        tenant_id="tenant_test",
        user_id="user_test",
        content="Jacob loves Python.",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        embedding=[0.1] * 1536,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="testing"
    )
    await repo.create(record)

    # Force embedding failure
    fake_emb = FakeEmbeddingService(fail=True)
    coordinator = RetrievalCoordinator(
        embedding_service=fake_emb,
        retriever=Retriever(repo),
        ranker=Ranker(),
        context_composer=ContextComposer(),
    )
    app.dependency_overrides[get_retrieval_coordinator] = lambda: coordinator

    payload = {
        "tenant_id": "tenant_test",
        "user_id": "user_test",
        "message": "Jacob and Python",  # contains matching tokens
        "temporary_chat": False,
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["retrieval_mode"] == "fallback"
    assert len(data["used_memories"]) == 1
    assert data["used_memories"][0]["content"] == "Jacob loves Python."
    # Cosine similarity is None in fallback, which resolves to semantic_score = 0.0
    assert data["used_memories"][0]["score_breakdown"]["semantic_score"] == 0.0
    assert data["used_memories"][0]["score_breakdown"]["keyword_score"] > 0.0


@pytest.mark.anyio
async def test_gateway_integration_temporary_chat():
    repo = InMemoryMemoryRepository()
    record = MemoryRecord(
        tenant_id="tenant_test",
        user_id="user_test",
        content="Jacob loves Python.",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        embedding=[0.1] * 1536,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="testing"
    )
    await repo.create(record)

    fake_emb = FakeEmbeddingService()
    coordinator = RetrievalCoordinator(
        embedding_service=fake_emb,
        retriever=Retriever(repo),
        ranker=Ranker(),
        context_composer=ContextComposer(),
    )
    app.dependency_overrides[get_retrieval_coordinator] = lambda: coordinator

    payload = {
        "tenant_id": "tenant_test",
        "user_id": "user_test",
        "message": "Jacob loves Python.",
        "temporary_chat": True,
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["retrieval_mode"] == "none"
    assert data["used_memories"] == []
    # Verify embedding service was completely bypassed
    assert fake_emb.call_count == 0


@pytest.mark.anyio
async def test_gateway_integration_tenant_isolation():
    repo = InMemoryMemoryRepository()
    # Memory seeded for different tenant
    record = MemoryRecord(
        tenant_id="tenant_other",
        user_id="user_test",
        content="Jacob loves Python.",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        embedding=[1.0] + [0.0]*1535,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="testing"
    )
    await repo.create(record)

    fake_emb = FakeEmbeddingService(vector=[1.0] + [0.0]*1535)
    coordinator = RetrievalCoordinator(
        embedding_service=fake_emb,
        retriever=Retriever(repo),
        ranker=Ranker(),
        context_composer=ContextComposer(),
    )
    app.dependency_overrides[get_retrieval_coordinator] = lambda: coordinator

    payload = {
        "tenant_id": "tenant_test",
        "user_id": "user_test",
        "message": "Jacob loves Python.",
        "temporary_chat": False,
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    assert response.json()["used_memories"] == []


@pytest.mark.anyio
async def test_gateway_integration_user_isolation():
    repo = InMemoryMemoryRepository()
    # Memory seeded for different user
    record = MemoryRecord(
        tenant_id="tenant_test",
        user_id="user_other",
        content="Jacob loves Python.",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        embedding=[1.0] + [0.0]*1535,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="testing"
    )
    await repo.create(record)

    fake_emb = FakeEmbeddingService(vector=[1.0] + [0.0]*1535)
    coordinator = RetrievalCoordinator(
        embedding_service=fake_emb,
        retriever=Retriever(repo),
        ranker=Ranker(),
        context_composer=ContextComposer(),
    )
    app.dependency_overrides[get_retrieval_coordinator] = lambda: coordinator

    payload = {
        "tenant_id": "tenant_test",
        "user_id": "user_test",
        "message": "Jacob loves Python.",
        "temporary_chat": False,
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    assert response.json()["used_memories"] == []


@pytest.mark.anyio
async def test_gateway_integration_lifecycle_isolation():
    repo = InMemoryMemoryRepository()

    from datetime import datetime, timezone

    # Seed records in pending, rejected, archived, deleted status (all non-active)
    for status in [MemoryStatus.PENDING, MemoryStatus.REJECTED, MemoryStatus.ARCHIVED, MemoryStatus.DELETED]:
        # Skip create limits or handle soft-delete properties if needed
        archived_at = datetime.now(timezone.utc) if status == MemoryStatus.ARCHIVED else None
        deleted_at = datetime.now(timezone.utc) if status == MemoryStatus.DELETED else None
        record = MemoryRecord(
            tenant_id="tenant_test",
            user_id="user_test",
            content=f"Jacob loves Python in status {status.value}.",
            memory_type=MemoryType.SEMANTIC,
            status=status,
            embedding=[1.0] + [0.0]*1535,
            archived_at=archived_at,
            deleted_at=deleted_at,
            initial_policy_decision=PolicyDecision.SAVE,
            initial_policy_reason="testing"
        )
        await repo.create(record)


    fake_emb = FakeEmbeddingService(vector=[1.0] + [0.0]*1535)
    coordinator = RetrievalCoordinator(
        embedding_service=fake_emb,
        retriever=Retriever(repo),
        ranker=Ranker(),
        context_composer=ContextComposer(),
    )
    app.dependency_overrides[get_retrieval_coordinator] = lambda: coordinator

    payload = {
        "tenant_id": "tenant_test",
        "user_id": "user_test",
        "message": "Jacob loves Python.",
        "temporary_chat": False,
    }
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    assert response.json()["used_memories"] == []


def test_gateway_integration_trace_ids():
    payload = {
        "tenant_id": "tenant_test",
        "user_id": "user_test",
        "message": "Hello trace verification!",
        "temporary_chat": False,
    }
    res1 = client.post("/api/chat", json=payload)
    res2 = client.post("/api/chat", json=payload)

    id1 = res1.json()["trace_id"]
    id2 = res2.json()["trace_id"]

    assert id1 != id2
    assert id1.startswith("trace-")
    assert id2.startswith("trace-")


@pytest.mark.anyio
async def test_gateway_integration_downstream_non_embedding_errors_propagate():
    # If the repository raises a database/runtime connection error, it must propagate
    class BrokenRepository(InMemoryMemoryRepository):
        async def search_candidates(self, *args, **kwargs):
            raise ConnectionError("Database went offline")

    repo = BrokenRepository()
    fake_emb = FakeEmbeddingService()
    coordinator = RetrievalCoordinator(
        embedding_service=fake_emb,
        retriever=Retriever(repo),
        ranker=Ranker(),
        context_composer=ContextComposer(),
    )
    app.dependency_overrides[get_retrieval_coordinator] = lambda: coordinator

    payload = {
        "tenant_id": "tenant_test",
        "user_id": "user_test",
        "message": "Jacob loves Python.",
        "temporary_chat": False,
    }

    # Downstream non-embedding exception should propagate (re-raised as 500 or raises client error)
    with pytest.raises(ConnectionError, match="Database went offline"):
        client.post("/api/chat", json=payload)
