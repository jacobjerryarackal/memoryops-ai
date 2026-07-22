import asyncio
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest

from app.domain import (
    AuditEvent,
    AuditEventAction,
    CandidateMemory,
    MemoryRecord,
    MemoryStatus,
    MemoryType,
    PolicyDecision,
    Sensitivity,
)
from app.policy import PolicyBroker, StaticSlotRegistry
from app.repositories import InMemoryMemoryRepository
from app.services.audit import InMemoryAuditService
from app.services.governance import (
    GovernanceInvalidTransitionError,
    GovernancePolicyBlockedError,
    GovernanceService,
    GovernanceTargetUnavailableError,
    GovernanceValidationError,
)


@pytest.fixture
def repo():
    return InMemoryMemoryRepository()


@pytest.fixture
def audit():
    return InMemoryAuditService()


@pytest.fixture
def broker(repo):
    return PolicyBroker(repo)


@pytest.fixture
def gov_service(repo, audit, broker):
    return GovernanceService(repo, audit, broker)


def test_list_memories_default_and_filtering(gov_service, repo):
    async def run():
        tenant = "tenant_a"
        user = "user_a"

        # Create active
        r1 = await repo.create(
            MemoryRecord(
                id=uuid4(),
                tenant_id=tenant,
                user_id=user,
                content="Active Semantic",
                memory_type=MemoryType.SEMANTIC,
                status=MemoryStatus.ACTIVE,
                initial_policy_decision=PolicyDecision.SAVE,
                initial_policy_reason="test",
            )
        )

        # Create pending
        r2 = await repo.create(
            MemoryRecord(
                id=uuid4(),
                tenant_id=tenant,
                user_id=user,
                content="Pending Procedural",
                memory_type=MemoryType.PROCEDURAL,
                status=MemoryStatus.PENDING,
                initial_policy_decision=PolicyDecision.PENDING_APPROVAL,
                initial_policy_reason="test",
            )
        )

        # Create archived
        r3 = await repo.create(
            MemoryRecord(
                id=uuid4(),
                tenant_id=tenant,
                user_id=user,
                content="Archived Semantic",
                memory_type=MemoryType.SEMANTIC,
                status=MemoryStatus.ARCHIVED,
                archived_at=datetime.now(timezone.utc),
                initial_policy_decision=PolicyDecision.SAVE,
                initial_policy_reason="test",
            )
        )

        # Create deleted (should be excluded by default)
        r4 = await repo.create(
            MemoryRecord(
                id=uuid4(),
                tenant_id=tenant,
                user_id=user,
                content="Deleted Semantic",
                memory_type=MemoryType.SEMANTIC,
                status=MemoryStatus.DELETED,
                deleted_at=datetime.now(timezone.utc),
                initial_policy_decision=PolicyDecision.SAVE,
                initial_policy_reason="test",
            )
        )

        # Default listing (excludes deleted)
        mems = await gov_service.list_memories(tenant, user)
        assert len(mems) == 3
        # Excludes deleted
        assert all(m.status != MemoryStatus.DELETED for m in mems)

        # Type filter
        semantic_mems = await gov_service.list_memories(
            tenant, user, memory_type=MemoryType.SEMANTIC
        )
        assert len(semantic_mems) == 2
        assert all(m.memory_type == MemoryType.SEMANTIC for m in semantic_mems)

        # Status filter
        pending_mems = await gov_service.list_memories(
            tenant, user, status=MemoryStatus.PENDING
        )
        assert len(pending_mems) == 1
        assert pending_mems[0].id == r2.id

        # Explicit deleted status query is allowed
        deleted_mems = await gov_service.list_memories(
            tenant, user, status=MemoryStatus.DELETED
        )
        assert len(deleted_mems) == 1
        assert deleted_mems[0].id == r4.id

    asyncio.run(run())


