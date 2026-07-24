import pytest
import asyncio
import math
from datetime import datetime, timezone, timedelta
from uuid import uuid4, UUID
import dotenv

from app.domain import MemoryRecord, MemoryStatus, MemoryType, Sensitivity, PolicyDecision, AuditEvent, AuditEventAction
from app.repositories.postgres import PostgreSQLMemoryRepository, PostgreSQLAuditRepository
from app.repositories.postgres_connection import db_manager

# Load environment configuration
dotenv.load_dotenv()


async def setup_db():
    """Helper to initialize the database connection pool in the active event loop and truncate tables."""
    if db_manager.pool is not None:
        if db_manager.pool._loop.is_closed():
            db_manager.pool = None
        else:
            try:
                await db_manager.close()
            except Exception:
                db_manager.pool = None
    await db_manager.initialize()
    async with db_manager.pool.acquire() as conn:
        await conn.execute("TRUNCATE TABLE memories, memory_audit_logs CASCADE;")


def test_postgres_duplicate_create_rejection():
    async def run():
        await setup_db()
        repo = PostgreSQLMemoryRepository()
        rec_id = uuid4()
        rec = MemoryRecord(
            id=rec_id,
            tenant_id="tenant_a",
            user_id="user_a",
            content="I prefer Python.",
            memory_type=MemoryType.SEMANTIC,
            initial_policy_decision=PolicyDecision.SAVE,
            initial_policy_reason="test"
        )
        await repo.create(rec)
        with pytest.raises(ValueError, match="Duplicate key"):
            await repo.create(rec)
    asyncio.run(run())


def test_postgres_scope_isolation():
    async def run():
        await setup_db()
        repo = PostgreSQLMemoryRepository()
        rec_id = uuid4()
        rec = MemoryRecord(
            id=rec_id,
            tenant_id="tenant_a",
            user_id="user_a",
            content="I prefer Python.",
            memory_type=MemoryType.SEMANTIC,
            initial_policy_decision=PolicyDecision.SAVE,
            initial_policy_reason="test"
        )
        await repo.create(rec)

        # 1. get_by_id under wrong scope
        assert await repo.get_by_id(rec_id, "tenant_b", "user_b") is None

        # 2. delete under wrong scope
        with pytest.raises(ValueError, match="Scope mismatch"):
            await repo.delete(rec_id, "tenant_b", "user_b")
    asyncio.run(run())


def test_postgres_scope_transfer_rejection():
    async def run():
        await setup_db()
        repo = PostgreSQLMemoryRepository()
        rec_id = uuid4()
        rec = MemoryRecord(
            id=rec_id,
            tenant_id="tenant_a",
            user_id="user_a",
            content="I prefer Python.",
            memory_type=MemoryType.SEMANTIC,
            initial_policy_decision=PolicyDecision.SAVE,
            initial_policy_reason="test"
        )
        created = await repo.create(rec)

        hijacked = created.model_copy(deep=True)
        hijacked.tenant_id = "tenant_b"
        with pytest.raises(ValueError, match="Scope mismatch"):
            await repo.update(hijacked)
    asyncio.run(run())


def test_postgres_terminal_deletion():
    async def run():
        await setup_db()
        repo = PostgreSQLMemoryRepository()
        rec_id = uuid4()
        rec = MemoryRecord(
            id=rec_id,
            tenant_id="tenant_a",
            user_id="user_a",
            content="I prefer Python.",
            memory_type=MemoryType.SEMANTIC,
            initial_policy_decision=PolicyDecision.SAVE,
            initial_policy_reason="test"
        )
        await repo.create(rec)
        deleted = await repo.delete(rec_id, "tenant_a", "user_a")
        assert deleted.status == MemoryStatus.DELETED
        assert deleted.deleted_at is not None

        to_update = deleted.model_copy(deep=True)
        to_update.status = MemoryStatus.ACTIVE
        with pytest.raises(ValueError, match="Terminal deletion"):
            await repo.update(to_update)
    asyncio.run(run())


