import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from uuid import uuid4

from app.domain import AuditEvent, AuditEventAction
from app.services import InMemoryAuditService

def test_audit_service_basic_recording():
    async def run():
        service = InMemoryAuditService()
        tenant = "tenant_a"
        user = "user_a"
        mem_id = uuid4()
        event_id = uuid4()

        event = AuditEvent(
            id=event_id,
            tenant_id=tenant,
            user_id=user,
            memory_id=mem_id,
            action=AuditEventAction.MEMORY_CREATED,
            reason="Saved successfully",
            metadata={"source": "api_test"}
        )

        # 1. Record successfully
        recorded = await service.record(event)
        
        # 2. Check fields preserved
        assert recorded.id == event_id
        assert recorded.tenant_id == tenant
        assert recorded.user_id == user
        assert recorded.memory_id == mem_id
        assert recorded.action == AuditEventAction.MEMORY_CREATED
        assert recorded.reason == "Saved successfully"
        assert recorded.metadata == {"source": "api_test"}
        assert recorded.created_at == event.created_at

        # 3. Check list_events
        logs = await service.list_events(tenant)
        assert len(logs) == 1
        assert logs[0].id == event_id

    asyncio.run(run())


def test_duplicate_event_rejection():
    async def run():
        service = InMemoryAuditService()
        event_id = uuid4()
        event = AuditEvent(
            id=event_id,
            tenant_id="tenant_a",
            action=AuditEventAction.MEMORY_CREATED
        )

        await service.record(event)

        # Duplicate ID should raise ValueError
        with pytest.raises(ValueError, match="Duplicate audit event ID"):
            await service.record(event)

    asyncio.run(run())


def test_deep_copy_protection():
    async def run():
        service = InMemoryAuditService()
        event_id = uuid4()
        meta = {"key": "original_val"}
        event = AuditEvent(
            id=event_id,
            tenant_id="tenant_a",
            action=AuditEventAction.MEMORY_CREATED,
            metadata=meta
        )

        recorded = await service.record(event)

        # 1. Mutate original event metadata
        meta["key"] = "mutated_val"
        
        logs1 = await service.list_events("tenant_a")
        assert logs1[0].metadata["key"] == "original_val"

        # 2. Mutate returned recorded event metadata
        recorded.metadata["key"] = "mutated_in_return"
        
        logs2 = await service.list_events("tenant_a")
        assert logs2[0].metadata["key"] == "original_val"

    asyncio.run(run())


def test_block_and_drop_with_none_memory_id():
    async def run():
        service = InMemoryAuditService()
        
        # BLOCK
        block_event = AuditEvent(
            id=uuid4(),
            tenant_id="tenant_a",
            memory_id=None,
            action=AuditEventAction.MEMORY_BLOCKED,
            reason="Secret pattern detected"
        )
        await service.record(block_event)

        # DROP
        drop_event = AuditEvent(
            id=uuid4(),
            tenant_id="tenant_a",
            memory_id=None,
            action=AuditEventAction.MEMORY_DROPPED,
            reason="Low utility"
        )
        await service.record(drop_event)

        logs = await service.list_events("tenant_a")
        assert len(logs) == 2
        assert logs[0].action == AuditEventAction.MEMORY_DROPPED
        assert logs[0].memory_id is None
        assert logs[1].action == AuditEventAction.MEMORY_BLOCKED
        assert logs[1].memory_id is None

    asyncio.run(run())


def test_scoped_filtering():
    async def run():
        service = InMemoryAuditService()
        tenant1 = "tenant_1"
        tenant2 = "tenant_2"
        user1 = "user_1"
        user2 = "user_2"
        mem1 = uuid4()
        mem2 = uuid4()

        # E1: tenant1, user1, mem1
        await service.record(AuditEvent(id=uuid4(), tenant_id=tenant1, user_id=user1, memory_id=mem1, action=AuditEventAction.MEMORY_CREATED))
        # E2: tenant1, user2, mem2
        await service.record(AuditEvent(id=uuid4(), tenant_id=tenant1, user_id=user2, memory_id=mem2, action=AuditEventAction.MEMORY_UPDATED))
        # E3: tenant2, user1, mem1
        await service.record(AuditEvent(id=uuid4(), tenant_id=tenant2, user_id=user1, memory_id=mem1, action=AuditEventAction.MEMORY_DELETED))

        # 1. Filter by tenant1
        t1_logs = await service.list_events(tenant1)
        assert len(t1_logs) == 2

        # 2. Filter by tenant1 and user1
        t1_u1_logs = await service.list_events(tenant1, user_id=user1)
        assert len(t1_u1_logs) == 1
        assert t1_u1_logs[0].user_id == user1

        # 3. Filter by tenant1 and memory_id=mem2
        t1_m2_logs = await service.list_events(tenant1, memory_id=mem2)
        assert len(t1_m2_logs) == 1
        assert t1_m2_logs[0].memory_id == mem2

        # 4. Filter by tenant2
        t2_logs = await service.list_events(tenant2)
        assert len(t2_logs) == 1
        assert t2_logs[0].tenant_id == tenant2

    asyncio.run(run())


def test_deterministic_sorting():
    async def run():
        service = InMemoryAuditService()
        tenant = "tenant_a"
        base_time = datetime.now(timezone.utc)

        # Create three events with specific created_at timestamps
        e1_id = uuid4()
        e2_id = uuid4()
        e3_id = uuid4()

        # Sort order: created_at DESC (newest first), then id ASC
        await service.record(AuditEvent(id=e1_id, tenant_id=tenant, action=AuditEventAction.MEMORY_CREATED, created_at=base_time))
        await service.record(AuditEvent(id=e2_id, tenant_id=tenant, action=AuditEventAction.MEMORY_UPDATED, created_at=base_time + timedelta(seconds=5)))
        await service.record(AuditEvent(id=e3_id, tenant_id=tenant, action=AuditEventAction.MEMORY_DELETED, created_at=base_time - timedelta(seconds=5)))

        logs = await service.list_events(tenant)
        assert len(logs) == 3
        # e2 is newest (base_time + 5s) -> index 0
        assert logs[0].id == e2_id
        # e1 is middle (base_time) -> index 1
        assert logs[1].id == e1_id
        # e3 is oldest (base_time - 5s) -> index 2
        assert logs[2].id == e3_id

        # Equal timestamp sorting (id ASC)
        service2 = InMemoryAuditService()
        # Ensure we have two distinct UUIDs that we can compare lexicographically
        id_a, id_b = sorted([uuid4(), uuid4()])
        
        await service2.record(AuditEvent(id=id_b, tenant_id=tenant, action=AuditEventAction.MEMORY_CREATED, created_at=base_time))
        await service2.record(AuditEvent(id=id_a, tenant_id=tenant, action=AuditEventAction.MEMORY_CREATED, created_at=base_time))

        logs2 = await service2.list_events(tenant)
        assert logs2[0].id == id_a
        assert logs2[1].id == id_b

    asyncio.run(run())


def test_limit_validation():
    async def run():
        service = InMemoryAuditService()
        with pytest.raises(ValueError, match="Limit must be a positive integer"):
            await service.list_events("tenant_a", limit=0)
        with pytest.raises(ValueError, match="Limit must be a positive integer"):
            await service.list_events("tenant_a", limit=-5)
    asyncio.run(run())


def test_no_mutation_apis():
    service = InMemoryAuditService()
    assert not hasattr(service, "update")
    assert not hasattr(service, "delete")
    assert not hasattr(service, "clear")
