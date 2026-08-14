import pytest
import os
import sys
import asyncio
from unittest.mock import patch, MagicMock
from uuid import uuid4
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.main import app
from app.domain import CandidateMemory, MemoryRecord, MemoryType, Sensitivity, MemoryStatus
from app.domain.enums import PolicyDecision, AuditEventAction
from app.services.write import WriteService, TargetUnavailableError
from app.services.retrieval import RetrievalCoordinator, RetrievalMode
from app.policy.broker import PolicyBroker
from app.repositories import InMemoryMemoryRepository
from app.services.audit import InMemoryAuditService
from app.services.idempotency import IdempotencyService, idempotency_service

client = TestClient(app)


@pytest.fixture(autouse=True)
async def clean_database():
    from app.repositories.postgres_connection import db_manager
    # Ensure pool is initialized if we are using postgres
    db_type = os.environ.get("DATABASE_TYPE", "memory").strip().lower()
    if db_type == "postgres":
        if db_manager.pool is None:
            await db_manager.initialize()
        if db_manager.pool is not None:
            try:
                async with db_manager.pool.acquire() as conn:
                    await conn.execute("TRUNCATE TABLE memories, memory_audit_logs, lifecycle_run_history, idempotency_records CASCADE;")
            except Exception:
                pass
    idempotency_service.clear()
    yield



# 1. Database Unavailable / Timeout
@pytest.mark.anyio
async def test_database_unavailable_resilience():
    # Mock scoped_connection context manager to raise an operational error
    with patch("app.repositories.postgres.scoped_connection") as mock_conn:
        mock_conn.side_effect = Exception("PostgreSQL pool connection refused.")
        
        from app.repositories.postgres import PostgreSQLMemoryRepository
        repo = PostgreSQLMemoryRepository()
        
        record = MemoryRecord(
            tenant_id="t1",
            user_id="u1",
            content="test",
            memory_type=MemoryType.SEMANTIC,
            initial_policy_decision=PolicyDecision.SAVE,
            initial_policy_reason="test"
        )
        
        with pytest.raises(Exception) as exc_info:
            await repo.create(record)
        assert "connection refused" in str(exc_info.value)


# 2. Policy Broker Failure
@pytest.mark.anyio
async def test_policy_failure_rollbacks_write():
    repo = InMemoryMemoryRepository()
    audit = InMemoryAuditService()
    
    # Mock PolicyBroker to raise exception
    mock_broker = MagicMock(spec=PolicyBroker)
    mock_broker.evaluate.side_effect = Exception("Policy engine unavailable.")
    
    with patch("app.runtime.get_memory_repository", return_value=repo), \
         patch("app.runtime.get_audit_service", return_value=audit):
        write_service = WriteService(broker=mock_broker, repository=repo, audit_service=audit)
        
        candidate = CandidateMemory(
            tenant_id="t1",
            user_id="u1",
            content="Resilience test content",
            memory_type=MemoryType.SEMANTIC,
            confidence=1.0,
            importance=5,
            sensitivity=Sensitivity.LOW,
        )
        
        with pytest.raises(Exception) as exc_info:
            await write_service.process(candidate)
        
        assert "Policy engine unavailable" in str(exc_info.value)
        # Ensure transaction rolled back: no memories created, no audit logs recorded
        assert len(repo._records) == 0
        assert len(audit._events) == 0


# 3. Embedding Failure (Degrades Gracefully)
@pytest.mark.anyio
async def test_embedding_failure_degrades_gracefully():
    # Setup mocks for coordinator
    mock_embed = MagicMock()
    mock_embed.generate_embedding.side_effect = Exception("Embedding provider timeout.")
    
    repo = InMemoryMemoryRepository()
    # Seed a memory
    record = MemoryRecord(
        id=uuid4(),
        tenant_id="t1",
        user_id="u1",
        content="My favorite color is green.",
        memory_type=MemoryType.SEMANTIC,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="seed",
        status=MemoryStatus.ACTIVE
    )
    await repo.create(record)
    
    from app.services.retrieval import Retriever, Ranker, ContextComposer
    retriever = Retriever(repo)
    ranker = Ranker()
    composer = ContextComposer()
    
    coordinator = RetrievalCoordinator(
        embedding_service=mock_embed,
        retriever=retriever,
        ranker=ranker,
        context_composer=composer,
    )
    
    # Execute retrieval
    context, used_memories, mode = await coordinator.retrieve_context(
        tenant_id="t1",
        user_id="u1",
        query_text="favorite color",
    )
    
    # Verify fallback mode is selected and it successfully returned results (degraded-safe)
    assert mode == RetrievalMode.FALLBACK
    assert "favorite color is green" in context
    assert len(used_memories) == 1


