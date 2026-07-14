import pytest
import asyncio
from datetime import datetime, timezone
from uuid import uuid4, UUID
from typing import Optional, List

from app.domain import (
    CandidateMemory, MemoryRecord, PolicyResult, PolicyDecision, 
    MemoryStatus, Sensitivity, MemoryType, AuditEventAction
)
from app.repositories import InMemoryMemoryRepository
from app.services import (
    WriteService, WriteResult, InMemoryAuditService, AuditService,
    WriteServiceError, TargetUnavailableError, InvalidPolicyResultError, UnsupportedDecisionError
)
from app.policy import PolicyBroker, StaticSlotRegistry

# ------------------------------------------------------------
# TEST DOUBLES
# ------------------------------------------------------------

class StubBroker:
    def __init__(self, result: PolicyResult) -> None:
        self.result = result

    async def evaluate(self, candidate: CandidateMemory) -> PolicyResult:
        return self.result


class FailingAuditService(AuditService):
    async def record(self, event) -> None:
        raise RuntimeError("Audit database connection lost.")

    async def list_events(self, tenant_id, user_id=None, memory_id=None, limit=None):
        return []


# ------------------------------------------------------------
# WRITE SERVICE TESTS
# ------------------------------------------------------------

def test_save_execution():
    async def run():
        repo = InMemoryMemoryRepository()
        audit = InMemoryAuditService()
        stub_broker = StubBroker(
            PolicyResult(decision=PolicyDecision.SAVE, reason="Valid candidate fact.")
        )
        service = WriteService(broker=stub_broker, repository=repo, audit_service=audit)

        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="Jacob is a Software Engineer",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.9,
            importance=8,
            sensitivity=Sensitivity.LOW,
            identity_slot="profession"
        )

        res = await service.process(candidate)
        assert res.policy_result.decision == PolicyDecision.SAVE
        assert res.memory is not None
        
        # Verify MemoryRecord field mappings
        rec = res.memory
        assert rec.tenant_id == "tenant_a"
        assert rec.user_id == "user_a"
        assert rec.content == "Jacob is a Software Engineer"
        assert rec.memory_type == MemoryType.SEMANTIC
        assert rec.status == MemoryStatus.ACTIVE
        assert rec.sensitivity == Sensitivity.LOW
        assert rec.importance == 8
        assert rec.confidence == 0.9
        assert rec.identity_slot == "profession"
        assert rec.embedding is None
        assert rec.initial_policy_decision == PolicyDecision.SAVE
        assert rec.initial_policy_reason == "Valid candidate fact."

        # Verify database state
        persisted = await repo.get_by_id(rec.id, "tenant_a", "user_a")
        assert persisted is not None
        assert persisted.content == "Jacob is a Software Engineer"

        # Verify Audit log
        logs = await audit.list_events("tenant_a")
        assert len(logs) == 1
        assert logs[0].action == AuditEventAction.MEMORY_CREATED
        assert logs[0].memory_id == rec.id
        assert logs[0].reason == "Valid candidate fact."

    asyncio.run(run())


def test_pending_approval_execution():
    async def run():
        repo = InMemoryMemoryRepository()
        audit = InMemoryAuditService()
        stub_broker = StubBroker(
            PolicyResult(decision=PolicyDecision.PENDING_APPROVAL, reason="Gated due to sensitivity.")
        )
        service = WriteService(broker=stub_broker, repository=repo, audit_service=audit)

        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="Jacob has medical updates.",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.9,
            importance=8,
            sensitivity=Sensitivity.HIGH,
            identity_slot="profession"
        )

        res = await service.process(candidate)
        assert res.policy_result.decision == PolicyDecision.PENDING_APPROVAL
        assert res.memory is not None
        
        rec = res.memory
        assert rec.status == MemoryStatus.PENDING
        assert rec.embedding is None
        assert rec.initial_policy_decision == PolicyDecision.PENDING_APPROVAL
        assert rec.initial_policy_reason == "Gated due to sensitivity."

        # Verify pending record is excluded from active occupancy check
        active_list = await repo.get_active_by_slot("tenant_a", "user_a", MemoryType.SEMANTIC, "profession")
        assert len(active_list) == 0

        # Verify audit log
        logs = await audit.list_events("tenant_a")
        assert len(logs) == 1
        assert logs[0].action == AuditEventAction.MEMORY_PENDING_APPROVAL
        assert logs[0].memory_id == rec.id

    asyncio.run(run())


