import os
import pytest
import asyncio
from uuid import uuid4
from datetime import datetime, timezone
import asyncpg

from app.domain import MemoryRecord, MemoryStatus, MemoryType, PolicyDecision, Sensitivity
from app.repositories.postgres import PostgreSQLMemoryRepository, scoped_connection, rls_bypass
from app.repositories.postgres_connection import db_manager

# Ensure the tests run with postgres DATABASE_TYPE
pytestmark = pytest.mark.skipif(
    os.environ.get("DATABASE_TYPE", "memory").strip().lower() != "postgres",
    reason="RLS adversarial tests only run on PostgreSQL"
)


from app.config import settings

async def setup_test_db():
    # Helper to clean DB under bypass
    if db_manager.pool is not None:
        if db_manager.pool._loop.is_closed():
            db_manager.pool = None
    if db_manager.pool is None:
        await db_manager.initialize()
    async with rls_bypass():
        async with scoped_connection("", "") as conn:
            await conn.execute("TRUNCATE TABLE memories, memory_audit_logs CASCADE;")



@pytest.fixture(autouse=True)
async def setup_app_user_pool():
    # 1. Close postgres pool if exists (handling closed loops gracefully)
    if db_manager.pool is not None:
        try:
            if db_manager.pool._loop.is_closed():
                db_manager.pool = None
            else:
                await db_manager.close()
        except Exception:
            db_manager.pool = None
        
    # 2. Swap settings to connect as memoryops_app
    orig_user = settings.postgres_user
    orig_password = settings.postgres_password
    settings.postgres_user = "memoryops_app"
    settings.postgres_password = "memoryops_password"
    
    # 3. Initialize pool under app user
    await db_manager.initialize()
    
    yield
    
    # 4. Cleanup and restore orig user
    if db_manager.pool is not None:
        try:
            if db_manager.pool._loop.is_closed():
                db_manager.pool = None
            else:
                await db_manager.close()
        except Exception:
            db_manager.pool = None
    settings.postgres_user = orig_user
    settings.postgres_password = orig_password



@pytest.mark.anyio

async def test_rls_tenant_isolation_adversarial():
    await setup_test_db()
    
    repo = PostgreSQLMemoryRepository()
    
    # 1. Create a record under tenant_a / user_a
    rec1_id = uuid4()
    rec1 = MemoryRecord(
        id=rec1_id,
        tenant_id="tenant_a",
        user_id="user_a",
        content="Tenant A secret content.",
        memory_type=MemoryType.SEMANTIC,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test"
    )
    await repo.create(rec1)
    
    # 2. Assert tenant_a can read the record
    fetched_a = await repo.get_by_id(rec1_id, "tenant_a", "user_a")
    assert fetched_a is not None
    assert fetched_a.content == "Tenant A secret content."
    
    # 3. Assert tenant_b/user_a CANNOT read the record (returns None due to RLS filtering)
    fetched_b = await repo.get_by_id(rec1_id, "tenant_b", "user_a")
    assert fetched_b is None

    # 4. Assert list_active for tenant_b is empty
    active_b = await repo.list_active("tenant_b", "user_a")
    assert len(active_b) == 0

    # 5. Assert direct raw queries under scoped connection are filtered
    async with scoped_connection("tenant_b", "user_a") as conn:
        # Diagnostic check
        curr_user = await conn.fetchval("SELECT current_user;")
        rls_tenant = await conn.fetchval("SELECT current_setting('app.current_tenant_id', true);")
        rls_user = await conn.fetchval("SELECT current_setting('app.current_user_id', true);")
        bypass = await conn.fetchval("SELECT current_setting('app.bypass_rls', true);")
        
        # Check if RLS is enabled on memories table
        rls_enabled = await conn.fetchval("""
            SELECT relrowsecurity FROM pg_class WHERE relname = 'memories';
        """)
        rls_forced = await conn.fetchval("""
            SELECT relforcerowsecurity FROM pg_class WHERE relname = 'memories';
        """)
        
        print(f"\n[RLS DIAG] User: {curr_user} | Tenant Setting: {rls_tenant} | User Setting: {rls_user} | Bypass: {bypass}")
        print(f"[RLS DIAG] Table RLS Enabled: {rls_enabled} | Table RLS Forced: {rls_forced}")
        
        rows = await conn.fetch("SELECT * FROM memories WHERE id = $1", rec1_id)
        assert len(rows) == 0


    # 6. Assert direct raw update under tenant_b connection fails to touch tenant_a record
    async with scoped_connection("tenant_b", "user_a") as conn:
        res = await conn.execute("UPDATE memories SET content = 'hacked' WHERE id = $1", rec1_id)
        # In postgres, RLS makes the row invisible, so UPDATE touches 0 rows
        assert "UPDATE 0" in res

    # Verify content was not modified
    async with rls_bypass():
        async with scoped_connection("", "") as conn:
            val = await conn.fetchval("SELECT content FROM memories WHERE id = $1", rec1_id)
            assert val == "Tenant A secret content."



@pytest.mark.anyio
async def test_rls_bypass_admin_operations():
    await setup_test_db()
    repo = PostgreSQLMemoryRepository()
    
    rec_id = uuid4()
    rec = MemoryRecord(
        id=rec_id,
        tenant_id="tenant_a",
        user_id="user_a",
        content="Secret",
        memory_type=MemoryType.SEMANTIC,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test"
    )
    await repo.create(rec)
    
    # Under bypass, we should be able to read all records across tenants
    async with rls_bypass():
        async with scoped_connection("", "") as conn:
            rows = await conn.fetch("SELECT * FROM memories;")
            assert len(rows) == 1
            assert rows[0]["content"] == "Secret"


@pytest.mark.anyio
async def test_postgres_optimistic_concurrency_control():
    await setup_test_db()
    repo = PostgreSQLMemoryRepository()
    
    mid = uuid4()
    rec = MemoryRecord(
        id=mid,
        tenant_id="tenant_a",
        user_id="user_a",
        content="Original content",
        memory_type=MemoryType.SEMANTIC,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test"
    )
    
    # Create record
    created = await repo.create(rec)
    assert created.version == 1
    
    # 1. Update successfully
    created.content = "New content"
    updated = await repo.update(created)
    assert updated.version == 2
    assert updated.content == "New content"
    
    # 2. Update with stale version (1) -> raises conflict
    created.content = "Conflict content"
    # created.version is still 1
    with pytest.raises(ValueError) as exc_info:
        await repo.update(created)
    assert "Concurrency conflict" in str(exc_info.value)


