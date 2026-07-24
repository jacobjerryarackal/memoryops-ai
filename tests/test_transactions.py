import os
import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timezone
import dotenv

from app.domain import MemoryRecord, MemoryStatus, MemoryType, Sensitivity, PolicyDecision, AuditEvent, AuditEventAction, CandidateMemory
from app.runtime import get_memory_repository, get_audit_service, get_transaction_manager
from app.services.write import WriteService
from app.services.governance import GovernanceService
from app.policy.broker import PolicyBroker
from app.repositories.postgres_connection import db_manager

# Load environment configuration
dotenv.load_dotenv()


async def clean_database():
    """Teardown database/in-memory records before each test case."""
    db_type = os.environ.get("DATABASE_TYPE", "memory").strip().lower()
    if db_type == "postgres":
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
    else:
        repo = get_memory_repository()
        audit = get_audit_service()
        if hasattr(repo, "_records"):
            repo._records.clear()
        if hasattr(audit, "_events"):
            audit._events.clear()


class StubBroker(PolicyBroker):
    """Stub Broker to return predetermined policy decisions in tests."""
    def __init__(self, decision: PolicyDecision = PolicyDecision.SAVE, reason: str = "Test admission"):
        self.decision = decision
        self.reason = reason

    async def evaluate(self, candidate: CandidateMemory):
        from app.domain import PolicyResult
        return PolicyResult(decision=self.decision, reason=self.reason)


def test_transaction_commit_success():
    async def run():
        await clean_database()

        repo = get_memory_repository()
        audit = get_audit_service()
        tx_manager = get_transaction_manager()

        broker = StubBroker(PolicyDecision.SAVE, "Admitted successfully")
        write_service = WriteService(broker=broker, repository=repo, audit_service=audit, transaction_manager=tx_manager)

        candidate = CandidateMemory(
            tenant_id="tenant_tx",
            user_id="user_tx",
            content="Successful transaction content",
            memory_type=MemoryType.SEMANTIC,
            confidence=1.0,
            importance=5,
            sensitivity=Sensitivity.LOW
        )

        # Execute write path in transaction
        result = await write_service.process(candidate)
        assert result.memory is not None
        mem_id = result.memory.id

        # Verify both memory record and audit event are persisted successfully
        fetched_mem = await repo.get_by_id(mem_id, "tenant_tx", "user_tx")
        assert fetched_mem is not None
        assert fetched_mem.content == "Successful transaction content"

        audit_events = await audit.list_events("tenant_tx", memory_id=mem_id)
        assert len(audit_events) == 1
        assert audit_events[0].action == AuditEventAction.MEMORY_CREATED
    asyncio.run(run())


def test_transaction_rollback_on_repository_failure():
    async def run():
        await clean_database()

        repo = get_memory_repository()
        audit = get_audit_service()
        tx_manager = get_transaction_manager()

        broker = StubBroker(PolicyDecision.SAVE, "Admitted successfully")
        write_service = WriteService(broker=broker, repository=repo, audit_service=audit, transaction_manager=tx_manager)

        rec_id = uuid4()
        # Seed an existing record to force a duplicate key validation error in the repo
        seed_record = MemoryRecord(
            id=rec_id,
            tenant_id="tenant_tx",
            user_id="user_tx",
            content="Existing content",
            memory_type=MemoryType.SEMANTIC,
            initial_policy_decision=PolicyDecision.SAVE,
            initial_policy_reason="Seed"
        )
        await repo.create(seed_record)

        # Clear audit log to isolate this test's events
        if hasattr(audit, "_events"):
            audit._events.clear()

        # Build candidate with matching duplicate UUID
        candidate = CandidateMemory(
            tenant_id="tenant_tx",
            user_id="user_tx",
            content="Duplicate ID content",
            memory_type=MemoryType.SEMANTIC,
            confidence=1.0,
            importance=5,
            sensitivity=Sensitivity.LOW
        )

        # Monkeypatch WriteService to force duplicate UUID creation
        original_process = write_service.process
        async def mock_process(cand):
            # Intercept and override the created record's ID to be the duplicate rec_id
            async with tx_manager.transaction():
                record = MemoryRecord(
                    id=rec_id,  # DUPLICATE ID
                    tenant_id=cand.tenant_id,
                    user_id=cand.user_id,
                    content=cand.content,
                    memory_type=cand.memory_type,
                    status=MemoryStatus.ACTIVE,
                    initial_policy_decision=PolicyDecision.SAVE,
                    initial_policy_reason="Duplicate test"
                )
                created = await repo.create(record)
                
                audit_event = AuditEvent(
                    tenant_id=cand.tenant_id,
                    user_id=cand.user_id,
                    memory_id=created.id,
                    action=AuditEventAction.MEMORY_CREATED,
                    reason="Duplicate test metadata"
                )
                await audit.record(audit_event)

        with pytest.raises(ValueError, match="Duplicate key|already exists"):
            await mock_process(candidate)

        # Assert: No audit event was written because of the repository failure rollback
        events = await audit.list_events("tenant_tx")
        assert len(events) == 0

        # Assert: The duplicate insertion content is rolled back, seed record content is unaffected
        fetched_mem = await repo.get_by_id(rec_id, "tenant_tx", "user_tx")
        assert fetched_mem is not None
        assert fetched_mem.content == "Existing content"  # Retained original content
    asyncio.run(run())


