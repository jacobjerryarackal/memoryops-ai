import pytest
from datetime import datetime, timezone
from uuid import uuid4

from app.domain import CandidateMemory, MemoryRecord, MemoryStatus, MemoryType, PolicyDecision, PolicyResult, Sensitivity
from app.services.write import WriteService, WriteResult
from app.repositories.base import MemoryRepository
from app.services.audit import AuditService


from app.services.observability import trace_class

@trace_class("repository")
class DummyMemoryRepository(MemoryRepository):
    def __init__(self):
        self.db = {}

    async def create(self, record):
        copied = record.model_copy(deep=True)
        if copied.id is None:
            copied.id = uuid4()
        self.db[copied.id] = copied
        return copied

    async def get_by_id(self, memory_id, tenant_id, user_id):
        rec = self.db.get(memory_id)
        if rec and rec.tenant_id == tenant_id and rec.user_id == user_id:
            return rec
        return None

    async def update(self, record):
        self.db[record.id] = record
        return record

    async def delete(self, memory_id, tenant_id, user_id):
        pass
    async def list_by_status(self, tenant_id, user_id, status):
        pass
    async def list_active(self, tenant_id, user_id, limit):
        pass
    async def get_active_by_slot(self, tenant_id, user_id, memory_type, identity_slot):
        pass
    async def search_candidates(self, tenant_id, user_id, query_embedding, limit):
        pass


class DummyAuditService(AuditService):
    def __init__(self):
        self.events = []

    async def record(self, event):
        self.events.append(event)
        return event

    async def list_events(self, tenant_id, user_id=None, memory_id=None, limit=None):
        return self.events


class DummyPolicyBroker:
    def __init__(self, decision, target_memory_id=None, reason="test policy reason"):
        self.decision = decision
        self.target_memory_id = target_memory_id
        self.reason = reason

    async def evaluate(self, candidate):
        return PolicyResult(
            decision=self.decision,
            reason=self.reason,
            target_memory_id=self.target_memory_id
        )


@pytest.fixture
def base_candidate():
    return CandidateMemory(
        tenant_id="t1",
        user_id="u1",
        content="Contact me at secret@example.com",
        memory_type=MemoryType.SEMANTIC,
        sensitivity=Sensitivity.LOW,
        importance=5,
        confidence=0.9,
        source_kind="chat",
        identity_slot="slot_a"
    )


@pytest.mark.anyio
async def test_write_path_redact(base_candidate):
    repo = DummyMemoryRepository()
    audit = DummyAuditService()
    broker = DummyPolicyBroker(PolicyDecision.REDACT)
    
    service = WriteService(broker, repo, audit)
    result = await service.process(base_candidate)
    
    assert result.memory is not None
    assert result.memory.content == "Contact me at [EMAIL_REDACTED]"
    assert result.memory.status == MemoryStatus.ACTIVE
    assert result.memory.initial_policy_decision == PolicyDecision.REDACT
    
    assert len(audit.events) == 1
    assert audit.events[0].action == "memory_redacted"


@pytest.mark.anyio
async def test_write_path_defer(base_candidate):
    repo = DummyMemoryRepository()
    audit = DummyAuditService()
    broker = DummyPolicyBroker(PolicyDecision.DEFER)
    
    service = WriteService(broker, repo, audit)
    result = await service.process(base_candidate)
    
    assert result.memory is not None
    assert result.memory.status == MemoryStatus.PENDING
    assert result.memory.initial_policy_decision == PolicyDecision.DEFER
    
    assert len(audit.events) == 1
    assert audit.events[0].action == "memory_deferred"


@pytest.mark.anyio
async def test_write_path_merge_with_existing(base_candidate):
    repo = DummyMemoryRepository()
    audit = DummyAuditService()
    
    # 1. Create target record
    target_id = uuid4()
    target_rec = MemoryRecord(
        id=target_id,
        tenant_id="t1",
        user_id="u1",
        content="Original content.",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        sensitivity=Sensitivity.LOW,
        importance=3,
        confidence=0.5,
        source_kind="chat",
        identity_slot="slot_a",
        embedding=[0.1]*1536,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="dummy"
    )

    await repo.create(target_rec)
    
    broker = DummyPolicyBroker(PolicyDecision.MERGE_WITH_EXISTING, target_memory_id=target_id)
    service = WriteService(broker, repo, audit)
    
    result = await service.process(base_candidate)
    
    assert result.memory is not None
    assert result.memory.id == target_id
    assert result.memory.content == "Original content.\nContact me at secret@example.com"
    # Merge strategy clamps confidence and importance to the max of both
    assert result.memory.confidence == 0.9
    assert result.memory.importance == 5
    # Embedding must be cleared to force recalculation
    assert result.memory.embedding is None
    
    assert len(audit.events) == 1
    assert audit.events[0].action == "memory_merged"


@pytest.mark.anyio
async def test_optimistic_concurrency_control():
    from app.repositories import InMemoryMemoryRepository
    repo = InMemoryMemoryRepository()
    
    mid = uuid4()

    rec = MemoryRecord(
        id=mid,
        tenant_id="t1",
        user_id="u1",
        content="OCC Test content.",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        sensitivity=Sensitivity.LOW,
        importance=5,
        confidence=0.9,
        source_kind="chat",
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="dummy"
    )
    
    created = await repo.create(rec)
    assert created.version == 1
    
    # 1. Update successfully
    created.content = "Updated first time"
    updated1 = await repo.update(created)
    assert updated1.version == 2
    assert updated1.content == "Updated first time"
    
    # 2. Update a second time using old version (1) -> raises conflict
    created.content = "Stale concurrent update"
    # created.version is still 1
    with pytest.raises(ValueError) as exc_info:
        await repo.update(created)
    assert "Concurrency conflict" in str(exc_info.value)

