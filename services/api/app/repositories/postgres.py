import os
import math
import json
import logging
import asyncio
import threading
from datetime import datetime, timezone
from uuid import UUID
from typing import List, Optional, Tuple, Dict, Any, AsyncIterator
from contextlib import asynccontextmanager
import asyncpg

from ..domain.models import MemoryRecord, AuditEvent, LifecycleRunHistory
from ..domain.enums import MemoryStatus, MemoryType, Sensitivity, PolicyDecision, AuditEventAction, LifecycleJobStatus
from .base import MemoryRepository, LifecycleRepository
from ..services.audit import AuditService
from .postgres_connection import db_manager
from .transactions import db_tx_conn

logger = logging.getLogger("app.repositories.postgres")


def run_async_synchronously(coro):
    """Helper to run a coroutine synchronously, even if the event loop is already running."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        result = []
        exception = []
        def target():
            try:
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                res = new_loop.run_until_complete(coro)
                result.append(res)
            except Exception as e:
                exception.append(e)
            finally:
                new_loop.close()
        t = threading.Thread(target=target)
        t.start()
        t.join()
        if exception:
            raise exception[0]
        return result[0]
    else:
        return loop.run_until_complete(coro)


async def run_in_temp_conn(coro_func) -> Any:
    """Helper to open a separate, temporary connection to prevent event-loop conflicts in secondary threads."""
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "postgres")
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "postgres")

    conn = await asyncpg.connect(
        host=host,
        port=int(port),
        database=db,
        user=user,
        password=password,
    )
    try:
        from pgvector.asyncpg import register_vector
        try:
            await register_vector(conn)
        except Exception:
            pass
        async with conn.transaction():
            await conn.execute("SET LOCAL app.bypass_rls = 'true';")
            return await coro_func(conn)
    finally:
        await conn.close()



from ..services.observability import obs, trace_method, trace_class
import time


class ObsConnectionProxy:
    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._conn, name)
        if callable(attr) and name in ("execute", "fetch", "fetchrow", "fetchval"):
            async def wrapped(*args, **kwargs):
                query = args[0] if args else "UNKNOWN"
                sql_prefix = " ".join(query.strip().split()[:3]).upper()
                start = time.perf_counter()
                try:
                    return await attr(*args, **kwargs)
                except Exception as e:
                    obs.record_error(
                        error_type=type(e).__name__,
                        message=str(e),
                        location=f"db_query:{sql_prefix}"
                    )
                    raise
                finally:
                    duration = (time.perf_counter() - start) * 1000.0
                    obs.record_metric("db_query_latency", round(duration, 3), tags={"query": sql_prefix})
            return wrapped
        return attr


async def ensure_active_pool() -> None:
    """Helper to ensure the database manager has an active pool in the current event loop."""
    if db_manager.pool is not None:
        if db_manager.pool._loop.is_closed():
            db_manager.pool = None
    if db_manager.pool is None:
        await db_manager.initialize()


@asynccontextmanager
async def get_connection() -> AsyncIterator[asyncpg.Connection]:
    """
    Yields the active transaction-bound connection if present in the context.
    Otherwise, temporarily acquires one from the pool.
    """
    conn = db_tx_conn.get()
    if conn is not None:
        yield ObsConnectionProxy(conn)
    else:
        await ensure_active_pool()
        pool = db_manager.pool
        if pool is not None:
            try:
                total = pool.get_size()
                idle = pool.get_idle_size()
                obs.record_metric("connection_pool_total", total)
                obs.record_metric("connection_pool_active", total - idle)
                obs.record_metric("connection_pool_idle", idle)
            except Exception:
                pass
        async with db_manager.pool.acquire() as conn_acquired:
            yield ObsConnectionProxy(conn_acquired)


from contextvars import ContextVar
from contextlib import asynccontextmanager

db_bypass_rls: ContextVar[bool] = ContextVar("db_bypass_rls", default=False)


@asynccontextmanager
async def rls_bypass() -> AsyncIterator[None]:
    token = db_bypass_rls.set(True)
    try:
        yield
    finally:
        db_bypass_rls.reset(token)


@asynccontextmanager
async def scoped_connection(tenant_id: str, user_id: Optional[str]) -> AsyncIterator[asyncpg.Connection]:
    async with get_connection() as conn:
        if db_bypass_rls.get():
            in_tx = db_tx_conn.get() is not None
            if in_tx:
                await conn.execute("SELECT set_config('app.bypass_rls', 'true', true)")
                yield conn
            else:
                async with conn.transaction():
                    await conn.execute("SELECT set_config('app.bypass_rls', 'true', true)")
                    yield conn
            return


        in_tx = db_tx_conn.get() is not None
        if in_tx:
            await conn.execute("SELECT set_config('app.current_tenant_id', $1, true)", tenant_id)
            if user_id:
                await conn.execute("SELECT set_config('app.current_user_id', $1, true)", user_id)
            else:
                await conn.execute("SELECT set_config('app.current_user_id', '', true)")
            yield conn
        else:
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.current_tenant_id', $1, true)", tenant_id)
                if user_id:
                    await conn.execute("SELECT set_config('app.current_user_id', $1, true)", user_id)
                else:
                    await conn.execute("SELECT set_config('app.current_user_id', '', true)")
                yield conn




class PostgresDictProxy(dict):
    """Dict proxy to intercept direct dictionary updates in test fixtures and sync them to PostgreSQL."""
    def __init__(self, table_name: str):
        self.table_name = table_name
        super().__init__()

    def clear(self) -> None:
        super().clear()
        async def do_clear(conn):
            await conn.execute(f"TRUNCATE TABLE {self.table_name} CASCADE;")
        run_async_synchronously(run_in_temp_conn(do_clear))

    def __setitem__(self, key: Any, value: Any) -> None:
        super().__setitem__(key, value)
        async def do_set(conn):
            if self.table_name == "memories":


                exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM memories WHERE id = $1)", key)
                if exists:
                    await conn.execute(
                        """
                        UPDATE memories SET
                            tenant_id = $2, user_id = $3, content = $4, memory_type = $5,
                            status = $6, sensitivity = $7, importance = $8, confidence = $9,
                            reinforcement_count = $10, embedding = $11, source_kind = $12,
                            source_conversation_id = $13, source_excerpt = $14,
                            initial_policy_decision = $15, initial_policy_reason = $16,
                            created_at = $17, updated_at = $18, archived_at = $19, deleted_at = $20,
                            identity_slot = $21, legal_hold = $22, expires_at = $23
                        WHERE id = $1
                        """,
                        value.id, value.tenant_id, value.user_id, value.content, value.memory_type.value,
                        value.status.value, value.sensitivity.value, value.importance, value.confidence,
                        value.reinforcement_count, value.embedding, value.source_kind, value.source_conversation_id,
                        value.source_excerpt, value.initial_policy_decision.value, value.initial_policy_reason,
                        value.created_at, value.updated_at, value.archived_at, value.deleted_at, value.identity_slot,
                        value.legal_hold, value.expires_at
                    )
                else:
                    await conn.execute(
                        """
                        INSERT INTO memories (
                            id, tenant_id, user_id, content, memory_type, status, sensitivity,
                            importance, confidence, reinforcement_count, embedding, source_kind,
                            source_conversation_id, source_excerpt, initial_policy_decision,
                            initial_policy_reason, created_at, updated_at, archived_at, deleted_at,
                            identity_slot, legal_hold, expires_at
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23
                        )
                        """,
                        value.id, value.tenant_id, value.user_id, value.content, value.memory_type.value,
                        value.status.value, value.sensitivity.value, value.importance, value.confidence,
                        value.reinforcement_count, value.embedding, value.source_kind, value.source_conversation_id,
                        value.source_excerpt, value.initial_policy_decision.value, value.initial_policy_reason,
                        value.created_at, value.updated_at, value.archived_at, value.deleted_at, value.identity_slot,
                        value.legal_hold, value.expires_at
                    )
            elif self.table_name == "memory_audit_logs":
                # Satisfy foreign key constraint on memory_id if present
                if value.memory_id is not None:
                    mem_exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM memories WHERE id = $1)", value.memory_id)
                    if not mem_exists:
                        await conn.execute(
                            """
                            INSERT INTO memories (
                                id, tenant_id, user_id, content, memory_type, status, sensitivity,
                                importance, confidence, reinforcement_count, embedding, source_kind,
                                source_conversation_id, source_excerpt, initial_policy_decision,
                                initial_policy_reason, created_at, updated_at, archived_at, deleted_at,
                                identity_slot, legal_hold, expires_at
                            ) VALUES (
                                $1, $2, $3, 'dummy', 'semantic', 'active', 'low', 5, 0.0, 0, NULL, 'chat', NULL, NULL, 'SAVE', 'dummy', NOW(), NOW(), NULL, NULL, NULL, FALSE, NULL
                            )
                            """,
                            value.memory_id, value.tenant_id, "dummy"
                        )

                exists = await conn.fetchval("SELECT EXISTS(SELECT 1 FROM memory_audit_logs WHERE id = $1)", key)
                if not exists:
                    await conn.execute(
                        """
                        INSERT INTO memory_audit_logs (
                            id, tenant_id, user_id, memory_id, action, reason, metadata, trace_id, created_at
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9
                        )
                        """,
                        value.id, value.tenant_id, value.user_id, value.memory_id, value.action.value,
                        value.reason, json.dumps(value.metadata), value.trace_id, value.created_at
                    )
        run_async_synchronously(run_in_temp_conn(do_set))


def row_to_memory_record(row: asyncpg.Record) -> MemoryRecord:
    embedding_val = row["embedding"]
    if embedding_val is not None:
        if hasattr(embedding_val, "to_list"):
            embedding_val = embedding_val.to_list()
        elif hasattr(embedding_val, "tolist"):
            embedding_val = embedding_val.tolist()
        else:
            embedding_val = list(embedding_val)

    return MemoryRecord(
        id=row["id"],
        tenant_id=row["tenant_id"],
        user_id=row["user_id"],
        content=row["content"],
        memory_type=MemoryType(row["memory_type"]),
        status=MemoryStatus(row["status"]),
        sensitivity=Sensitivity(row["sensitivity"]),
        importance=row["importance"],
        confidence=row["confidence"],
        reinforcement_count=row["reinforcement_count"],
        embedding=embedding_val,
        source_kind=row["source_kind"],
        source_conversation_id=row["source_conversation_id"],
        source_excerpt=row["source_excerpt"],
        initial_policy_decision=PolicyDecision(row["initial_policy_decision"]),
        initial_policy_reason=row["initial_policy_reason"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        archived_at=row["archived_at"],
        deleted_at=row["deleted_at"],
        identity_slot=row["identity_slot"],
        legal_hold=row["legal_hold"],
        expires_at=row["expires_at"],
        version=row["version"],
    )



def row_to_audit_event(row: asyncpg.Record) -> AuditEvent:
    metadata_val = row["metadata"]
    if metadata_val is None:
        metadata_val = {}
    elif isinstance(metadata_val, str):
        metadata_val = json.loads(metadata_val)

    return AuditEvent(
        id=row["id"],
        tenant_id=row["tenant_id"],
        user_id=row["user_id"],
        memory_id=row["memory_id"],
        action=AuditEventAction(row["action"]),
        reason=row["reason"],
        metadata=metadata_val,
        trace_id=row["trace_id"],
        created_at=row["created_at"],
    )


@trace_class("repository")
class PostgreSQLMemoryRepository(MemoryRepository):
    def __init__(self) -> None:
        self._records = PostgresDictProxy("memories")

    async def create(self, record: MemoryRecord) -> MemoryRecord:
        try:
            async with scoped_connection(record.tenant_id, record.user_id) as conn:
                await conn.execute(
                    """
                    INSERT INTO memories (
                        id, tenant_id, user_id, content, memory_type, status, sensitivity,
                        importance, confidence, reinforcement_count, embedding, source_kind,
                        source_conversation_id, source_excerpt, initial_policy_decision,
                        initial_policy_reason, created_at, updated_at, archived_at, deleted_at,
                        identity_slot, legal_hold, expires_at, version
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24
                    )
                    """,
                    record.id,
                    record.tenant_id,
                    record.user_id,
                    record.content,
                    record.memory_type.value,
                    record.status.value,
                    record.sensitivity.value,
                    record.importance,
                    record.confidence,
                    record.reinforcement_count,
                    record.embedding,
                    record.source_kind,
                    record.source_conversation_id,
                    record.source_excerpt,
                    record.initial_policy_decision.value,
                    record.initial_policy_reason,
                    record.created_at,
                    record.updated_at,
                    record.archived_at,
                    record.deleted_at,
                    record.identity_slot,
                    record.legal_hold,
                    record.expires_at,
                    record.version,
                )
        except asyncpg.exceptions.UniqueViolationError:
            raise ValueError(f"Duplicate key: Memory record with ID {record.id} already exists.")


        return record.model_copy(deep=True)

    async def get_by_id(
        self, memory_id: UUID, tenant_id: str, user_id: str
    ) -> Optional[MemoryRecord]:
        async with scoped_connection(tenant_id, user_id) as conn:
            row = await conn.fetchrow(
                "SELECT * FROM memories WHERE id = $1 AND tenant_id = $2 AND user_id = $3",
                memory_id,
                tenant_id,
                user_id,
            )
            if row is None:
                return None
            return row_to_memory_record(row)

    async def update(self, record: MemoryRecord) -> MemoryRecord:
        # Check if record exists at all using RLS bypass to read actual metadata for immutable coordinate checks
        async with rls_bypass():
            async with scoped_connection("", "") as conn:
                persisted_row = await conn.fetchrow("SELECT * FROM memories WHERE id = $1", record.id)

                
        if persisted_row is None:
            raise ValueError(f"Missing target: Memory record with ID {record.id} does not exist.")

        persisted = row_to_memory_record(persisted_row)

        # 1. Verify immutable scope isolation
        if persisted.tenant_id != record.tenant_id or persisted.user_id != record.user_id:
            raise ValueError("Scope mismatch: tenant_id and user_id are immutable and cannot be altered.")

        # 2. Verify immutable admission provenance
        if persisted.initial_policy_decision != record.initial_policy_decision or persisted.initial_policy_reason != record.initial_policy_reason:
            raise ValueError("Immutable admission provenance: initial_policy_decision and initial_policy_reason cannot be altered.")

        # 3. Verify immutable coordinates
        if persisted.memory_type != record.memory_type:
            raise ValueError("Core coordinate mismatch: memory_type is immutable and cannot be altered.")
        if persisted.identity_slot != record.identity_slot:
            raise ValueError("Core coordinate mismatch: identity_slot is immutable and cannot be altered.")

        # 4. Verify terminal logical deletion
        if persisted.status == MemoryStatus.DELETED:
            is_compaction = (
                record.status == MemoryStatus.DELETED
                and record.content == "[COMPACTED]"
                and record.embedding is None
            )
            if not is_compaction:
                raise ValueError("Terminal deletion: cannot update a logically deleted memory record.")

        # 5. Enforce segregation of deletion
        if record.status == MemoryStatus.DELETED and persisted.status != MemoryStatus.DELETED:
            raise ValueError("Segregation of deletion: logical deletion must occur via the delete() method.")

        # Verify version matching for OCC
        if persisted.version != record.version:
            raise ValueError("Concurrency conflict: Memory record version mismatch.")

        new_updated_at = datetime.now(timezone.utc)

        async with scoped_connection(record.tenant_id, record.user_id) as conn:
            res = await conn.execute(
                """
                UPDATE memories SET
                    content = $4,
                    status = $5,
                    sensitivity = $6,
                    importance = $7,
                    confidence = $8,
                    reinforcement_count = $9,
                    embedding = $10,
                    source_kind = $11,
                    source_conversation_id = $12,
                    source_excerpt = $13,
                    updated_at = $14,
                    archived_at = $15,
                    deleted_at = $16,
                    legal_hold = $17,
                    expires_at = $18,
                    version = version + 1
                WHERE id = $1 AND tenant_id = $2 AND user_id = $3 AND version = $19
                """,
                record.id,
                record.tenant_id,
                record.user_id,
                record.content,
                record.status.value,
                record.sensitivity.value,
                record.importance,
                record.confidence,
                record.reinforcement_count,
                record.embedding,
                record.source_kind,
                record.source_conversation_id,
                record.source_excerpt,
                new_updated_at,
                record.archived_at,
                record.deleted_at,
                record.legal_hold,
                record.expires_at,
                record.version,
            )
            if "UPDATE 0" in res:
                raise ValueError("Concurrency conflict: Memory record version mismatch.")

        # Return updated record
        copied = record.model_copy(deep=True)
        copied.version = record.version + 1
        copied.updated_at = new_updated_at
        return copied

    async def delete(
        self, memory_id: UUID, tenant_id: str, user_id: str
    ) -> MemoryRecord:
        async with rls_bypass():
            async with scoped_connection("", "") as conn:
                persisted_row = await conn.fetchrow("SELECT * FROM memories WHERE id = $1", memory_id)

                
        if persisted_row is None:
            raise ValueError(f"Missing target: Memory record with ID {memory_id} does not exist.")

        persisted = row_to_memory_record(persisted_row)

        # Verify scope
        if persisted.tenant_id != tenant_id or persisted.user_id != user_id:
            raise ValueError("Scope mismatch: unauthorized deletion attempt.")

        # Enforce legal hold gating (fail-closed)
        if persisted.legal_hold:
            raise ValueError("Operation blocked: Memory record is under active legal hold.")

        if persisted.status == MemoryStatus.DELETED:
            return persisted

        now = datetime.now(timezone.utc)
        async with scoped_connection(tenant_id, user_id) as conn:
            await conn.execute(
                """
                UPDATE memories SET
                    status = 'deleted',
                    deleted_at = $4,
                    updated_at = $5
                WHERE id = $1 AND tenant_id = $2 AND user_id = $3
                """,
                memory_id,
                tenant_id,
                user_id,
                now,
                now,
            )

        persisted.status = MemoryStatus.DELETED
        persisted.deleted_at = now
        persisted.updated_at = now
        return persisted

    async def list_by_status(
        self, tenant_id: str, user_id: str, status: MemoryStatus
    ) -> List[MemoryRecord]:
        async with scoped_connection(tenant_id, user_id) as conn:
            rows = await conn.fetch(
                "SELECT * FROM memories WHERE tenant_id = $1 AND user_id = $2 AND status = $3 ORDER BY created_at DESC, id ASC",
                tenant_id,
                user_id,
                status.value,
            )
            return [row_to_memory_record(r) for r in rows]

    async def list_active(
        self, tenant_id: str, user_id: str, limit: int = 100
    ) -> List[MemoryRecord]:
        if limit <= 0:
            raise ValueError("Limit must be a positive integer greater than zero.")

        async with scoped_connection(tenant_id, user_id) as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM memories
                WHERE tenant_id = $1 AND user_id = $2 AND status = 'active'
                ORDER BY created_at DESC, id ASC
                LIMIT $3
                """,
                tenant_id,
                user_id,
                limit,
            )
            return [row_to_memory_record(r) for r in rows]

    async def get_active_by_slot(
        self,
        tenant_id: str,
        user_id: str,
        memory_type: MemoryType,
        identity_slot: str,
    ) -> List[MemoryRecord]:
        async with scoped_connection(tenant_id, user_id) as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM memories
                WHERE tenant_id = $1 AND user_id = $2 AND memory_type = $3 AND identity_slot = $4 AND status = 'active'
                ORDER BY created_at DESC, id ASC
                LIMIT 2
                """,
                tenant_id,
                user_id,
                memory_type.value,
                identity_slot,
            )
            return [row_to_memory_record(r) for r in rows]

    async def search_candidates(
        self,
        tenant_id: str,
        user_id: str,
        query_embedding: Optional[List[float]],
        limit: int = 50,
    ) -> List[Tuple[MemoryRecord, Optional[float]]]:
        if limit < 1:
            raise ValueError("limit must be >= 1")

        if query_embedding is not None and len(query_embedding) != 1536:
            raise ValueError("query_embedding must be exactly 1536 dimensions")

        async with scoped_connection(tenant_id, user_id) as conn:
            if query_embedding is None:
                rows = await conn.fetch(
                    """
                    SELECT * FROM memories
                    WHERE tenant_id = $1 AND user_id = $2 AND status = 'active'
                    ORDER BY created_at DESC, id ASC
                    LIMIT $3
                    """,
                    tenant_id,
                    user_id,
                    limit,
                )
                return [(row_to_memory_record(r), None) for r in rows]
            else:
                rows = await conn.fetch(
                    """
                    SELECT *, (1 - (embedding <=> $3)) as similarity FROM memories
                    WHERE tenant_id = $1 AND user_id = $2 AND status = 'active' AND embedding IS NOT NULL
                    ORDER BY (1 - (embedding <=> $3)) DESC, created_at DESC, id ASC
                    LIMIT $4
                    """,
                    tenant_id,
                    user_id,
                    query_embedding,
                    limit,
                )
                return [(row_to_memory_record(r), float(r["similarity"])) for r in rows]



class PostgreSQLAuditRepository(AuditService):
    def __init__(self) -> None:
        self._events = PostgresDictProxy("memory_audit_logs")

    async def record(self, event: AuditEvent) -> AuditEvent:
        try:
            async with scoped_connection(event.tenant_id, event.user_id) as conn:
                await conn.execute(
                    """
                    INSERT INTO memory_audit_logs (
                        id, tenant_id, user_id, memory_id, action, reason, metadata, trace_id, created_at
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9
                    )
                    """,
                    event.id,
                    event.tenant_id,
                    event.user_id,
                    event.memory_id,
                    event.action.value,
                    event.reason,
                    json.dumps(event.metadata),
                    event.trace_id,
                    event.created_at,
                )
        except asyncpg.exceptions.UniqueViolationError:
            raise ValueError(f"Duplicate audit event ID: {event.id} already exists.")

        return event.model_copy(deep=True)

    async def list_events(
        self,
        tenant_id: str,
        user_id: Optional[str] = None,
        memory_id: Optional[UUID] = None,
        limit: Optional[int] = None,
    ) -> List[AuditEvent]:
        if limit is not None and limit <= 0:
            raise ValueError("Limit must be a positive integer greater than zero.")

        query = "SELECT * FROM memory_audit_logs WHERE tenant_id = $1"
        params = [tenant_id]
        idx = 2

        if user_id is not None:
            query += f" AND user_id = ${idx}"
            params.append(user_id)
            idx += 1

        if memory_id is not None:
            query += f" AND memory_id = ${idx}"
            params.append(memory_id)
            idx += 1

        query += " ORDER BY created_at DESC, id ASC"

        if limit is not None:
            query += f" LIMIT ${idx}"
            params.append(limit)

        async with scoped_connection(tenant_id, user_id) as conn:
            rows = await conn.fetch(query, *params)
            return [row_to_audit_event(r) for r in rows]



class DateTimeEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)


@trace_class("repository")
class PostgreSQLLifecycleRepository(LifecycleRepository):

    async def create_run(self, run: LifecycleRunHistory) -> LifecycleRunHistory:
        try:
            async with get_connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO lifecycle_run_history (
                        id, job_name, status, started_at, completed_at, error_message, records_processed, metadata
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8
                    )
                    """,
                    run.id,
                    run.job_name,
                    run.status.value,
                    run.started_at,
                    run.completed_at,
                    run.error_message,
                    run.records_processed,
                    json.dumps(run.metadata, cls=DateTimeEncoder),
                )
        except asyncpg.exceptions.UniqueViolationError:
            raise ValueError(f"Duplicate key: Run with ID {run.id} already exists.")
        return run.model_copy(deep=True)

    async def update_run(self, run: LifecycleRunHistory) -> LifecycleRunHistory:
        async with get_connection() as conn:
            exists = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM lifecycle_run_history WHERE id = $1)",
                run.id
            )
            if not exists:
                raise ValueError(f"Missing target: Run with ID {run.id} does not exist.")

            await conn.execute(
                """
                UPDATE lifecycle_run_history SET
                    status = $2,
                    completed_at = $3,
                    error_message = $4,
                    records_processed = $5,
                    metadata = $6
                WHERE id = $1
                """,
                run.id,
                run.status.value,
                run.completed_at,
                run.error_message,
                run.records_processed,
                json.dumps(run.metadata, cls=DateTimeEncoder),
            )
        return run.model_copy(deep=True)

    async def get_run_by_id(self, run_id: UUID) -> Optional[LifecycleRunHistory]:
        async with get_connection() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM lifecycle_run_history WHERE id = $1",
                run_id
            )
            if row is None:
                return None
            
            metadata_val = row["metadata"]
            if metadata_val is None:
                metadata_val = {}
            elif isinstance(metadata_val, str):
                metadata_val = json.loads(metadata_val)

            return LifecycleRunHistory(
                id=row["id"],
                job_name=row["job_name"],
                status=LifecycleJobStatus(row["status"]),
                started_at=row["started_at"],
                completed_at=row["completed_at"],
                error_message=row["error_message"],
                records_processed=row["records_processed"],
                metadata=metadata_val,
            )

    async def list_runs(
        self, job_name: Optional[str] = None, limit: int = 100
    ) -> List[LifecycleRunHistory]:
        query = "SELECT * FROM lifecycle_run_history"
        params = []
        if job_name is not None:
            query += " WHERE job_name = $1"
            params.append(job_name)
        
        query += " ORDER BY started_at DESC, id ASC"
        
        if job_name is not None:
            query += f" LIMIT $2"
            params.append(limit)
        else:
            query += f" LIMIT $1"
            params.append(limit)

        async with get_connection() as conn:
            rows = await conn.fetch(query, *params)
            
            runs = []
            for row in rows:
                metadata_val = row["metadata"]
                if metadata_val is None:
                    metadata_val = {}
                elif isinstance(metadata_val, str):
                    metadata_val = json.loads(metadata_val)

                runs.append(
                    LifecycleRunHistory(
                        id=row["id"],
                        job_name=row["job_name"],
                        status=LifecycleJobStatus(row["status"]),
                        started_at=row["started_at"],
                        completed_at=row["completed_at"],
                        error_message=row["error_message"],
                        records_processed=row["records_processed"],
                        metadata=metadata_val,
                    )
                )
            return runs

    async def is_job_running(self, job_name: str, tenant_id: str, user_id: str) -> bool:
        async with get_connection() as conn:
            return await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM lifecycle_run_history 
                    WHERE job_name = $1 
                      AND status = 'running' 
                      AND metadata->>'tenant_id' = $2 
                      AND metadata->>'user_id' = $3
                )
                """,
                job_name,
                tenant_id,
                user_id
            )