def test_transaction_rollback_on_audit_failure(monkeypatch):
    async def run():
        await clean_database()

        repo = get_memory_repository()
        audit = get_audit_service()
        tx_manager = get_transaction_manager()

        broker = StubBroker(PolicyDecision.SAVE, "Admitted successfully")
        write_service = WriteService(broker=broker, repository=repo, audit_service=audit, transaction_manager=tx_manager)

        # Monkeypatch audit_service.record to fail with an exception
        async def failing_record(event):
            raise RuntimeError("Database connection lost during audit write")
        monkeypatch.setattr(audit, "record", failing_record)

        candidate = CandidateMemory(
            tenant_id="tenant_tx",
            user_id="user_tx",
            content="Transactional write with failing audit",
            memory_type=MemoryType.SEMANTIC,
            confidence=1.0,
            importance=5,
            sensitivity=Sensitivity.LOW
        )

        # Attempt process. Audit failure should rollback the repository write!
        with pytest.raises(RuntimeError, match="Database connection lost during audit write"):
            await write_service.process(candidate)

        # Assert: The repository write was rolled back successfully, and the memory record does NOT exist
        memories = await repo.list_active("tenant_tx", "user_tx")
        assert len(memories) == 0
    asyncio.run(run())


def test_nested_transaction_rollback():
    async def run():
        await clean_database()

        repo = get_memory_repository()
        audit = get_audit_service()
        tx_manager = get_transaction_manager()

        id_a = uuid4()
        id_b = uuid4()

        async def run_nested_txs():
            async with tx_manager.transaction():
                # 1. Write Memory A (Outer Transaction)
                rec_a = MemoryRecord(
                    id=id_a,
                    tenant_id="tenant_tx",
                    user_id="user_tx",
                    content="Memory A (Outer)",
                    memory_type=MemoryType.SEMANTIC,
                    initial_policy_decision=PolicyDecision.SAVE,
                    initial_policy_reason="Outer"
                )
                await repo.create(rec_a)

                try:
                    # 2. Start Nested Transaction
                    async with tx_manager.transaction():
                        rec_b = MemoryRecord(
                            id=id_b,
                            tenant_id="tenant_tx",
                            user_id="user_tx",
                            content="Memory B (Inner)",
                            memory_type=MemoryType.SEMANTIC,
                            initial_policy_decision=PolicyDecision.SAVE,
                            initial_policy_reason="Inner"
                        )
                        await repo.create(rec_b)
                        
                        # Raise inner exception to force inner rollback
                        raise ValueError("Inner failure")
                except ValueError as e:
                    # Catch nested error to allow the outer transaction to proceed
                    assert str(e) == "Inner failure"

        # Execute transaction block
        await run_nested_txs()

        # Assertions:
        # Memory A should exist (Outer committed successfully)
        fetched_a = await repo.get_by_id(id_a, "tenant_tx", "user_tx")
        assert fetched_a is not None
        assert fetched_a.content == "Memory A (Outer)"

        # Memory B should NOT exist (Inner was rolled back via SAVEPOINT/snapshot rollback)
        fetched_b = await repo.get_by_id(id_b, "tenant_tx", "user_tx")
        assert fetched_b is None
    asyncio.run(run())