def test_block_execution():
    async def run():
        repo = InMemoryMemoryRepository()
        audit = InMemoryAuditService()
        stub_broker = StubBroker(
            PolicyResult(decision=PolicyDecision.BLOCK, reason="Content matched a secret pattern.")
        )
        service = WriteService(broker=stub_broker, repository=repo, audit_service=audit)

        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="sk-test-secret-key-12345",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.9,
            importance=8,
            sensitivity=Sensitivity.LOW
        )

        res = await service.process(candidate)
        assert res.policy_result.decision == PolicyDecision.BLOCK
        assert res.memory is None

        # Verify no memory records exist
        active_list = await repo.list_active("tenant_a", "user_a")
        assert len(active_list) == 0

        # Verify audit log exists but is safety-redacted
        logs = await audit.list_events("tenant_a")
        assert len(logs) == 1
        assert logs[0].action == AuditEventAction.MEMORY_BLOCKED
        assert logs[0].memory_id is None
        assert "sk-test" not in logs[0].reason
        assert "sk-test" not in str(logs[0].metadata)

    asyncio.run(run())


def test_drop_low_utility_execution():
    async def run():
        repo = InMemoryMemoryRepository()
        audit = InMemoryAuditService()
        stub_broker = StubBroker(
            PolicyResult(decision=PolicyDecision.DROP_LOW_UTILITY, reason="Redundant greeting.")
        )
        service = WriteService(broker=stub_broker, repository=repo, audit_service=audit)

        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="hello there",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.9,
            importance=1,
            sensitivity=Sensitivity.LOW
        )

        res = await service.process(candidate)
        assert res.policy_result.decision == PolicyDecision.DROP_LOW_UTILITY
        assert res.memory is None

        # Verify no memory records exist
        active_list = await repo.list_active("tenant_a", "user_a")
        assert len(active_list) == 0

        # Verify audit log
        logs = await audit.list_events("tenant_a")
        assert len(logs) == 1
        assert logs[0].action == AuditEventAction.MEMORY_DROPPED
        assert logs[0].memory_id is None

    asyncio.run(run())


def test_update_existing_success():
    async def run():
        repo = InMemoryMemoryRepository()
        audit = InMemoryAuditService()
        
        # 1. Create an active target record in the repository
        target_rec = MemoryRecord(
            tenant_id="tenant_a",
            user_id="user_a",
            content="Jacob is an AI Engineer",
            memory_type=MemoryType.SEMANTIC,
            status=MemoryStatus.ACTIVE,
            sensitivity=Sensitivity.LOW,
            importance=7,
            confidence=0.9,
            embedding=[0.1] * 1536,  # Non-None embedding
            initial_policy_decision=PolicyDecision.SAVE,
            initial_policy_reason="Original Save",
            identity_slot="profession"
        )
        created = await repo.create(target_rec)

        stub_broker = StubBroker(
            PolicyResult(
                decision=PolicyDecision.UPDATE_EXISTING,
                reason="Slot coordinate occupied; updating.",
                target_memory_id=created.id
            )
        )
        service = WriteService(broker=stub_broker, repository=repo, audit_service=audit)

        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="Jacob is a Senior AI Engineer",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.95,
            importance=9,
            sensitivity=Sensitivity.MEDIUM,
            source_kind="slack",
            source_conversation_id="conv_123",
            source_excerpt="Update: Jacob is now a Senior AI Engineer",
            identity_slot="profession"
        )

        # 2. Run write process
        res = await service.process(candidate)
        assert res.policy_result.decision == PolicyDecision.UPDATE_EXISTING
        assert res.memory is not None
        
        # Verify target payload replaced but coordinates and provenance preserved
        updated = res.memory
        assert updated.id == created.id
        assert updated.content == "Jacob is a Senior AI Engineer"
        assert updated.confidence == 0.95
        assert updated.importance == 9
        assert updated.sensitivity == Sensitivity.MEDIUM
        assert updated.source_kind == "slack"
        assert updated.source_conversation_id == "conv_123"
        assert updated.source_excerpt == "Update: Jacob is now a Senior AI Engineer"
        
        # Invalidation (ADR-006)
        assert updated.embedding is None
        
        # Preserved
        assert updated.tenant_id == "tenant_a"
        assert updated.user_id == "user_a"
        assert updated.memory_type == MemoryType.SEMANTIC
        assert updated.identity_slot == "profession"
        assert updated.created_at == created.created_at
        assert updated.initial_policy_decision == PolicyDecision.SAVE
        assert updated.initial_policy_reason == "Original Save"
        assert updated.status == MemoryStatus.ACTIVE

        # Verify audit log
        logs = await audit.list_events("tenant_a")
        assert len(logs) == 1
        assert logs[0].action == AuditEventAction.MEMORY_UPDATED
        assert logs[0].memory_id == created.id
        assert "changed_fields" in logs[0].metadata
        assert "content" in logs[0].metadata["changed_fields"]
        assert "embedding" in logs[0].metadata["changed_fields"]
        # Audit log does not copy raw contents
        assert "Senior AI Engineer" not in str(logs[0].metadata)

    asyncio.run(run())


