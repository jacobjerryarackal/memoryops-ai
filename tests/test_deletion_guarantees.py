import pytest
import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from tests.test_postgres_repository import setup_db
from app.domain import MemoryRecord, MemoryStatus, MemoryType, PolicyDecision, AuditEventAction
from app.repositories.postgres import PostgreSQLMemoryRepository, PostgreSQLAuditRepository
from app.services.governance import GovernanceService, GovernanceTargetUnavailableError
from app.services.retrieval import Retriever, RetrievalCoordinator, Ranker, ContextComposer
from app.services import get_embedding_service
from app.runtime import get_governance_service


@pytest.mark.anyio
async def test_complete_deletion_guarantees_lifecycle():
    await setup_db()
    repo = PostgreSQLMemoryRepository()
    audit_repo = PostgreSQLAuditRepository()
    from app.policy.broker import PolicyBroker
    broker = PolicyBroker(repository=repo)
    gov_service = GovernanceService(repository=repo, audit_service=audit_repo, broker=broker)

    tenant = "tenant_del"
    user = "user_del"
    mid = uuid4()

    # 1. Create a memory record
    record = MemoryRecord(
        id=mid,
        tenant_id=tenant,
        user_id=user,
        content="Sensitive developer credentials key Sk-999",
        memory_type=MemoryType.SEMANTIC,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="Seed for deletion guarantee test"
    )
    
    created = await repo.create(record)
    assert created.status == MemoryStatus.ACTIVE

    from app.domain import AuditEvent
    # Log creation audit event
    await audit_repo.record(
        AuditEvent(
            id=uuid4(),
            tenant_id=tenant,
            user_id=user,
            memory_id=mid,
            action=AuditEventAction.MEMORY_CREATED,
            reason="Created in test",
            metadata={"test": "true"}
        )
    )

    # Verify retrieval by ID works
    fetched = await gov_service.get_memory_by_id(mid, tenant, user)
    assert fetched.id == mid
    assert fetched.status == MemoryStatus.ACTIVE

    # 2. Legal Hold Gating (Fail-closed)
    # Set legal hold to True
    fetched.legal_hold = True
    updated = await repo.update(fetched)
    assert updated.legal_hold is True

    # Attempt deletion under legal hold -> Should fail
    from app.services.governance import GovernanceValidationError
    with pytest.raises(GovernanceValidationError, match="Cannot delete memory under active legal hold."):
        await gov_service.delete_memory(mid, tenant, user, trace_id="trace-hold")

    # Verify memory is still active and exists
    still_active = await repo.get_by_id(mid, tenant, user)
    assert still_active.status == MemoryStatus.ACTIVE

    # 3. Remove Legal Hold and Delete Memory
    still_active.legal_hold = False
    await repo.update(still_active)

    # Perform deletion
    deleted = await gov_service.delete_memory(mid, tenant, user, trace_id="trace-del")
    assert deleted.status == MemoryStatus.DELETED
    assert deleted.deleted_at is not None

    # 4. Verification post-deletion
    # A. Retrieve by ID -> Should raise GovernanceTargetUnavailableError
    with pytest.raises(GovernanceTargetUnavailableError, match="Memory was not found within the requested scope."):
        await gov_service.get_memory_by_id(mid, tenant, user)

    # B. Candidate Search -> Should exclude deleted record
    # Instantiate a retriever with postgres repo
    retriever = Retriever(repo)
    candidates = await retriever.retrieve(tenant, user, "Sensitive developer credentials", query_embedding=None)
    # The list of candidates must not contain our deleted memory ID
    candidate_ids = [c.memory.id for c in candidates]
    assert mid not in candidate_ids

    # C. Context Composition -> Should exclude deleted record from model context
    coord = RetrievalCoordinator(
        embedding_service=get_embedding_service(),
        retriever=retriever,
        ranker=Ranker(),
        context_composer=ContextComposer()
    )
    context, used_memories, mode = await coord.retrieve_context(tenant, user, "Sensitive developer credentials")
    used_ids = [m.memory_id for m in used_memories]
    assert mid not in used_ids
    assert "Sensitive developer credentials key Sk-999" not in context

    # D. Immutable Audit Retention -> Events are still fully accessible in audit logs
    events = await audit_repo.list_events(tenant_id=tenant, memory_id=mid)
    assert len(events) >= 2  # Created + Deleted
    actions = [e.action for e in events]
    assert AuditEventAction.MEMORY_CREATED in actions
    assert AuditEventAction.MEMORY_DELETED in actions

    # E. Physical Compaction
    # Simulating CompactionWorker processing deleted records
    # Fetch record directly using repo backchannel (bypassing governance checks)
    db_record = await repo.get_by_id(mid, tenant, user)
    assert db_record.status == MemoryStatus.DELETED
    
    # Compaction replaces content with tombstone and wipes embeddings
    db_record.content = "[COMPACTED]"
    db_record.embedding = None
    
    compacted = await repo.update(db_record)
    assert compacted.content == "[COMPACTED]"
    assert compacted.embedding is None