def test_postgres_update_cannot_perform_deletion():
    async def run():
        await setup_db()
        repo = PostgreSQLMemoryRepository()
        rec_id = uuid4()
        rec = MemoryRecord(
            id=rec_id,
            tenant_id="tenant_a",
            user_id="user_a",
            content="I prefer Python.",
            memory_type=MemoryType.SEMANTIC,
            initial_policy_decision=PolicyDecision.SAVE,
            initial_policy_reason="test"
        )
        created = await repo.create(rec)

        to_delete = created.model_copy(deep=True)
        to_delete.status = MemoryStatus.DELETED
        to_delete.deleted_at = datetime.now(timezone.utc)
        with pytest.raises(ValueError, match="Segregation of deletion"):
            await repo.update(to_delete)
    asyncio.run(run())


def test_postgres_immutable_admission_provenance():
    async def run():
        await setup_db()
        repo = PostgreSQLMemoryRepository()
        rec_id = uuid4()
        rec = MemoryRecord(
            id=rec_id,
            tenant_id="tenant_a",
            user_id="user_a",
            content="I prefer Python.",
            memory_type=MemoryType.SEMANTIC,
            initial_policy_decision=PolicyDecision.SAVE,
            initial_policy_reason="test"
        )
        created = await repo.create(rec)

        # 1. Change initial_policy_decision
        hijack_decision = created.model_copy(deep=True)
        hijack_decision.initial_policy_decision = PolicyDecision.BLOCK
        with pytest.raises(ValueError, match="Immutable admission provenance"):
            await repo.update(hijack_decision)

        # 2. Change initial_policy_reason
        hijack_reason = created.model_copy(deep=True)
        hijack_reason.initial_policy_reason = "modified reason"
        with pytest.raises(ValueError, match="Immutable admission provenance"):
            await repo.update(hijack_reason)

        # Persisted provenance remains unchanged after rejected mutation attempts
        fetched = await repo.get_by_id(rec_id, "tenant_a", "user_a")
        assert fetched.initial_policy_decision == PolicyDecision.SAVE
        assert fetched.initial_policy_reason == "test"
    asyncio.run(run())


def test_postgres_deep_copy_mutation_protection():
    async def run():
        await setup_db()
        repo = PostgreSQLMemoryRepository()
        rec_id = uuid4()
        rec = MemoryRecord(
            id=rec_id,
            tenant_id="tenant_a",
            user_id="user_a",
            content="I prefer Python.",
            memory_type=MemoryType.SEMANTIC,
            initial_policy_decision=PolicyDecision.SAVE,
            initial_policy_reason="test"
        )
        created = await repo.create(rec)

        # Mutate the returned object directly
        created.content = "Rust is better."
        
        # Verify the stored database state was not modified
        fetched = await repo.get_by_id(rec_id, "tenant_a", "user_a")
        assert fetched.content == "I prefer Python."
    asyncio.run(run())


def test_postgres_list_active_active_only_filtering():
    async def run():
        await setup_db()
        repo = PostgreSQLMemoryRepository()
        tenant = "tenant_a"
        user = "user_a"

        # Create active memory
        rid1 = uuid4()
        rec1 = MemoryRecord(
            id=rid1, tenant_id=tenant, user_id=user, content="Active", memory_type=MemoryType.SEMANTIC,
            initial_policy_decision=PolicyDecision.SAVE, initial_policy_reason="test"
        )
        await repo.create(rec1)

        # Create pending memory
        rid2 = uuid4()
        rec2 = MemoryRecord(
            id=rid2, tenant_id=tenant, user_id=user, content="Pending", memory_type=MemoryType.SEMANTIC,
            status=MemoryStatus.PENDING,
            initial_policy_decision=PolicyDecision.PENDING_APPROVAL, initial_policy_reason="test"
        )
        await repo.create(rec2)

        active_list = await repo.list_active(tenant, user)
        assert len(active_list) == 1
        assert active_list[0].id == rid1
    asyncio.run(run())