def test_update_existing_missing_target():
    async def run():
        repo = InMemoryMemoryRepository()
        audit = InMemoryAuditService()
        
        stub_broker = StubBroker(
            PolicyResult(
                decision=PolicyDecision.UPDATE_EXISTING,
                reason="Slot coordinate occupied; updating.",
                target_memory_id=uuid4()  # Missing target UUID
            )
        )
        service = WriteService(broker=stub_broker, repository=repo, audit_service=audit)

        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="Jacob is a Senior AI Engineer",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.95,
            importance=9,
            sensitivity=Sensitivity.MEDIUM,
            identity_slot="profession"
        )

        with pytest.raises(TargetUnavailableError):
            await service.process(candidate)

        # Verify no audit event was emitted
        assert len(await audit.list_events("tenant_a")) == 0

    asyncio.run(run())


def test_update_existing_inactive_target():
    async def run():
        repo = InMemoryMemoryRepository()
        audit = InMemoryAuditService()
        
        # Target status is PENDING (not ACTIVE)
        target_rec = MemoryRecord(
            tenant_id="tenant_a",
            user_id="user_a",
            content="Jacob is an AI Engineer",
            memory_type=MemoryType.SEMANTIC,
            status=MemoryStatus.PENDING,  # Inactive status
            sensitivity=Sensitivity.LOW,
            importance=7,
            confidence=0.9,
            initial_policy_decision=PolicyDecision.SAVE,
            initial_policy_reason="Original Save",
            identity_slot="profession"
        )
        created = await repo.create(target_rec)

        stub_broker = StubBroker(
            PolicyResult(
                decision=PolicyDecision.UPDATE_EXISTING,
                reason="Slot coordinate occupied; updating.",
                target_memory_id=created.id
            )
        )
        service = WriteService(broker=stub_broker, repository=repo, audit_service=audit)

        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="Jacob is a Senior AI Engineer",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.95,
            importance=9,
            sensitivity=Sensitivity.MEDIUM,
            identity_slot="profession"
        )

        # Must fail closed since target is not active
        with pytest.raises(TargetUnavailableError):
            await service.process(candidate)

    asyncio.run(run())


