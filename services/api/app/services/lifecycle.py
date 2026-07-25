import asyncio
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Set, Tuple
from uuid import UUID, uuid4

from ..domain.enums import LifecycleJobStatus, MemoryStatus, MemoryType, PolicyDecision, Sensitivity
from ..domain.models import LifecycleRunHistory, MemoryRecord
from ..repositories.base import LifecycleRepository, MemoryRepository
from datetime import timedelta
from .observability import obs

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
        start_time = time.perf_counter()
        try:
            records_processed = await worker.run(tenant_id, user_id, **kwargs)
            run.status = LifecycleJobStatus.SUCCESS
            run.records_processed = records_processed

            duration = (time.perf_counter() - start_time) * 1000.0
            obs.record_metric(
                "lifecycle_worker_duration",
                round(duration, 3),
                tags={"job_name": job_name, "status": "success", "tenant_id": tenant_id}
            )
        except Exception as e:
            logger.exception(f"Error running job '{job_name}': {e}")
            run.status = LifecycleJobStatus.FAILED
            run.error_message = str(e)

            duration = (time.perf_counter() - start_time) * 1000.0
            obs.record_metric(
                "lifecycle_worker_duration",
                round(duration, 3),
                tags={"job_name": job_name, "status": "failed", "tenant_id": tenant_id}
            )
            obs.record_error(
                error_type=type(e).__name__,
                message=str(e),
                location=f"worker:{job_name}",
                trace_id=kwargs.get("trace_id")
            )
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
        start_time = time.perf_counter()
        try:
            trace_id = f"trace-{uuid4()}"
            with obs.span(f"scheduler:{job_name}", trace_id=trace_id, tags={"job_name": job_name, "tenant_id": tenant_id}):
                await self.runner.run_job(job_name, tenant_id, user_id, trace_id=trace_id)
        except ValueError as e:
            if "Concurrency block" not in str(e):
                logger.error(f"Scheduler failed to run job '{job_name}': {e}")
        except Exception as e:
            logger.exception(f"Scheduler failed to execute job '{job_name}': {e}")
        finally:
            duration = (time.perf_counter() - start_time) * 1000.0
            obs.record_metric(
                "scheduler_trigger_duration",
                round(duration, 3),
                tags={"job_name": job_name, "tenant_id": tenant_id}
            )


def enforce_legal_hold(record: MemoryRecord) -> None:
    """
    Enforces the legal hold gate. If active, raises ValueError.
    """
    if record.legal_hold:
        raise ValueError("Operation blocked: Memory record is under active legal hold.")


class RetentionWorker(LifecycleWorker):
    """
    Scans active memories and logically deletes those that have expired.
    """

    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository

    @property
    def name(self) -> str:
        return "retention_worker"

    async def run(self, tenant_id: str, user_id: str, **kwargs) -> int:
        now = kwargs.get("now") or datetime.now(timezone.utc)
        
        active_memories = await self.repository.list_by_status(
            tenant_id, user_id, MemoryStatus.ACTIVE
        )
        
        processed_count = 0
        for record in active_memories:
            if record.expires_at is not None and record.expires_at < now:
                if record.legal_hold:
                    logger.warning(f"Skipping expired memory {record.id} due to active legal hold.")
                    continue
                
                await self.repository.delete(record.id, tenant_id, user_id)
                processed_count += 1
                
        return processed_count


class DecayWorker(LifecycleWorker):
    """
    Decays importance of active memories over time, archiving those that drop to 0 importance.
    """

    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository

    @property
    def name(self) -> str:
        return "decay_worker"

    async def run(self, tenant_id: str, user_id: str, **kwargs) -> int:
        now = kwargs.get("now") or datetime.now(timezone.utc)
        
        decay_days = kwargs.get("decay_days", 30)
        decay_seconds = kwargs.get("decay_seconds")
        
        threshold = timedelta(seconds=decay_seconds) if decay_seconds is not None else timedelta(days=decay_days)
        
        active_memories = await self.repository.list_by_status(
            tenant_id, user_id, MemoryStatus.ACTIVE
        )
        
        processed_count = 0
        for record in active_memories:
            if now - record.updated_at >= threshold:
                if record.legal_hold:
                    continue
                
                new_importance = max(0, record.importance - 1)
                
                updated_record = record.model_copy(deep=True)
                updated_record.importance = new_importance
                
                if new_importance == 0:
                    updated_record.status = MemoryStatus.ARCHIVED
                    updated_record.archived_at = now
                
                await self.repository.update(updated_record)
                processed_count += 1
                
        return processed_count