def test_postgres_list_active_deterministic_ordering():
    async def run():
        await setup_db()
        repo = PostgreSQLMemoryRepository()
        tenant = "tenant_a"
        user = "user_a"

        base_time = datetime.now(timezone.utc)
        for i in range(5):
            rid = uuid4()
            r = MemoryRecord(
                id=rid,
                tenant_id=tenant,
                user_id=user,
                content=f"Memory {i}",
                memory_type=MemoryType.SEMANTIC,
                created_at=base_time + timedelta(seconds=i),
                initial_policy_decision=PolicyDecision.SAVE,
                initial_policy_reason="Sorting test"
            )
            await repo.create(r)

        active_list = await repo.list_active(tenant, user, limit=3)
        assert len(active_list) == 3
        # Sorted by created_at DESC (newest first)
        assert active_list[0].content == "Memory 4"
        assert active_list[1].content == "Memory 3"
        assert active_list[2].content == "Memory 2"
    asyncio.run(run())


def test_postgres_list_active_positive_limit_validation():
    async def run():
        await setup_db()
        repo = PostgreSQLMemoryRepository()
        with pytest.raises(ValueError, match="Limit must be a positive integer"):
            await repo.list_active("t", "u", limit=0)

        with pytest.raises(ValueError, match="Limit must be a positive integer"):
            await repo.list_active("t", "u", limit=-5)
    asyncio.run(run())


def test_postgres_list_by_status_scoped_filtering():
    async def run():
        await setup_db()
        repo = PostgreSQLMemoryRepository()
        tenant = "tenant_a"
        user = "user_a"

        rid = uuid4()
        rec = MemoryRecord(
            id=rid, tenant_id=tenant, user_id=user, content="Archived", memory_type=MemoryType.SEMANTIC,
            status=MemoryStatus.ARCHIVED,
            archived_at=datetime.now(timezone.utc),
            initial_policy_decision=PolicyDecision.SAVE, initial_policy_reason="test"
        )
        await repo.create(rec)

        # 1. list_by_status under correct scope
        archived_list = await repo.list_by_status(tenant, user, MemoryStatus.ARCHIVED)
        assert len(archived_list) == 1
        assert archived_list[0].id == rid

        # 2. list_by_status under wrong scope
        assert len(await repo.list_by_status("tenant_b", "user_b", MemoryStatus.ARCHIVED)) == 0
    asyncio.run(run())


def test_postgres_get_active_by_slot_basic_scenarios():
    async def run():
        await setup_db()
        repo = PostgreSQLMemoryRepository()
        tenant = "tenant_a"
        user = "user_a"

        # 1. Zero matching active records returns []
        res = await repo.get_active_by_slot(tenant, user, MemoryType.SEMANTIC, "profession")
        assert res == []

        # Create one active match
        rec1 = MemoryRecord(
            id=uuid4(), tenant_id=tenant, user_id=user, content="Engineer", memory_type=MemoryType.SEMANTIC,
            initial_policy_decision=PolicyDecision.SAVE, initial_policy_reason="test",
            identity_slot="profession"
        )
        await repo.create(rec1)

        # 2. One exact active match returns one record
        res1 = await repo.get_active_by_slot(tenant, user, MemoryType.SEMANTIC, "profession")
        assert len(res1) == 1
        assert res1[0].id == rec1.id
        assert res1[0].identity_slot == "profession"

        # Create more matches to test bounded result and deterministic ordering
        recs = []
        base_time = datetime.now(timezone.utc)
        for i in range(3):
            r = MemoryRecord(
                id=uuid4(), tenant_id=tenant, user_id=user, content=f"Eng {i}", memory_type=MemoryType.SEMANTIC,
                initial_policy_decision=PolicyDecision.SAVE, initial_policy_reason="test",
                identity_slot="profession",
                created_at=base_time + timedelta(seconds=i+1)
            )
            recs.append(await repo.create(r))

        # 3. get_active_by_slot returns exactly two records (bounded result)
        res2 = await repo.get_active_by_slot(tenant, user, MemoryType.SEMANTIC, "profession")
        assert len(res2) == 2
        # Deterministic ordering is created_at DESC (newest first), then id ASC
        assert res2[0].id == recs[2].id
        assert res2[1].id == recs[1].id
    asyncio.run(run())


