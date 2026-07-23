import logging
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.runtime import _shared_repository
from app.services.openai_embedding import OpenAIEmbeddingService

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_shared_state():
    _shared_repository._records.clear()
    yield


def test_api_key_present_semantic_retrieval(monkeypatch):
    # Mock generate_embedding to simulate successful API call
    dummy_vector = [0.05] * 1536
    async def mock_generate_embedding(self, text: str):
        return dummy_vector
    monkeypatch.setattr(OpenAIEmbeddingService, "generate_embedding", mock_generate_embedding)

    # Set mock key in environment
    monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-env-key")

    payload = {
        "tenant_id": "tenant_fallback_test",
        "user_id": "user_fallback_test",
        "message": "Verify semantic mode runs",
        "temporary_chat": False
    }

    resp = client.post("/api/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["retrieval_mode"] == "hybrid"


def test_api_key_absent_fallback_retrieval(monkeypatch):
    # Ensure OPENAI_API_KEY is not set
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    payload = {
        "tenant_id": "tenant_fallback_test",
        "user_id": "user_fallback_test",
        "message": "Verify fallback mode runs",
        "temporary_chat": False
    }

    # Verify no HTTP 500 occurs, instead a successful 200 with fallback mode
    resp = client.post("/api/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["retrieval_mode"] == "fallback"


def test_provider_runtime_failure_fallback_retrieval(monkeypatch, caplog):
    # Mock generate_embedding to simulate OpenAI API runtime error
    async def mock_failed_generate_embedding(self, text: str):
        raise RuntimeError("OpenAI API connection timed out.")
    monkeypatch.setattr(OpenAIEmbeddingService, "generate_embedding", mock_failed_generate_embedding)

    # Set key in environment so initialization succeeds but runtime fails
    monkeypatch.setenv("OPENAI_API_KEY", "sk-mock-env-key")

    payload = {
        "tenant_id": "tenant_fallback_test",
        "user_id": "user_fallback_test",
        "message": "Verify runtime exception handled",
        "temporary_chat": False
    }

    with caplog.at_level(logging.WARNING):
        resp = client.post("/api/chat", json=payload)

    # Verify no HTTP 500 occurs, instead a successful 200 with fallback mode
    assert resp.status_code == 200
    data = resp.json()
    assert data["retrieval_mode"] == "fallback"


def test_explicit_fallback_provider_retrieval(monkeypatch):
    # Set EMBEDDING_PROVIDER = fallback
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fallback")

    payload = {
        "tenant_id": "tenant_fallback_test",
        "user_id": "user_fallback_test",
        "message": "Verify explicit fallback provider works",
        "temporary_chat": False
    }

    resp = client.post("/api/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["retrieval_mode"] == "fallback"
