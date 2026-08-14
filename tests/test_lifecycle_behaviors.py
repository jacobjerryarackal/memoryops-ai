import os
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import dotenv
dotenv.load_dotenv()

from app.domain import (
    MemoryRecord,
    MemoryStatus,
    MemoryType,
    Sensitivity,
    PolicyDecision,
    LifecycleJobStatus,
)
from app.runtime import (
    get_memory_repository,
    get_lifecycle_repository,
    get_lifecycle_runner,
    get_worker_scheduler,
    get_governance_service,
)
from app.services.lifecycle import WorkerScheduler
from app.services.governance import GovernanceValidationError
from app.repositories.postgres_connection import db_manager


async def clean_all():
    db_type = os.environ.get("DATABASE_TYPE", "memory").strip().lower()
    repo = get_memory_repository()
    lifecycle_repo = get_lifecycle_repository()

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
            await conn.execute("TRUNCATE TABLE memories, memory_audit_logs, lifecycle_run_history, idempotency_records CASCADE;")
    else:
        # In-memory clean up
        repo._records.clear()
        lifecycle_repo._runs.clear()


@pytest.mark.anyio
async def test_retention_and_expiration():
    await clean_all()
    repo = get_memory_repository()
    runner = get_lifecycle_runner()

    now = datetime.now(timezone.utc)

    # 1. Expired memory record
    expired_id = uuid4()
    expired_rec = MemoryRecord(
        id=expired_id,
        tenant_id="tenant_a",
        user_id="user_a",
        content="I am expired.",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test",
        expires_at=now - timedelta(seconds=10),
    )
    await repo.create(expired_rec)

    # 2. Expired memory under active legal hold (should not be deleted)
    held_id = uuid4()
    held_rec = MemoryRecord(
        id=held_id,
        tenant_id="tenant_a",
        user_id="user_a",
        content="I am expired but held.",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test",
        expires_at=now - timedelta(seconds=10),
        legal_hold=True,
    )
    await repo.create(held_rec)

    # 3. Not expired memory record
    valid_id = uuid4()
    valid_rec = MemoryRecord(
        id=valid_id,
        tenant_id="tenant_a",
        user_id="user_a",
        content="I am still valid.",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test",
        expires_at=now + timedelta(days=5),
    )
    await repo.create(valid_rec)

    # Run retention worker
    run = await runner.run_job("retention_worker", "tenant_a", "user_a", now=now)
    assert run.status == LifecycleJobStatus.SUCCESS
    assert run.records_processed == 1

    # Verify states
    expired = await repo.get_by_id(expired_id, "tenant_a", "user_a")
    assert expired is not None
    assert expired.status == MemoryStatus.DELETED
    
    # Retrieve directly from list_by_status
    deleted_recs = await repo.list_by_status("tenant_a", "user_a", MemoryStatus.DELETED)
    assert len(deleted_recs) == 1
    assert deleted_recs[0].id == expired_id

    # The held memory should remain active
    held = await repo.get_by_id(held_id, "tenant_a", "user_a")
    assert held is not None
    assert held.status == MemoryStatus.ACTIVE


@pytest.mark.anyio
async def test_decay_processing():
    await clean_all()
    repo = get_memory_repository()
    runner = get_lifecycle_runner()

    now = datetime.now(timezone.utc)

    # 1. Decay candidate (updated more than 30 days ago)
    decay_id = uuid4()
    decay_rec = MemoryRecord(
        id=decay_id,
        tenant_id="tenant_a",
        user_id="user_a",
        content="Decay candidate.",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        importance=5,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test",
        created_at=now - timedelta(days=35),
        updated_at=now - timedelta(days=35),
    )
    await repo.create(decay_rec)

    # 2. Decay candidate under legal hold (should not decay)
    held_decay_id = uuid4()
    held_decay_rec = MemoryRecord(
        id=held_decay_id,
        tenant_id="tenant_a",
        user_id="user_a",
        content="Decay candidate under hold.",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        importance=5,
        legal_hold=True,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test",
        created_at=now - timedelta(days=35),
        updated_at=now - timedelta(days=35),
    )
    await repo.create(held_decay_rec)

    # Run decay worker
    run = await runner.run_job("decay_worker", "tenant_a", "user_a", now=now, decay_days=30)
    assert run.status == LifecycleJobStatus.SUCCESS
    assert run.records_processed == 1

    # Verify decay
    decayed = await repo.get_by_id(decay_id, "tenant_a", "user_a")
    assert decayed.importance == 4

    held = await repo.get_by_id(held_decay_id, "tenant_a", "user_a")
    assert held.importance == 5

    # 3. Test archiving transition when importance hits 0
    decayed.importance = 1
    await repo.update(decayed)

    # We run with decay_days=0 and a future now so it forces decay on the newly updated record
    run2 = await runner.run_job("decay_worker", "tenant_a", "user_a", now=now + timedelta(seconds=5), decay_days=0)
    assert run2.records_processed == 1

    archived = await repo.get_by_id(decay_id, "tenant_a", "user_a")
    assert archived.importance == 0
    assert archived.status == MemoryStatus.ARCHIVED
    assert archived.archived_at is not None


