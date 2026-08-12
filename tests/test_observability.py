import os
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import dotenv
dotenv.load_dotenv()

from app.domain import MemoryRecord, MemoryStatus, MemoryType, PolicyDecision
from app.runtime import (
    get_memory_repository,
    get_lifecycle_repository,
    get_lifecycle_runner,
    get_transaction_manager,
)
from app.services.observability import obs
from app.services.lifecycle import WorkerScheduler


async def clean_all():
    db_type = os.environ.get("DATABASE_TYPE", "memory").strip().lower()
    repo = get_memory_repository()
    lifecycle_repo = get_lifecycle_repository()

    if db_type == "postgres":
        from app.repositories.postgres_connection import db_manager
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
        repo._records.clear()
        lifecycle_repo._runs.clear()


@pytest.mark.anyio
async def test_telemetry_emission_and_spans():
    obs.set_test_mode(True)
    obs.set_exporters_available(True)
    
    with obs.span("test_span", trace_id="trace-test-123", tags={"env": "pytest"}) as tid:
        assert tid == "trace-test-123"
        obs.record_metric("test_counter", 42, tags={"metric_tag": "val"})

    events = obs.recorded_events
    assert len(events) == 3  # span_start, metric, span_end
    
    # 1. Verify span_start event
    assert events[0]["event_type"] == "span_start"
    assert events[0]["span_name"] == "test_span"
    assert events[0]["trace_id"] == "trace-test-123"
    assert events[0]["tags"]["env"] == "pytest"

    # 2. Verify metric event
    assert events[1]["event_type"] == "metric"
    assert events[1]["metric_name"] == "test_counter"
    assert events[1]["metric_value"] == 42
    assert events[1]["tags"]["metric_tag"] == "val"

    # 3. Verify span_end event
    assert events[2]["event_type"] == "span_end"
    assert events[2]["span_name"] == "test_span"
    assert events[2]["trace_id"] == "trace-test-123"
    assert "duration_ms" in events[2]


@pytest.mark.anyio
async def test_repository_and_transaction_timing_propagation():
    await clean_all()
    obs.set_test_mode(True)
    obs.set_exporters_available(True)

    repo = get_memory_repository()
    tx_manager = get_transaction_manager()

    rec_id = uuid4()
    rec = MemoryRecord(
        id=rec_id,
        tenant_id="tenant_obs",
        user_id="user_obs",
        content="Testing trace propagation.",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test",
    )

    # Execute under trace context
    test_trace_id = "trace-tx-propagation-999"
    async with tx_manager.transaction():
        # Pass trace_id explicitly as kwarg to check decorator extraction
        await repo.create(rec, trace_id=test_trace_id)

    events = obs.recorded_events
    
    # Check transaction timing
    tx_span = next((e for e in events if e.get("span_name") == "TransactionManager.transaction" and e.get("event_type") == "span_start"), None)
    assert tx_span is not None

    # Check repository create trace propagation
    repo_span = next((e for e in events if "MemoryRepository" in e.get("span_name", "") and e.get("event_type") == "span_start"), None)
    assert repo_span is not None
    assert repo_span["trace_id"] == test_trace_id
    assert repo_span["tags"]["tenant_id"] == "tenant_obs"


@pytest.mark.anyio
async def test_worker_and_scheduler_timing():
    await clean_all()
    obs.set_test_mode(True)
    obs.set_exporters_available(True)

    runner = get_lifecycle_runner()

    # Run retention worker
    await runner.run_job("retention_worker", "tenant_obs", "user_obs")

    events = obs.recorded_events
    
    # Check worker metric emission
    worker_metric = next((e for e in events if e.get("event_type") == "metric" and e.get("metric_name") == "lifecycle_worker_duration"), None)
    assert worker_metric is not None
    assert worker_metric["tags"]["job_name"] == "retention_worker"
    assert worker_metric["tags"]["status"] == "success"

    # Test scheduler trigger metric
    scheduler = WorkerScheduler(runner)
    scheduler.schedule_job("retention_worker", 0.05)
    await scheduler.start("tenant_obs", "user_obs")
    
    # Poll for events with timeout to prevent timing flakiness
    sched_metric = None
    for _ in range(30):
        await asyncio.sleep(0.05)
        events_after_scheduler = obs.recorded_events
        sched_metric = next((e for e in events_after_scheduler if e.get("event_type") == "metric" and e.get("metric_name") == "scheduler_trigger_duration"), None)
        if sched_metric is not None:
            break
            
    await scheduler.stop()
    assert sched_metric is not None
    assert sched_metric["tags"]["job_name"] == "retention_worker"



@pytest.mark.anyio
async def test_database_timing_and_pool_metrics():
    db_type = os.environ.get("DATABASE_TYPE", "memory").strip().lower()
    if db_type != "postgres":
        pytest.skip("Database timing tests require PostgreSQL connection.")

    await clean_all()
    obs.set_test_mode(True)
    obs.set_exporters_available(True)

    repo = get_memory_repository()
    # Trigger a query
    await repo.list_by_status("tenant_obs", "user_obs", MemoryStatus.ACTIVE)

    events = obs.recorded_events
    
    # Verify pool metrics were collected
    pool_total = next((e for e in events if e.get("metric_name") == "connection_pool_total"), None)
    pool_active = next((e for e in events if e.get("metric_name") == "connection_pool_active"), None)
    assert pool_total is not None
    assert pool_active is not None

    # Verify query latency metric was recorded
    query_latency = next((e for e in events if e.get("metric_name") == "db_query_latency"), None)
    assert query_latency is not None
    assert "tags" in query_latency
    assert "query" in query_latency["tags"]
    # E.g. tag query should contain SQL prefix like 'SELECT MEMORIES'
    assert "SELECT" in query_latency["tags"]["query"]


@pytest.mark.anyio
async def test_exporter_unavailable_isolation():
    obs.set_test_mode(True)
    obs.set_exporters_available(False)  # Telemetry exporters offline

    repo = get_memory_repository()
    
    # Call should complete successfully without raising exceptions or logging events
    rec = MemoryRecord(
        id=uuid4(),
        tenant_id="tenant_offline",
        user_id="user_offline",
        content="Telemetry is offline.",
        memory_type=MemoryType.SEMANTIC,
        status=MemoryStatus.ACTIVE,
        initial_policy_decision=PolicyDecision.SAVE,
        initial_policy_reason="test",
    )
    await repo.create(rec)

    # Verify no telemetry events were collected while exporters are offline
    assert len(obs.recorded_events) == 0
    obs.set_exporters_available(True)