def test_get_memory_by_id_and_provenance(gov_service, repo, audit):
    async def run():
        tenant = "tenant_a"
        user = "user_a"
        mid = uuid4()

        rec = await repo.create(
            MemoryRecord(
                id=mid,
                tenant_id=tenant,
                user_id=user,
                content="Engineer in Seattle",
                memory_type=MemoryType.SEMANTIC,
                status=MemoryStatus.ACTIVE,
                initial_policy_decision=PolicyDecision.SAVE,
                initial_policy_reason="test_provenance",
            )
        )

        # Record a fake audit event for it
        e1 = await audit.record(
            AuditEvent(
                id=uuid4(),
                tenant_id=tenant,
                user_id=user,
                memory_id=mid,
                action=AuditEventAction.MEMORY_CREATED,
                reason="Created",
            )
        )

        # Retrieve record
        fetched = await gov_service.get_memory_by_id(mid, tenant, user)
        assert fetched.id == mid

        # Mismatch scope returns TargetUnavailableError
        with pytest.raises(GovernanceTargetUnavailableError):
            await gov_service.get_memory_by_id(mid, "wrong_tenant", user)

        # Get provenance
        prov = await gov_service.get_memory_provenance(mid, tenant, user)
        assert prov["memory_id"] == mid
        assert prov["initial_policy_reason"] == "test_provenance"
        assert str(e1.id) in prov["audit_event_ids"]

        # Get deleted record returns TargetUnavailableError
        await repo.delete(mid, tenant, user)
        with pytest.raises(GovernanceTargetUnavailableError):
            await gov_service.get_memory_by_id(mid, tenant, user)

    asyncio.run(run())


def test_patch_memory_validation_and_safety_gate(gov_service, repo, audit):
    async def run():
        tenant = "tenant_a"
        user = "user_a"
        mid = uuid4()

        rec = await repo.create(
            MemoryRecord(
                id=mid,
                tenant_id=tenant,
                user_id=user,
                content="Seattle developer",
                memory_type=MemoryType.SEMANTIC,
                status=MemoryStatus.PENDING,
                embedding=[0.1] * 1536,
                initial_policy_decision=PolicyDecision.PENDING_APPROVAL,
                initial_policy_reason="needs review",
            )
        )

        # 1. Valid Transition: pending -> active
        updated = await gov_service.patch_memory(mid, tenant, user, status=MemoryStatus.ACTIVE)
        assert updated.status == MemoryStatus.ACTIVE

        # 2. Embedding clearance on content change
        updated_content = await gov_service.patch_memory(
            mid, tenant, user, content="Bellevue developer"
        )
        assert updated_content.content == "Bellevue developer"
        assert updated_content.embedding is None  # cleared atomically

        # 3. Invalid Transition: active -> pending
        with pytest.raises(GovernanceInvalidTransitionError):
            await gov_service.patch_memory(mid, tenant, user, status=MemoryStatus.PENDING)

        # 4. Content Safety: secret blocking (BLOCK)
        with pytest.raises(GovernancePolicyBlockedError):
            await gov_service.patch_memory(
                mid, tenant, user, content="My key is sk-proj-123456789012345678901234"
            )

        # 5. Content Safety: high sensitivity classification forcing pending_approval
        updated_sensitive = await gov_service.patch_memory(
            mid, tenant, user, content="Highly sensitive data", sensitivity=Sensitivity.HIGH
        )
        # Content changes, but safety gate redirects decision to PENDING_APPROVAL,
        # forcing status to pending
        assert updated_sensitive.status == MemoryStatus.PENDING
        assert updated_sensitive.sensitivity == Sensitivity.HIGH

    asyncio.run(run())