# 4. Audit Recording Failure (Atomic Rollback)
@pytest.mark.anyio
async def test_audit_failure_atomic_rollback():
    repo = InMemoryMemoryRepository()
    
    # Mock AuditService to fail
    mock_audit = MagicMock()
    mock_audit.record.side_effect = Exception("Audit storage disk full.")
    
    broker = PolicyBroker(repository=repo)
    
    with patch("app.runtime.get_memory_repository", return_value=repo), \
         patch("app.runtime.get_audit_service", return_value=mock_audit):
        write_service = WriteService(broker=broker, repository=repo, audit_service=mock_audit)
        
        candidate = CandidateMemory(
            tenant_id="t1",
            user_id="u1",
            content="Important secure fact",
            memory_type=MemoryType.SEMANTIC,
            confidence=1.0,
            importance=5,
            sensitivity=Sensitivity.LOW,
        )
        
        with pytest.raises(Exception) as exc_info:
            await write_service.process(candidate)
            
        assert "Audit storage disk full" in str(exc_info.value)
        # Ensure memory record was rolled back (not saved) because audit log failed
        assert len(repo._records) == 0


# 5. Evidence Retrieval Failure
@pytest.mark.anyio
async def test_evidence_failure_safe_degradation():
    from app.services.governance import GovernanceService
    repo = InMemoryMemoryRepository()
    mock_audit = MagicMock()
    mock_audit.list_events.side_effect = Exception("Audit trail DB corruption.")
    
    broker = PolicyBroker(repository=repo)
    gov_service = GovernanceService(repository=repo, audit_service=mock_audit, broker=broker)
    
    # Seed a memory
    mid = uuid4()
    record = MemoryRecord(
        id=mid,
        tenant_id="t1",
        user_id="u1",
        content="Seattle",
        memory_type=MemoryType.SEMANTIC,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="seed",
        status=MemoryStatus.ACTIVE
    )
    await repo.create(record)
    
    with pytest.raises(Exception) as exc_info:
        await gov_service.get_memory_evidence(memory_id=mid, tenant_id="t1", user_id="u1")
    assert "Audit trail DB corruption" in str(exc_info.value)


# 6. SDK Request Timeout
def test_sdk_timeout_handling():
    with patch("requests.request") as mock_request:
        import requests
        mock_request.side_effect = requests.exceptions.Timeout("Connection timed out.")
        
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../sdk/memoryops-sdk")))
        from memoryops_sdk import MemoryOpsClient, MemoryOpsError
        
        client = MemoryOpsClient("http://api.memoryops.local", max_retries=0)
        with pytest.raises(MemoryOpsError) as exc_info:
            client.list_memories(tenant_id="t1", user_id="u1")
        assert "timed out" in str(exc_info.value) or "Connection timed out" in str(exc_info.value)


# 7. Duplicate Request (Idempotency Cache Hits)
@pytest.mark.anyio
async def test_duplicate_request_idempotency():
    idem = IdempotencyService()
    key = "idem-key-duplicate"
    payload = {"query": "hello"}
    
    # Cache first response
    await idem.get_cached_response(key, "t1", "u1", payload)
    await idem.cache_response(key, "t1", "u1", 200, {"response": "world"}, payload)
    
    # Second duplicate request matches key and payload -> returns cached response
    status_code, body = await idem.get_cached_response(key, "t1", "u1", payload)
    assert status_code == 200
    assert body == {"response": "world"}


# 8. Concurrent Request Lock (Conflict on same key)
@pytest.mark.anyio
async def test_concurrent_request_idempotency_conflict():
    idem = IdempotencyService()
    key = "idem-key-concurrent"
    payload = {"query": "hello"}
    
    # First request starts processing (acquires lock, response status is 102)
    await idem.get_cached_response(key, "t1", "u1", payload)
    
    # Second concurrent request with same key and payload raises 409 Conflict
    with pytest.raises(HTTPException) as exc_info:
        await idem.get_cached_response(key, "t1", "u1", payload)
    assert exc_info.value.status_code == 409
    assert "concurrent request" in exc_info.value.detail.lower()
