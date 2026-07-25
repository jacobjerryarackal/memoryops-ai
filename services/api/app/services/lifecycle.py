import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Set, Tuple
from uuid import UUID, uuid4

from ..domain.enums import LifecycleJobStatus
from ..domain.models import LifecycleRunHistory, MemoryRecord
from ..repositories.base import LifecycleRepository

logger = logging.getLogger("app.services.lifecycle")


class LifecycleWorker(ABC):
    """
    Abstract base class for all background lifecycle workers (jobs).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        The unique name identifier of the worker job.
        """
        pass

    @abstractmethod
    async def run(self, tenant_id: str, user_id: str, **kwargs) -> int:
        """
        Executes the worker's operational logic.

        Args:
            tenant_id: Scope tenant identifier.
            user_id: Scope user identifier.
            **kwargs: Additional runtime arguments.

        Returns:
            int: The number of memory records processed.
        """
        pass


class LifecycleRunner:
    """
    Coordinates background job execution, registration, concurrency safety,
    and records execution history.
    """

    def __init__(self, lifecycle_repo: LifecycleRepository) -> None:
        self.lifecycle_repo = lifecycle_repo
        self._workers: Dict[str, LifecycleWorker] = {}
        self._running_keys: Set[Tuple[str, str, str]] = set()
        self._lock = asyncio.Lock()

    def register_worker(self, worker: LifecycleWorker) -> None:
        """
        Registers a worker with the runner.
        """
        if worker.name in self._workers:
            raise ValueError(f"Worker with name '{worker.name}' is already registered.")
        self._workers[worker.name] = worker
        logger.info(f"Registered lifecycle worker: {worker.name}")

    async def run_job(
        self, job_name: str, tenant_id: str, user_id: str, **kwargs
    ) -> LifecycleRunHistory:
        """
        Executes a registered job under concurrent execution protection.
        """
        # 1. Fetch worker
        worker = self._workers.get(job_name)
        if worker is None:
            raise ValueError(f"No registered worker found for job name '{job_name}'.")

        # 2. Concurrency checks
        async with self._lock:
            key = (job_name, tenant_id, user_id)
            if key in self._running_keys:
                raise ValueError(
                    f"Concurrency block: Job '{job_name}' is already running for tenant '{tenant_id}' and user '{user_id}'."
                )

            # Check database for active runs (for multi-process / multi-worker setups)
            db_running = await self.lifecycle_repo.is_job_running(job_name, tenant_id, user_id)
            if db_running:
                raise ValueError(
                    f"Concurrency block: Database records indicate job '{job_name}' is already running for tenant '{tenant_id}' and user '{user_id}'."
                )

            # Mark as running locally
            self._running_keys.add(key)

        # 3. Create run history entry
        run = LifecycleRunHistory(
            id=uuid4(),
            job_name=job_name,
            status=LifecycleJobStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
            metadata={"tenant_id": tenant_id, "user_id": user_id, **kwargs},
        )
        await self.lifecycle_repo.create_run(run)

        # 4. Execute worker
        try:
            records_processed = await worker.run(tenant_id, user_id, **kwargs)
            run.status = LifecycleJobStatus.SUCCESS
            run.records_processed = records_processed
        except Exception as e:
            logger.exception(f"Error running job '{job_name}': {e}")
            run.status = LifecycleJobStatus.FAILED
            run.error_message = str(e)
        finally:
            run.completed_at = datetime.now(timezone.utc)
            async with self._lock:
                self._running_keys.discard(key)

        # 5. Update run history entry
        await self.lifecycle_repo.update_run(run)
        return run


class WorkerScheduler:
    """
    Schedules registered jobs to execute periodically in an execution loop.
    """

    def __init__(self, runner: LifecycleRunner) -> None:
        self.runner = runner
        self._schedules: Dict[str, float] = {}  # job_name -> interval_seconds
        self._task: Optional[asyncio.Task] = None
        self._running: bool = False

    def schedule_job(self, job_name: str, interval_seconds: float) -> None:
        """
        Schedules a job to run periodically at the specified interval.
        """
        if interval_seconds <= 0:
            raise ValueError("Interval must be a positive number of seconds.")
        self._schedules[job_name] = interval_seconds

    async def start(self, tenant_id: str, user_id: str) -> None:
        """
        Starts the background scheduling execution loop.
        """
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._execution_loop(tenant_id, user_id))
        logger.info("Worker scheduler started.")

    async def stop(self) -> None:
        """
        Stops the background scheduling execution loop.
        """
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Worker scheduler stopped.")

    async def _execution_loop(self, tenant_id: str, user_id: str) -> None:
        # job_name -> timestamp of last execution
        last_run: Dict[str, float] = {}

        while self._running:
            now = asyncio.get_event_loop().time()
            for job_name, interval in list(self._schedules.items()):
                if job_name not in last_run or now - last_run[job_name] >= interval:
                    last_run[job_name] = now
                    # Launch job in background task to not block the scheduling loop
                    asyncio.create_task(
                        self._trigger_job(job_name, tenant_id, user_id)
                    )
            await asyncio.sleep(0.1)

    async def _trigger_job(self, job_name: str, tenant_id: str, user_id: str) -> None:
        try:
            await self.runner.run_job(job_name, tenant_id, user_id)
        except ValueError as e:
            # Silence concurrency errors in scheduler log to keep it clean
            if "Concurrency block" not in str(e):
                logger.error(f"Scheduler failed to run job '{job_name}': {e}")
        except Exception as e:
            logger.exception(f"Scheduler failed to execute job '{job_name}': {e}")


def enforce_legal_hold(record: MemoryRecord) -> None:
    """
    Enforces the legal hold gate. If active, raises ValueError.
    """
    if record.legal_hold:
        raise ValueError("Operation blocked: Memory record is under active legal hold.")