class ReflectionWorker(LifecycleWorker):
    """
    Scans active memories to detect high lexical Jaccard overlap, generating PENDING merge proposals.
    """

    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository

    @property
    def name(self) -> str:
        return "reflection_worker"

    def _normalize_tokens(self, text: str) -> set:
        import unicodedata
        import re
        if not text:
            return set()
        normalized = unicodedata.normalize("NFKC", text).lower()
        cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", normalized)
        return {token for token in cleaned.split() if token}

    def _calculate_jaccard(self, text1: str, text2: str) -> float:
        tokens1 = self._normalize_tokens(text1)
        tokens2 = self._normalize_tokens(text2)
        if not tokens1 or not tokens2:
            return 0.0
        intersection = tokens1.intersection(tokens2)
        union = tokens1.union(tokens2)
        return len(intersection) / len(union)

    async def run(self, tenant_id: str, user_id: str, **kwargs) -> int:
        threshold = kwargs.get("jaccard_threshold", 0.5)
        
        active_memories = await self.repository.list_by_status(
            tenant_id, user_id, MemoryStatus.ACTIVE
        )
        
        pending_memories = await self.repository.list_by_status(
            tenant_id, user_id, MemoryStatus.PENDING
        )
        existing_proposal_keys = set()
        for rec in pending_memories:
            if rec.source_conversation_id == "reflection_proposal" and rec.source_excerpt:
                if rec.source_excerpt.startswith("source_ids:"):
                    source_ids_str = rec.source_excerpt.replace("source_ids:", "").split(",")
                    source_ids = sorted(source_ids_str)
                    existing_proposal_keys.add(tuple(source_ids))

        processed_count = 0
        n = len(active_memories)
        
        for i in range(n):
            for j in range(i + 1, n):
                rec1 = active_memories[i]
                rec2 = active_memories[j]
                
                sim = self._calculate_jaccard(rec1.content, rec2.content)
                if sim >= threshold:
                    source_ids = sorted([str(rec1.id), str(rec2.id)])
                    key = tuple(source_ids)
                    
                    if key in existing_proposal_keys:
                        continue
                        
                    proposal = MemoryRecord(
                        id=uuid4(),
                        tenant_id=tenant_id,
                        user_id=user_id,
                        content=f"Proposed Merge: {rec1.content} AND {rec2.content}",
                        memory_type=rec1.memory_type,
                        status=MemoryStatus.PENDING,
                        sensitivity=max(rec1.sensitivity, rec2.sensitivity, key=lambda s: ["low", "medium", "high"].index(s.value)),
                        importance=max(rec1.importance, rec2.importance),
                        confidence=min(rec1.confidence, rec2.confidence),
                        initial_policy_decision=PolicyDecision.PENDING_APPROVAL,
                        initial_policy_reason="Generated by reflection loop Jaccard-overlap detection.",
                        source_kind="chat",
                        source_conversation_id="reflection_proposal",
                        source_excerpt=f"source_ids:{rec1.id},{rec2.id}",
                    )
                    
                    await self.repository.create(proposal)
                    existing_proposal_keys.add(key)
                    processed_count += 1
                    
        return processed_count


class CompactionWorker(LifecycleWorker):
    """
    Wipes content and embedding vectors of logically deleted memories, preserving metadata.
    """

    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository

    @property
    def name(self) -> str:
        return "compaction_worker"

    async def run(self, tenant_id: str, user_id: str, **kwargs) -> int:
        deleted_memories = await self.repository.list_by_status(
            tenant_id, user_id, MemoryStatus.DELETED
        )
        
        processed_count = 0
        for record in deleted_memories:
            if record.content == "[COMPACTED]" and record.embedding is None:
                continue
                
            if record.legal_hold:
                logger.warning(f"Skipping compaction for deleted memory {record.id} due to active legal hold.")
                continue
                
            compacted_record = record.model_copy(deep=True)
            compacted_record.content = "[COMPACTED]"
            compacted_record.embedding = None
            
            await self.repository.update(compacted_record)
            processed_count += 1
            
        return processed_count
