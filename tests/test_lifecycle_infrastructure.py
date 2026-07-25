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
    LifecycleRunHistory,
)
from app.runtime import (
    get_memory_repository,
    get_lifecycle_repository,
    get_lifecycle_runner,
    get_worker_scheduler,
    get_governance_service,
)
from app.services.lifecycle import LifecycleWorker, LifecycleRunner, WorkerScheduler
from app.services.governance import GovernanceValidationError
from app.repositories.postgres_connection import db_manager


class DummyWorker(LifecycleWorker):
    def __init__(self, name: str = "dummy_job", process_count: int = 1):
        self._name = name
        self.process_count = process_count
        self.run_count = 0

    @property
    def name(self) -> str:
        return self._name

    async def run(self, tenant_id: str, user_id: str, **kwargs) -> int:
        self.run_count += 1
        return self.process_count


class SleepWorker(LifecycleWorker):
    def __init__(self, name: str = "sleep_job", sleep_time: float = 0.5):
        self._name = name
        self.sleep_time = sleep_time

    @property
    def name(self) -> str:
        return self._name

    async def run(self, tenant_id: str, user_id: str, **kwargs) -> int:
        await asyncio.sleep(self.sleep_time)
        return 1


class FailWorker(LifecycleWorker):
    @property
    def name(self) -> str:
        return "fail_job"

    async def run(self, tenant_id: str, user_id: str, **kwargs) -> int:
        raise RuntimeError("Something went wrong.")


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
            await conn.execute("TRUNCATE TABLE memories, memory_audit_logs, lifecycle_run_history CASCADE;")
    else:
        # In-memory repository cleanup
        repo._records.clear()
        lifecycle_repo._runs.clear()


@pytest.mark.anyio
async def test_worker_registration():
    await clean_all()
    lifecycle_repo = get_lifecycle_repository()
    runner = LifecycleRunner(lifecycle_repo)

    worker1 = DummyWorker("job_1")
    worker2 = DummyWorker("job_2")

    runner.register_worker(worker1)
    runner.register_worker(worker2)

    assert "job_1" in runner._workers
    assert "job_2" in runner._workers

    # Expect error on duplicate registration
    with pytest.raises(ValueError, match="already registered"):
        runner.register_worker(DummyWorker("job_1"))


@pytest.mark.anyio
async def test_execution_history_success_and_fail():
    await clean_all()
    lifecycle_repo = get_lifecycle_repository()
    runner = LifecycleRunner(lifecycle_repo)

    success_worker = DummyWorker("success_job", process_count=5)
    fail_worker = FailWorker()

    runner.register_worker(success_worker)
    runner.register_worker(fail_worker)

    # 1. Test success run
    run1 = await runner.run_job("success_job", "tenant_a", "user_a")
    assert run1.status == LifecycleJobStatus.SUCCESS
    assert run1.records_processed == 5
    assert run1.completed_at is not None
    assert run1.error_message is None

    # Retrieve from repository
    persisted1 = await lifecycle_repo.get_run_by_id(run1.id)
    assert persisted1 is not None
    assert persisted1.status == LifecycleJobStatus.SUCCESS
    assert persisted1.records_processed == 5
    assert persisted1.metadata.get("tenant_id") == "tenant_a"

    # 2. Test fail run
    await asyncio.sleep(0.02)
    run2 = await runner.run_job("fail_job", "tenant_a", "user_a")
    assert run2.status == LifecycleJobStatus.FAILED
    assert run2.completed_at is not None
    assert "Something went wrong" in run2.error_message

    persisted2 = await lifecycle_repo.get_run_by_id(run2.id)
    assert persisted2 is not None
    assert persisted2.status == LifecycleJobStatus.FAILED
    assert "Something went wrong" in persisted2.error_message

    # Test list_runs
    all_runs = await lifecycle_repo.list_runs()
    assert len(all_runs) == 2
    # Check ordering is DESC (run2 was started after run1)
    assert all_runs[0].id == run2.id
    assert all_runs[1].id == run1.id

    # Filtered by job name
    filtered_runs = await lifecycle_repo.list_runs(job_name="success_job")
    assert len(filtered_runs) == 1
    assert filtered_runs[0].id == run1.id


