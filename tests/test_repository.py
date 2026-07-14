import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from app.domain import MemoryRecord, MemoryStatus, MemoryType, Sensitivity, PolicyDecision
from app.repositories import InMemoryMemoryRepository

def test_duplicate_create_rejection():
    async def run():
        repo = InMemoryMemoryRepository()
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


def test_scope_isolation():
    async def run():
        repo = InMemoryMemoryRepository()
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


def test_scope_transfer_rejection():
    async def run():
        repo = InMemoryMemoryRepository()
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


def test_terminal_deletion():
    async def run():
        repo = InMemoryMemoryRepository()
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


def test_update_cannot_perform_deletion():
    async def run():
        repo = InMemoryMemoryRepository()
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


def test_immutable_admission_provenance():
    async def run():
        repo = InMemoryMemoryRepository()
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


def test_deep_copy_mutation_protection():
    async def run():
        repo = InMemoryMemoryRepository()
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


def test_list_active_active_only_filtering():
    async def run():
        repo = InMemoryMemoryRepository()
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


def test_list_active_deterministic_ordering():
    async def run():
        repo = InMemoryMemoryRepository()
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


def test_list_active_positive_limit_validation():
    async def run():
        repo = InMemoryMemoryRepository()
        with pytest.raises(ValueError, match="Limit must be a positive integer"):
            await repo.list_active("t", "u", limit=0)

        with pytest.raises(ValueError, match="Limit must be a positive integer"):
            await repo.list_active("t", "u", limit=-5)
    asyncio.run(run())


def test_list_by_status_scoped_filtering():
    async def run():
        repo = InMemoryMemoryRepository()
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


def test_get_active_by_slot_basic_scenarios():
    async def run():
        repo = InMemoryMemoryRepository()
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

        # 4. Mutating returned records does not mutate internal repository state (deep copy check)
        res2[0].content = "MUTATED"
        res3 = await repo.get_active_by_slot(tenant, user, MemoryType.SEMANTIC, "profession")
        assert res3[0].content != "MUTATED"

    asyncio.run(run())


def test_get_active_by_slot_filters():
    async def run():
        repo = InMemoryMemoryRepository()
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

        # 6. identity_slot=None records are not returned
        rec_none = MemoryRecord(
            id=uuid4(), tenant_id=tenant, user_id=user, content="Engineer", memory_type=MemoryType.SEMANTIC,
            initial_policy_decision=PolicyDecision.SAVE, initial_policy_reason="test",
            identity_slot=None
        )
        await repo.create(rec_none)
        res_none = await repo.get_active_by_slot(tenant, user, MemoryType.SEMANTIC, "profession")
        assert len(res_none) == 1

    asyncio.run(run())


def test_update_identity_immutability():
    async def run():
        repo = InMemoryMemoryRepository()
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

        # Create a record with identity_slot=None
        rec_none = MemoryRecord(
            id=uuid4(), tenant_id=tenant, user_id=user, content="Unclassified", memory_type=MemoryType.SEMANTIC,
            initial_policy_decision=PolicyDecision.SAVE, initial_policy_reason="test",
            identity_slot=None
        )
        created_none = await repo.create(rec_none)

        # 5. identity_slot mutation from None to concrete slot is rejected
        created_none.identity_slot = "profession"
        with pytest.raises(ValueError, match="identity_slot is immutable"):
            await repo.update(created_none)

    asyncio.run(run())

