import pytest
import os
from uuid import uuid4
from datetime import datetime, timezone

from app.domain import MemoryRecord, MemoryStatus, MemoryType, PolicyDecision
from app.repositories.postgres import PostgreSQLMemoryRepository, scoped_connection, rls_bypass
from app.repositories.postgres_connection import db_manager
from app.repositories.transactions import TransactionManager
from app.runtime import get_memory_repository, get_audit_service
from tests.test_rls_adversarial import setup_test_db


@pytest.fixture(autouse=True)
async def ensure_db():
    # If using postgres type, ensure pool is active and clean
    db_type = os.environ.get("DATABASE_TYPE", "memory").strip().lower()
    if db_type == "postgres":
        await setup_test_db()
    yield


@pytest.mark.anyio
async def test_postgres_transaction_rollback():
    db_type = os.environ.get("DATABASE_TYPE", "memory").strip().lower()
    if db_type != "postgres":
        pytest.skip("This test is specific to PostgreSQL database transactions.")
        
    repo = PostgreSQLMemoryRepository()
    tx_manager = TransactionManager(force_in_memory=False)
    
    mid = uuid4()
    rec = MemoryRecord(
        id=mid,
        tenant_id="tenant_tx",
        user_id="user_tx",
        content="This should not be saved",
        memory_type=MemoryType.SEMANTIC,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="tx"
    )
    
    # 1. Run transaction block that raises exception
    with pytest.raises(RuntimeError) as exc_info:
        async with tx_manager.transaction():
            await repo.create(rec)
            raise RuntimeError("Failure injection: simulate runtime crash")
            
    assert "Failure injection" in str(exc_info.value)
    
    # 2. Verify record was rolled back and is not in db
    fetched = await repo.get_by_id(mid, "tenant_tx", "user_tx")
    assert fetched is None


@pytest.mark.anyio
async def test_postgres_nested_savepoint_rollback():
    db_type = os.environ.get("DATABASE_TYPE", "memory").strip().lower()
    if db_type != "postgres":
        pytest.skip("This test is specific to PostgreSQL savepoints.")
        
    repo = PostgreSQLMemoryRepository()
    tx_manager = TransactionManager(force_in_memory=False)
    
    mid_outer = uuid4()
    mid_inner = uuid4()
    
    rec_outer = MemoryRecord(
        id=mid_outer,
        tenant_id="tenant_tx",
        user_id="user_tx",
        content="Outer transaction commit",
        memory_type=MemoryType.SEMANTIC,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="outer"
    )
    
    rec_inner = MemoryRecord(
        id=mid_inner,
        tenant_id="tenant_tx",
        user_id="user_tx",
        content="Inner transaction rollback",
        memory_type=MemoryType.SEMANTIC,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="inner"
    )
    
    # Run root transaction
    async with tx_manager.transaction():
        # Outer create succeeds
        await repo.create(rec_outer)
        
        # Nested transaction block throws error
        try:
            async with tx_manager.transaction():
                await repo.create(rec_inner)
                raise RuntimeError("Inner savepoint failure injection")
        except RuntimeError as e:
            assert "Inner savepoint failure" in str(e)
            
    # After outer transaction successfully commits:
    # Outer record MUST exist, inner record MUST be rolled back
    fetched_outer = await repo.get_by_id(mid_outer, "tenant_tx", "user_tx")
    assert fetched_outer is not None
    assert fetched_outer.content == "Outer transaction commit"
    
    fetched_inner = await repo.get_by_id(mid_inner, "tenant_tx", "user_tx")
    assert fetched_inner is None


@pytest.mark.anyio
async def test_in_memory_simulated_rollback():
    # Force simulated in-memory transaction rollback
    repo = get_memory_repository()
    # Check that this is the in-memory repository
    from app.repositories import InMemoryMemoryRepository
    if not isinstance(repo, InMemoryMemoryRepository):
        pytest.skip("This test runs only when global repository is InMemory.")
        
    tx_manager = TransactionManager(force_in_memory=True)
    
    mid = uuid4()
    rec = MemoryRecord(
        id=mid,
        tenant_id="tenant_mem",
        user_id="user_mem",
        content="Memory rollback test",
        memory_type=MemoryType.SEMANTIC,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="seed",
    )
    
    with pytest.raises(RuntimeError):
        async with tx_manager.transaction():
            await repo.create(rec)
            # Verify record is temporarily present in repository dictionary
            assert mid in repo._records
            raise RuntimeError("Crash simulated")
            
    # Verify in-memory snapshot was restored and record is removed
    assert mid not in repo._records