@pytest.mark.anyio
async def test_scheduled_execution():
    await clean_all()
    lifecycle_repo = get_lifecycle_repository()
    runner = LifecycleRunner(lifecycle_repo)
    worker = DummyWorker("scheduled_job", process_count=1)
    runner.register_worker(worker)

    scheduler = WorkerScheduler(runner)
    scheduler.schedule_job("scheduled_job", 0.1)

    await scheduler.start("tenant_a", "user_a")
    # Wait for execution loop to trigger the scheduled job a few times
    await asyncio.sleep(0.7)
    await scheduler.stop()

    # Worker should have run at least 2 times
    assert worker.run_count >= 2

    # Check execution history
    runs = await lifecycle_repo.list_runs(job_name="scheduled_job")
    assert len(runs) >= 2
    success_runs = [run for run in runs if run.status == LifecycleJobStatus.SUCCESS]
    assert len(success_runs) >= 2


@pytest.mark.anyio
async def test_legal_hold_gating():
    await clean_all()
    repo = get_memory_repository()
    gov_service = get_governance_service()

    # 1. Create a memory record under active legal hold
    rec_held_id = uuid4()
    rec_held = MemoryRecord(
        id=rec_held_id,
        tenant_id="tenant_a",
        user_id="user_a",
        content="This memory is protected by legal hold.",
        memory_type=MemoryType.SEMANTIC,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test",
        legal_hold=True,
    )
    await repo.create(rec_held)

    # 2. Assert repository delete raises ValueError
    with pytest.raises(ValueError, match="legal hold"):
        await repo.delete(rec_held_id, "tenant_a", "user_a")

    # 3. Assert GovernanceService delete_memory raises GovernanceValidationError
    with pytest.raises(GovernanceValidationError, match="legal hold"):
        await gov_service.delete_memory(rec_held_id, "tenant_a", "user_a")

    # Verify status is still active (not deleted)
    persisted = await repo.get_by_id(rec_held_id, "tenant_a", "user_a")
    assert persisted is not None
    assert persisted.status == MemoryStatus.ACTIVE

    # 4. Create a normal memory record (no legal hold)
    rec_normal_id = uuid4()
    rec_normal = MemoryRecord(
        id=rec_normal_id,
        tenant_id="tenant_a",
        user_id="user_a",
        content="Normal memory without hold.",
        memory_type=MemoryType.SEMANTIC,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test",
        legal_hold=False,
    )
    await repo.create(rec_normal)

    # 5. Assert deletion succeeds
    deleted = await gov_service.delete_memory(rec_normal_id, "tenant_a", "user_a")
    assert deleted.status == MemoryStatus.DELETED


@pytest.mark.anyio
async def test_concurrent_execution_protection():
    await clean_all()
    lifecycle_repo = get_lifecycle_repository()
    runner = LifecycleRunner(lifecycle_repo)

    sleep_worker = SleepWorker("sleep_job", sleep_time=0.4)
    runner.register_worker(sleep_worker)

    # Start first run in the background
    task1 = asyncio.create_task(runner.run_job("sleep_job", "tenant_a", "user_a"))

    # Give it a tiny bit to start and lock
    await asyncio.sleep(0.05)

    # Attempt to start concurrent execution for the SAME tenant and user
    with pytest.raises(ValueError, match="Concurrency block"):
        await runner.run_job("sleep_job", "tenant_a", "user_a")

    # Attempt to start concurrently for a DIFFERENT tenant or user
    # This should succeed since scope isolation separates concurrency scopes
    run_diff = await runner.run_job("sleep_job", "tenant_b", "user_a")
    assert run_diff.status == LifecycleJobStatus.SUCCESS

    # Complete the first task
    res = await task1
    assert res.status == LifecycleJobStatus.SUCCESS