@pytest.mark.anyio
async def test_reflection_proposal_generation():
    await clean_all()
    repo = get_memory_repository()
    runner = get_lifecycle_runner()

    # 1. Create two highly similar memories (high Jaccard Jaccard Jaccard Jaccard overlap)
    rec1_id = uuid4()
    rec1 = MemoryRecord(
        id=rec1_id,
        tenant_id="tenant_a",
        user_id="user_a",
        content="Jacob Jerry Arackal is a Python engineer based in Munich.",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test",
    )
    await repo.create(rec1)

    rec2_id = uuid4()
    rec2 = MemoryRecord(
        id=rec2_id,
        tenant_id="tenant_a",
        user_id="user_a",
        content="Jacob J Arackal works as a Python engineer in Munich.",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test",
    )
    await repo.create(rec2)

    # 2. Run reflection worker
    run = await runner.run_job("reflection_worker", "tenant_a", "user_a", jaccard_threshold=0.5)
    assert run.status == LifecycleJobStatus.SUCCESS
    assert run.records_processed == 1

    # Verify a pending proposal was created
    pending_recs = await repo.list_by_status("tenant_a", "user_a", MemoryStatus.PENDING)
    assert len(pending_recs) == 1
    proposal = pending_recs[0]
    assert "Proposed Merge" in proposal.content
    assert proposal.source_conversation_id == "reflection_proposal"
    assert str(rec1_id) in proposal.source_excerpt
    assert str(rec2_id) in proposal.source_excerpt

    # 3. Running again should NOT create duplicate proposals
    run2 = await runner.run_job("reflection_worker", "tenant_a", "user_a", jaccard_threshold=0.5)
    assert run2.records_processed == 0
    
    pending_recs_again = await repo.list_by_status("tenant_a", "user_a", MemoryStatus.PENDING)
    assert len(pending_recs_again) == 1


@pytest.mark.anyio
async def test_compaction_and_legal_hold():
    await clean_all()
    repo = get_memory_repository()
    runner = get_lifecycle_runner()

    # 1. Normal logically deleted memory (should be compacted)
    del_id = uuid4()
    del_rec = MemoryRecord(
        id=del_id,
        tenant_id="tenant_a",
        user_id="user_a",
        content="Sensitive deleted content.",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.DELETED,
        embedding=[0.1] * 1536,
        deleted_at=datetime.now(timezone.utc),
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test",
    )
    db_type = os.environ.get("DATABASE_TYPE", "memory").strip().lower()
    if db_type == "postgres":
        repo._records[del_id] = del_rec
    else:
        repo._records[del_id] = del_rec.model_copy(deep=True)

    # 2. Logically deleted memory under legal hold (should NOT be compacted)
    held_del_id = uuid4()
    held_del_rec = MemoryRecord(
        id=held_del_id,
        tenant_id="tenant_a",
        user_id="user_a",
        content="Sensitive held deleted content.",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.DELETED,
        legal_hold=True,
        embedding=[0.2] * 1536,
        deleted_at=datetime.now(timezone.utc),
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test",
    )
    if db_type == "postgres":
        repo._records[held_del_id] = held_del_rec
    else:
        repo._records[held_del_id] = held_del_rec.model_copy(deep=True)

    # Run compaction worker
    run = await runner.run_job("compaction_worker", "tenant_a", "user_a")
    assert run.status == LifecycleJobStatus.SUCCESS
    assert run.records_processed == 1

    # Verify normal record is compacted
    deleted_recs = await repo.list_by_status("tenant_a", "user_a", MemoryStatus.DELETED)
    
    normal_check = next(r for r in deleted_recs if r.id == del_id)
    assert normal_check.content == "[COMPACTED]"
    assert normal_check.embedding is None
    assert normal_check.tenant_id == "tenant_a"
    assert normal_check.user_id == "user_a"

    # Verify held record is untouched
    held_check = next(r for r in deleted_recs if r.id == held_del_id)
    assert held_check.content == "Sensitive held deleted content."
    assert held_check.embedding == pytest.approx([0.2] * 1536)


@pytest.mark.anyio
async def test_repeated_scheduler_execution():
    await clean_all()
    runner = get_lifecycle_runner()
    
    scheduler = WorkerScheduler(runner)
    scheduler.schedule_job("compaction_worker", 0.05)
    scheduler.schedule_job("decay_worker", 0.05)

    await scheduler.start("tenant_a", "user_a")
    await asyncio.sleep(0.3)
    await scheduler.stop()

    history_repo = get_lifecycle_repository()
    compaction_runs = await history_repo.list_runs(job_name="compaction_worker")
    decay_runs = await history_repo.list_runs(job_name="decay_worker")
    
    assert len(compaction_runs) > 0
    assert len(decay_runs) > 0
