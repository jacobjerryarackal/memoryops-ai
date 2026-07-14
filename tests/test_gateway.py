import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.domain.enums import RetrievalMode

client = TestClient(app)


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
    assert data["retrieval_mode"] == "none"
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