def test_postgres_get_active_by_slot_filters():
    async def run():
        await setup_db()
        repo = PostgreSQLMemoryRepository()
        tenant = "tenant_a"
        user = "user_a"

        # Create active record
        rec = MemoryRecord(
            id=uuid4(), tenant_id=tenant, user_id=user, content="Engineer", memory_type=MemoryType.SEMANTIC,
            initial_policy_decision=PolicyDecision.SAVE, initial_policy_reason="test",
            identity_slot="profession"
        )
        await repo.create(rec)

        # 1. Scope isolation check: different tenant
        res_t = await repo.get_active_by_slot("tenant_b", user, MemoryType.SEMANTIC, "profession")
        assert len(res_t) == 0

        # 2. Scope isolation check: different user
        res_u = await repo.get_active_by_slot(tenant, "user_b", MemoryType.SEMANTIC, "profession")
        assert len(res_u) == 0

        # 3. Memory type mismatch check
        res_type = await repo.get_active_by_slot(tenant, user, MemoryType.PROCEDURAL, "profession")
        assert len(res_type) == 0

        # 4. Identity slot mismatch check
        res_slot = await repo.get_active_by_slot(tenant, user, MemoryType.SEMANTIC, "residence")
        assert len(res_slot) == 0

        # 5. Non-active records exclusion
        # Pending
        rec_pending = MemoryRecord(
            id=uuid4(), tenant_id=tenant, user_id=user, content="Engineer", memory_type=MemoryType.SEMANTIC,
            status=MemoryStatus.PENDING,
            initial_policy_decision=PolicyDecision.SAVE, initial_policy_reason="test",
            identity_slot="profession"
        )
        await repo.create(rec_pending)
        
        # Archived
        rec_archived = MemoryRecord(
            id=uuid4(), tenant_id=tenant, user_id=user, content="Engineer", memory_type=MemoryType.SEMANTIC,
            status=MemoryStatus.ARCHIVED,
            archived_at=datetime.now(timezone.utc),
            initial_policy_decision=PolicyDecision.SAVE, initial_policy_reason="test",
            identity_slot="profession"
        )
        await repo.create(rec_archived)

        # Deleted
        rec_deleted = MemoryRecord(
            id=uuid4(), tenant_id=tenant, user_id=user, content="Engineer", memory_type=MemoryType.SEMANTIC,
            status=MemoryStatus.DELETED,
            deleted_at=datetime.now(timezone.utc),
            initial_policy_decision=PolicyDecision.SAVE, initial_policy_reason="test",
            identity_slot="profession"
        )
        await repo.create(rec_deleted)

        res_filter = await repo.get_active_by_slot(tenant, user, MemoryType.SEMANTIC, "profession")
        assert len(res_filter) == 1
        assert res_filter[0].id == rec.id
    asyncio.run(run())


def test_postgres_update_identity_immutability():
    async def run():
        await setup_db()
        repo = PostgreSQLMemoryRepository()
        tenant = "tenant_a"
        user = "user_a"

        rec = MemoryRecord(
            id=uuid4(), tenant_id=tenant, user_id=user, content="Engineer", memory_type=MemoryType.SEMANTIC,
            initial_policy_decision=PolicyDecision.SAVE, initial_policy_reason="test",
            identity_slot="profession"
        )
        created = await repo.create(rec)

        # 1. Ordinary mutable payload updates still succeed when identity coordinates remain unchanged
        created.content = "Senior Engineer"
        updated = await repo.update(created)
        assert updated.content == "Senior Engineer"

        # 2. memory_type mutation is rejected with ValueError
        updated.memory_type = MemoryType.PROCEDURAL
        with pytest.raises(ValueError, match="memory_type is immutable"):
            await repo.update(updated)
        
        # Restore type
        updated.memory_type = MemoryType.SEMANTIC

        # 3. identity_slot mutation from one concrete slot to another is rejected
        updated.identity_slot = "residence"
        with pytest.raises(ValueError, match="identity_slot is immutable"):
            await repo.update(updated)

        # 4. identity_slot mutation from concrete slot to None is rejected
        updated.identity_slot = None
        with pytest.raises(ValueError, match="identity_slot is immutable"):
            await repo.update(updated)
    asyncio.run(run())


