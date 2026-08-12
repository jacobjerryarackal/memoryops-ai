import pytest
from uuid import uuid4
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.domain import MemoryRecord, MemoryStatus, MemoryType, PolicyDecision
from app.runtime import _shared_repository, _shared_audit
from app.services.idempotency import idempotency_service

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_shared_state():
    _shared_repository._records.clear()
    _shared_audit._events.clear()
    idempotency_service.clear()
    yield


def test_chat_idempotency():
    tenant = "tenant_idemp"
    user = "user_idemp"
    
    # 1. Send first request with idempotency key
    headers = {"X-Idempotency-Key": "chat_key_123"}
    payload = {
        "tenant_id": tenant,
        "user_id": user,
        "message": "remember that I like apples",
    }
    
    resp1 = client.post("/api/chat", json=payload, headers=headers)
    assert resp1.status_code == 200
    data1 = resp1.json()
    trace1 = data1["trace_id"]
    
    # 2. Send duplicate request with same key
    resp2 = client.post("/api/chat", json=payload, headers=headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    trace2 = data2["trace_id"]
    
    # Assert trace_id is cached and reused (idempotency hit)
    assert trace1 == trace2
    
    # 3. Send request with different key -> processes fresh
    headers2 = {"X-Idempotency-Key": "chat_key_456"}
    resp3 = client.post("/api/chat", json=payload, headers=headers2)
    assert resp3.status_code == 200
    data3 = resp3.json()
    trace3 = data3["trace_id"]
    
    assert trace1 != trace3


def test_patch_idempotency():
    tenant = "tenant_idemp_patch"
    user = "user_idemp_patch"
    mid = uuid4()
    
    # Pre-seed memory record
    _shared_repository._records[mid] = MemoryRecord(
        id=mid,
        tenant_id=tenant,
        user_id=user,
        content="Apples are delicious",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="seed",
    )
    
    headers = {"X-Idempotency-Key": "patch_key_1"}
    payload = {
        "tenant_id": tenant,
        "user_id": user,
        "content": "Oranges are delicious",
    }
    
    # 1. Execute patch
    resp1 = client.patch(f"/api/memories/{mid}", json=payload, headers=headers)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["content"] == "Oranges are delicious"
    
    # 2. Execute duplicate patch
    resp2 = client.patch(f"/api/memories/{mid}", json=payload, headers=headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["content"] == "Oranges are delicious"
    assert data1["updated_at"] == data2["updated_at"]


def test_delete_idempotency():
    tenant = "tenant_idemp_del"
    user = "user_idemp_del"
    mid = uuid4()
    
    # Pre-seed memory record
    _shared_repository._records[mid] = MemoryRecord(
        id=mid,
        tenant_id=tenant,
        user_id=user,
        content="Bananas are delicious",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="seed",
    )
    
    headers = {"X-Idempotency-Key": "delete_key_1"}
    payload = {
        "tenant_id": tenant,
        "user_id": user,
    }
    
    # 1. Delete record
    resp1 = client.request("DELETE", f"/api/memories/{mid}", json=payload, headers=headers)
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["status"] == "deleted"
    
    # 2. Re-send duplicate delete
    resp2 = client.request("DELETE", f"/api/memories/{mid}", json=payload, headers=headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data1["deleted_at"] == data2["deleted_at"]
