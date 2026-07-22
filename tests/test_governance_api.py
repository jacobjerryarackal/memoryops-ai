import uuid
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.domain import AuditEvent, AuditEventAction, MemoryRecord, MemoryStatus, MemoryType, PolicyDecision
from app.main import app
from app.runtime import _shared_audit, _shared_repository

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_shared_state():
    # Clean the process-lifetime singletons between test runs to ensure isolation
    _shared_repository._records.clear()
    _shared_audit._events.clear()
    yield


def test_api_list_memories():
    tenant = "tenant_list"
    user = "user_list"

    # Create active memory via direct repo mock insertion
    mid1 = uuid4()
    _shared_repository._records[mid1] = MemoryRecord(
        id=mid1,
        tenant_id=tenant,
        user_id=user,
        content="Active fact",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test",
    )

    # Create deleted memory (should be excluded by default)
    mid2 = uuid4()
    _shared_repository._records[mid2] = MemoryRecord(
        id=mid2,
        tenant_id=tenant,
        user_id=user,
        content="Deleted fact",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.DELETED,
        deleted_at=datetime.now(timezone.utc),
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test",
    )

    # 1. Query memories listing
    response = client.get(f"/api/memories?tenant_id={tenant}&user_id={user}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == str(mid1)

    # 2. Query with deleted status explicitly
    response_deleted = client.get(f"/api/memories?tenant_id={tenant}&user_id={user}&status=deleted")
    assert response_deleted.status_code == 200
    data_del = response_deleted.json()
    assert len(data_del) == 1
    assert data_del[0]["id"] == str(mid2)


def test_api_get_memory_by_id_and_provenance_and_audit():
    tenant = "tenant_get"
    user = "user_get"
    mid = uuid4()

    _shared_repository._records[mid] = MemoryRecord(
        id=mid,
        tenant_id=tenant,
        user_id=user,
        content="Seattle dev",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test_api",
    )

    # 1. Successful GET
    resp = client.get(f"/api/memories/{mid}?tenant_id={tenant}&user_id={user}")
    assert resp.status_code == 200
    assert resp.json()["content"] == "Seattle dev"

    # 2. Scope Mismatch -> 404 with MEMORY_NOT_FOUND error payload
    resp_mismatch = client.get(f"/api/memories/{mid}?tenant_id=wrong_tenant&user_id={user}")
    assert resp_mismatch.status_code == 404
    err_payload = resp_mismatch.json()
    assert err_payload["error"]["code"] == "MEMORY_NOT_FOUND"

    # 3. Successful Provenance GET
    resp_prov = client.get(f"/api/memories/{mid}/provenance?tenant_id={tenant}&user_id={user}")
    assert resp_prov.status_code == 200
    assert resp_prov.json()["initial_policy_reason"] == "test_api"

    # 4. Successful Audit GET
    resp_audit = client.get(f"/api/memories/{mid}/audit?tenant_id={tenant}&user_id={user}")
    assert resp_audit.status_code == 200
    assert isinstance(resp_audit.json(), list)


def test_api_patch_memory_transitions_and_safety():
    tenant = "tenant_patch"
    user = "user_patch"
    mid = uuid4()

    _shared_repository._records[mid] = MemoryRecord(
        id=mid,
        tenant_id=tenant,
        user_id=user,
        content="Tacoma dev",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.PENDING,
        initial_policy_decision=PolicyDecision.PENDING_APPROVAL,
        initial_policy_reason="review queue",
    )

    # 1. Approve memory (pending -> active)
    resp = client.patch(
        f"/api/memories/{mid}",
        json={
            "tenant_id": tenant,
            "user_id": user,
            "status": "active"
        }
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"

    # 2. Content change with safety block (contains secrets) -> 400 POLICY_BLOCKED
    resp_blocked = client.patch(
        f"/api/memories/{mid}",
        json={
            "tenant_id": tenant,
            "user_id": user,
            "content": "My token sk-proj-123456789012345678901234"
        }
    )
    assert resp_blocked.status_code == 400
    assert resp_blocked.json()["error"]["code"] == "POLICY_BLOCKED"

    # 3. Content update success (embedding cleared)
    resp_ok = client.patch(
        f"/api/memories/{mid}",
        json={
            "tenant_id": tenant,
            "user_id": user,
            "content": "Olympia dev"
        }
    )
    assert resp_ok.status_code == 200
    assert resp_ok.json()["content"] == "Olympia dev"
    assert resp_ok.json()["embedding"] is None


def test_api_delete_memory_idempotent():
    tenant = "tenant_delete"
    user = "user_delete"
    mid = uuid4()

    _shared_repository._records[mid] = MemoryRecord(
        id=mid,
        tenant_id=tenant,
        user_id=user,
        content="Portland dev",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test",
    )

    # 1. First DELETE succeeds and returns 200 with deleted_at timestamp
    resp = client.request(
        "DELETE",
        f"/api/memories/{mid}",
        json={
            "tenant_id": tenant,
            "user_id": user
        }
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "deleted"
    assert data["deleted_at"] != ""

    first_deleted_at = data["deleted_at"]

    # 2. Second DELETE is idempotent, returns same deleted_at
    resp_again = client.request(
        "DELETE",
        f"/api/memories/{mid}",
        json={
            "tenant_id": tenant,
            "user_id": user
        }
    )
    assert resp_again.status_code == 200
    assert resp_again.json()["deleted_at"] == first_deleted_at


def test_api_audit_and_metrics():
    tenant = "tenant_stats"
    user = "user_stats"

    # Insert some audit logs directly
    audit_id = uuid4()
    _shared_audit._events[audit_id] = AuditEvent(
        id=audit_id,
        tenant_id=tenant,
        user_id=user,
        action=AuditEventAction.MEMORY_CREATED,
        reason="Initial",
        metadata={},
        created_at=datetime.now(timezone.utc)
    )

    # Query audit list
    resp_audit = client.get(f"/api/audit?tenant_id={tenant}")
    assert resp_audit.status_code == 200
    assert len(resp_audit.json()) == 1

    # Query metrics
    resp_metrics = client.get(f"/api/metrics?tenant_id={tenant}")
    assert resp_metrics.status_code == 200
    assert resp_metrics.json()["audit_events"] == 1