def test_postgres_search_candidates_flow():
    async def run():
        await setup_db()
        repo = PostgreSQLMemoryRepository()
        tenant = "tenant_a"
        user = "user_a"

        # Helpers to create embeddings
        e1 = [0.1] * 1536
        e2 = [0.2] * 1536

        # Create active matching records
        r1 = await repo.create(MemoryRecord(
            id=uuid4(), tenant_id=tenant, user_id=user, content="Rec 1",
            memory_type=MemoryType.SEMANTIC, status=MemoryStatus.ACTIVE,
            embedding=e1, initial_policy_decision=PolicyDecision.SAVE, initial_policy_reason="test"
        ))

        r2 = await repo.create(MemoryRecord(
            id=uuid4(), tenant_id=tenant, user_id=user, content="Rec 2",
            memory_type=MemoryType.SEMANTIC, status=MemoryStatus.ACTIVE,
            embedding=e2, initial_policy_decision=PolicyDecision.SAVE, initial_policy_reason="test"
        ))

        # Create active record with embedding=None
        r_none = await repo.create(MemoryRecord(
            id=uuid4(), tenant_id=tenant, user_id=user, content="Rec None",
            memory_type=MemoryType.SEMANTIC, status=MemoryStatus.ACTIVE,
            embedding=None, initial_policy_decision=PolicyDecision.SAVE, initial_policy_reason="test"
        ))

        # 1. Test Fallback/Non-semantic query: query_embedding = None
        results_fallback = await repo.search_candidates(tenant, user, None, limit=10)
        assert len(results_fallback) == 3
        for record, similarity in results_fallback:
            assert similarity is None
            assert record.status == MemoryStatus.ACTIVE

        # 2. Test Semantic query: query_embedding = e1
        results_semantic = await repo.search_candidates(tenant, user, e1, limit=10)
        assert len(results_semantic) == 2
        for record, similarity in results_semantic:
            assert isinstance(similarity, float)
            assert record.id != r_none.id

        # 3. Test Invalid Limit
        with pytest.raises(ValueError, match="limit must be >= 1"):
            await repo.search_candidates(tenant, user, e1, limit=0)

        # 4. Test Dimension Mismatch
        with pytest.raises(ValueError, match="query_embedding must be exactly 1536 dimensions"):
            await repo.search_candidates(tenant, user, [0.1] * 100, limit=10)

    asyncio.run(run())


def test_postgres_audit_service_basic_recording():
    async def run():
        await setup_db()
        service = PostgreSQLAuditRepository()
        tenant = "tenant_a"
        user = "user_a"
        mem_id = uuid4()
        event_id = uuid4()

        # Create dummy memory record to satisfy foreign key constraint on memory_id
        repo = PostgreSQLMemoryRepository()
        await repo.create(MemoryRecord(
            id=mem_id, tenant_id=tenant, user_id=user, content="dummy",
            memory_type=MemoryType.SEMANTIC, initial_policy_decision=PolicyDecision.SAVE,
            initial_policy_reason="dummy"
        ))

        event = AuditEvent(
            id=event_id,
            tenant_id=tenant,
            user_id=user,
            memory_id=mem_id,
            action=AuditEventAction.MEMORY_CREATED,
            reason="Saved successfully",
            metadata={"source": "api_test"}
        )

        recorded = await service.record(event)
        
        assert recorded.id == event_id
        assert recorded.tenant_id == tenant
        assert recorded.user_id == user
        assert recorded.memory_id == mem_id
        assert recorded.action == AuditEventAction.MEMORY_CREATED
        assert recorded.reason == "Saved successfully"
        assert recorded.metadata == {"source": "api_test"}

        logs = await service.list_events(tenant)
        assert len(logs) == 1
        assert logs[0].id == event_id
    asyncio.run(run())


def test_postgres_duplicate_event_rejection():
    async def run():
        await setup_db()
        service = PostgreSQLAuditRepository()
        event_id = uuid4()
        event = AuditEvent(
            id=event_id,
            tenant_id="tenant_a",
            action=AuditEventAction.MEMORY_CREATED
        )

        await service.record(event)

        with pytest.raises(ValueError, match="Duplicate audit event ID"):
            await service.record(event)
    asyncio.run(run())