def test_patch_memory_single_valued_cardinality_revalidation(gov_service, repo):
    async def run():
        tenant = "tenant_a"
        user = "user_a"

        # Occupy the "profession" single slot with an ACTIVE memory
        active_prof = await repo.create(
            MemoryRecord(
                id=uuid4(),
                tenant_id=tenant,
                user_id=user,
                content="Engineer",
                memory_type=MemoryType.SEMANTIC,
                status=MemoryStatus.ACTIVE,
                identity_slot="profession",
                initial_policy_decision=PolicyDecision.SAVE,
                initial_policy_reason="test",
            )
        )

        # Create a pending memory for the same single slot
        pending_prof = await repo.create(
            MemoryRecord(
                id=uuid4(),
                tenant_id=tenant,
                user_id=user,
                content="Doctor",
                memory_type=MemoryType.SEMANTIC,
                status=MemoryStatus.PENDING,
                identity_slot="profession",
                initial_policy_decision=PolicyDecision.PENDING_APPROVAL,
                initial_policy_reason="test",
            )
        )

        # Attempting to approve the pending memory should fail slot validation
        with pytest.raises(GovernanceValidationError, match="is already occupied"):
            await gov_service.patch_memory(
                pending_prof.id, tenant, user, status=MemoryStatus.ACTIVE
            )

    asyncio.run(run())


def test_delete_memory_idempotency(gov_service, repo, audit):
    async def run():
        tenant = "tenant_a"
        user = "user_a"
        mid = uuid4()

        rec = await repo.create(
            MemoryRecord(
                id=mid,
                tenant_id=tenant,
                user_id=user,
                content="Seattle developer",
                memory_type=MemoryType.SEMANTIC,
                status=MemoryStatus.ACTIVE,
                initial_policy_decision=PolicyDecision.SAVE,
                initial_policy_reason="test",
            )
        )

        # 1. First delete transitions to deleted and emits audit log
        del_rec = await gov_service.delete_memory(mid, tenant, user)
        assert del_rec.status == MemoryStatus.DELETED
        assert del_rec.deleted_at is not None

        events = await audit.list_events(tenant_id=tenant, memory_id=mid)
        assert len(events) == 1
        assert events[0].action == AuditEventAction.MEMORY_DELETED

        # 2. Subsequent delete is idempotent, returns record, does not emit new audit log
        del_rec_again = await gov_service.delete_memory(mid, tenant, user)
        assert del_rec_again.status == MemoryStatus.DELETED
        assert del_rec_again.deleted_at == del_rec.deleted_at

        events_again = await audit.list_events(tenant_id=tenant, memory_id=mid)
        assert len(events_again) == 1  # Still only 1 event

    asyncio.run(run())


def test_get_metrics(gov_service, repo, audit):
    async def run():
        tenant = "tenant_metrics"
        user = "user_metrics"

        # Create active, pending, deleted
        await repo.create(
            MemoryRecord(
                id=uuid4(),
                tenant_id=tenant,
                user_id=user,
                content="Active",
                memory_type=MemoryType.SEMANTIC,
                status=MemoryStatus.ACTIVE,
                initial_policy_decision=PolicyDecision.SAVE,
                initial_policy_reason="test",
            )
        )
        await repo.create(
            MemoryRecord(
                id=uuid4(),
                tenant_id=tenant,
                user_id=user,
                content="Pending",
                memory_type=MemoryType.SEMANTIC,
                status=MemoryStatus.PENDING,
                initial_policy_decision=PolicyDecision.PENDING_APPROVAL,
                initial_policy_reason="test",
            )
        )

        # Record events
        await audit.record(
            AuditEvent(
                id=uuid4(),
                tenant_id=tenant,
                user_id=user,
                action=AuditEventAction.MEMORY_CREATED,
            )
        )
        await audit.record(
            AuditEvent(
                id=uuid4(),
                tenant_id=tenant,
                user_id=user,
                action=AuditEventAction.MEMORY_DELETED,
            )
        )

        metrics = await gov_service.get_metrics(tenant)
        assert metrics["total_memories"] == 2
        assert metrics["by_status"]["active"] == 1
        assert metrics["by_status"]["pending"] == 1
        assert metrics["by_status"]["deleted"] == 0
        assert metrics["audit_events"] == 2
        assert metrics["by_action"]["memory_created"] == 1
        assert metrics["by_action"]["memory_deleted"] == 1

    asyncio.run(run())