def test_update_existing_coordinate_mismatch():
    async def run():
        repo = InMemoryMemoryRepository()
        audit = InMemoryAuditService()
        
        target_rec = MemoryRecord(
            tenant_id="tenant_a",
            user_id="user_a",
            content="Jacob is an AI Engineer",
            memory_type=MemoryType.SEMANTIC,  # Target Type: SEMANTIC
            status=MemoryStatus.ACTIVE,
            sensitivity=Sensitivity.LOW,
            importance=7,
            confidence=0.9,
            initial_policy_decision=PolicyDecision.SAVE,
            initial_policy_reason="Original Save",
            identity_slot="profession"
        )
        created = await repo.create(target_rec)

        stub_broker = StubBroker(
            PolicyResult(
                decision=PolicyDecision.UPDATE_EXISTING,
                reason="Slot coordinate occupied; updating.",
                target_memory_id=created.id
            )
        )
        service = WriteService(broker=stub_broker, repository=repo, audit_service=audit)

        # Candidate coordinate mismatch (MemoryType.PROCEDURAL)
        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="Jacob is a Senior AI Engineer",
            memory_type=MemoryType.PROCEDURAL,  # Coordinate Mismatch
            confidence=0.95,
            importance=9,
            sensitivity=Sensitivity.MEDIUM,
            identity_slot="profession"
        )

        with pytest.raises(InvalidPolicyResultError):
            await service.process(candidate)

    asyncio.run(run())


def test_malformed_update_existing_result():
    async def run():
        repo = InMemoryMemoryRepository()
        audit = InMemoryAuditService()
        
        # Construct malformed result directly (target_memory_id=None for UPDATE_EXISTING)
        malformed_result = PolicyResult.model_construct(
            decision=PolicyDecision.UPDATE_EXISTING,
            reason="Missing target id",
            target_memory_id=None
        )
        stub_broker = StubBroker(malformed_result)
        service = WriteService(broker=stub_broker, repository=repo, audit_service=audit)

        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="Jacob is a Senior AI Engineer",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.95,
            importance=9,
            sensitivity=Sensitivity.MEDIUM,
            identity_slot="profession"
        )

        with pytest.raises(InvalidPolicyResultError):
            await service.process(candidate)

    asyncio.run(run())


def test_merge_with_existing_throws():
    async def run():
        repo = InMemoryMemoryRepository()
        audit = InMemoryAuditService()
        stub_broker = StubBroker(
            PolicyResult(
                decision=PolicyDecision.MERGE_WITH_EXISTING,
                reason="Candidate overlaps with existing record.",
                target_memory_id=uuid4()
            )
        )
        service = WriteService(broker=stub_broker, repository=repo, audit_service=audit)

        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="FastAPI is Pythonic.",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.9,
            importance=8,
            sensitivity=Sensitivity.LOW
        )

        # Verify merge throws UnsupportedDecisionError in Phase 1
        with pytest.raises(UnsupportedDecisionError):
            await service.process(candidate)

    asyncio.run(run())


def test_audit_failure_propagation():
    async def run():
        repo = InMemoryMemoryRepository()
        failing_audit = FailingAuditService()
        
        # Test case: SAVE
        stub_broker = StubBroker(
            PolicyResult(decision=PolicyDecision.SAVE, reason="Allowed.")
        )
        service = WriteService(broker=stub_broker, repository=repo, audit_service=failing_audit)

        candidate = CandidateMemory(
            tenant_id="tenant_a",
            user_id="user_a",
            content="FastAPI is Pythonic.",
            memory_type=MemoryType.SEMANTIC,
            confidence=0.9,
            importance=8,
            sensitivity=Sensitivity.LOW
        )

        # Exception must propagate
        with pytest.raises(RuntimeError, match="Audit database connection lost"):
            await service.process(candidate)

        # LIMITATION CHECK: Verify repository state is already mutated (in-memory MVP limitation)
        # Because we do not have transaction wrappers in this phase, the record was saved but audit failed.
        active_list = await repo.list_active("tenant_a", "user_a")
        assert len(active_list) == 1

    asyncio.run(run())


def test_service_package_exports():
    from app.services import (
        WriteService, WriteResult, WriteServiceError, 
        TargetUnavailableError, InvalidPolicyResultError, UnsupportedDecisionError,
        AuditService, InMemoryAuditService
    )
    assert WriteService is not None
    assert WriteResult is not None
    assert WriteServiceError is not None
    assert TargetUnavailableError is not None
    assert InvalidPolicyResultError is not None
    assert UnsupportedDecisionError is not None
    assert AuditService is not None
    assert InMemoryAuditService is not None