def test_postgres_block_and_drop_with_none_memory_id():
    async def run():
        await setup_db()
        service = PostgreSQLAuditRepository()
        base_time = datetime.now(timezone.utc)
        
        # BLOCK
        block_event = AuditEvent(
            id=uuid4(),
            tenant_id="tenant_a",
            memory_id=None,
            action=AuditEventAction.MEMORY_BLOCKED,
            reason="Secret pattern detected",
            created_at=base_time - timedelta(seconds=1)
        )
        await service.record(block_event)

        # DROP
        drop_event = AuditEvent(
            id=uuid4(),
            tenant_id="tenant_a",
            memory_id=None,
            action=AuditEventAction.MEMORY_DROPPED,
            reason="Low utility",
            created_at=base_time
        )
        await service.record(drop_event)

        logs = await service.list_events("tenant_a")
        assert len(logs) == 2
        assert logs[0].action == AuditEventAction.MEMORY_DROPPED
        assert logs[0].memory_id is None
        assert logs[1].action == AuditEventAction.MEMORY_BLOCKED
        assert logs[1].memory_id is None
    asyncio.run(run())


def test_postgres_scoped_filtering():
    async def run():
        await setup_db()
        service = PostgreSQLAuditRepository()
        tenant1 = "tenant_1"
        tenant2 = "tenant_2"
        user1 = "user_1"
        user2 = "user_2"
        mem1 = uuid4()
        mem2 = uuid4()

        # Create dummy memories to satisfy foreign key constraints
        repo = PostgreSQLMemoryRepository()
        await repo.create(MemoryRecord(id=mem1, tenant_id=tenant1, user_id=user1, content="dummy", memory_type=MemoryType.SEMANTIC, initial_policy_decision=PolicyDecision.SAVE, initial_policy_reason="dummy"))
        await repo.create(MemoryRecord(id=mem2, tenant_id=tenant1, user_id=user2, content="dummy", memory_type=MemoryType.SEMANTIC, initial_policy_decision=PolicyDecision.SAVE, initial_policy_reason="dummy"))

        await service.record(AuditEvent(id=uuid4(), tenant_id=tenant1, user_id=user1, memory_id=mem1, action=AuditEventAction.MEMORY_CREATED))
        await service.record(AuditEvent(id=uuid4(), tenant_id=tenant1, user_id=user2, memory_id=mem2, action=AuditEventAction.MEMORY_UPDATED))
        await service.record(AuditEvent(id=uuid4(), tenant_id=tenant2, user_id=user1, memory_id=mem1, action=AuditEventAction.MEMORY_DELETED))

        t1_logs = await service.list_events(tenant1)
        assert len(t1_logs) == 2

        t1_u1_logs = await service.list_events(tenant1, user_id=user1)
        assert len(t1_u1_logs) == 1
        assert t1_u1_logs[0].user_id == user1

        t1_m2_logs = await service.list_events(tenant1, memory_id=mem2)
        assert len(t1_m2_logs) == 1
        assert t1_m2_logs[0].memory_id == mem2
    asyncio.run(run())


def test_postgres_deterministic_sorting():
    async def run():
        await setup_db()
        service = PostgreSQLAuditRepository()
        tenant = "tenant_a"
        base_time = datetime.now(timezone.utc)

        e1_id = uuid4()
        e2_id = uuid4()
        e3_id = uuid4()

        await service.record(AuditEvent(id=e1_id, tenant_id=tenant, action=AuditEventAction.MEMORY_CREATED, created_at=base_time))
        await service.record(AuditEvent(id=e2_id, tenant_id=tenant, action=AuditEventAction.MEMORY_UPDATED, created_at=base_time + timedelta(seconds=5)))
        await service.record(AuditEvent(id=e3_id, tenant_id=tenant, action=AuditEventAction.MEMORY_DELETED, created_at=base_time - timedelta(seconds=5)))

        logs = await service.list_events(tenant)
        assert len(logs) == 3
        assert logs[0].id == e2_id
        assert logs[1].id == e1_id
        assert logs[2].id == e3_id
    asyncio.run(run())


def test_postgres_limit_validation():
    async def run():
        await setup_db()
        service = PostgreSQLAuditRepository()
        with pytest.raises(ValueError, match="Limit must be a positive integer"):
            await service.list_events("tenant_a", limit=0)
        with pytest.raises(ValueError, match="Limit must be a positive integer"):
            await service.list_events("tenant_a", limit=-5)
    asyncio.run(run())
