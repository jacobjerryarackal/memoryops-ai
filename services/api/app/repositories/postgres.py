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

from ..domain.models import MemoryRecord, AuditEvent
from ..domain.enums import MemoryStatus, MemoryType, Sensitivity, PolicyDecision, AuditEventAction
from .base import MemoryRepository
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
        return await coro_func(conn)
    finally:
        await conn.close()


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
        yield conn
    else:
        await ensure_active_pool()
        async with db_manager.pool.acquire() as conn_acquired:
            yield conn_acquired


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
                            identity_slot = $21
                        WHERE id = $1
                        """,
                        value.id, value.tenant_id, value.user_id, value.content, value.memory_type.value,
                        value.status.value, value.sensitivity.value, value.importance, value.confidence,
                        value.reinforcement_count, value.embedding, value.source_kind, value.source_conversation_id,
                        value.source_excerpt, value.initial_policy_decision.value, value.initial_policy_reason,
                        value.created_at, value.updated_at, value.archived_at, value.deleted_at, value.identity_slot
                    )
                else:
                    await conn.execute(
                        """
                        INSERT INTO memories (
                            id, tenant_id, user_id, content, memory_type, status, sensitivity,
                            importance, confidence, reinforcement_count, embedding, source_kind,
                            source_conversation_id, source_excerpt, initial_policy_decision,
                            initial_policy_reason, created_at, updated_at, archived_at, deleted_at,
                            identity_slot
                        ) VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21
                        )
                        """,
                        value.id, value.tenant_id, value.user_id, value.content, value.memory_type.value,
                        value.status.value, value.sensitivity.value, value.importance, value.confidence,
                        value.reinforcement_count, value.embedding, value.source_kind, value.source_conversation_id,
                        value.source_excerpt, value.initial_policy_decision.value, value.initial_policy_reason,
                        value.created_at, value.updated_at, value.archived_at, value.deleted_at, value.identity_slot
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
                                identity_slot
                            ) VALUES (
                                $1, $2, $3, 'dummy', 'semantic', 'active', 'low', 5, 0.0, 0, NULL, 'chat', NULL, NULL, 'SAVE', 'dummy', NOW(), NOW(), NULL, NULL, NULL
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


class PostgreSQLMemoryRepository(MemoryRepository):
    def __init__(self) -> None:
        self._records = PostgresDictProxy("memories")

    async def create(self, record: MemoryRecord) -> MemoryRecord:
        try:
            async with get_connection() as conn:
                await conn.execute(
                    """
                    INSERT INTO memories (
                        id, tenant_id, user_id, content, memory_type, status, sensitivity,
                        importance, confidence, reinforcement_count, embedding, source_kind,
                        source_conversation_id, source_excerpt, initial_policy_decision,
                        initial_policy_reason, created_at, updated_at, archived_at, deleted_at,
                        identity_slot
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21
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
                )
        except asyncpg.exceptions.UniqueViolationError:
            raise ValueError(f"Duplicate key: Memory record with ID {record.id} already exists.")

        return record.model_copy(deep=True)

    async def get_by_id(
        self, memory_id: UUID, tenant_id: str, user_id: str
    ) -> Optional[MemoryRecord]:
        async with get_connection() as conn:
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
        async with get_connection() as conn:
            # Check if record exists at all
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
                raise ValueError("Terminal deletion: cannot update a logically deleted memory record.")

            # 5. Enforce segregation of deletion
            if record.status == MemoryStatus.DELETED:
                raise ValueError("Segregation of deletion: logical deletion must occur via the delete() method.")

            new_updated_at = datetime.now(timezone.utc)

            await conn.execute(
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
                    deleted_at = $16
                WHERE id = $1 AND tenant_id = $2 AND user_id = $3
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
            )

            # Return updated record
            copied = record.model_copy(deep=True)
            copied.updated_at = new_updated_at
            return copied

    async def delete(
        self, memory_id: UUID, tenant_id: str, user_id: str
    ) -> MemoryRecord:
        async with get_connection() as conn:
            persisted_row = await conn.fetchrow("SELECT * FROM memories WHERE id = $1", memory_id)
            if persisted_row is None:
                raise ValueError(f"Missing target: Memory record with ID {memory_id} does not exist.")

            persisted = row_to_memory_record(persisted_row)

            # Verify scope
            if persisted.tenant_id != tenant_id or persisted.user_id != user_id:
                raise ValueError("Scope mismatch: unauthorized deletion attempt.")

            if persisted.status == MemoryStatus.DELETED:
                return persisted

            now = datetime.now(timezone.utc)
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
        async with get_connection() as conn:
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

        async with get_connection() as conn:
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
        async with get_connection() as conn:
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

        async with get_connection() as conn:
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
            async with get_connection() as conn:
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

        async with get_connection() as conn:
            rows = await conn.fetch(query, *params)
            return [row_to_audit_event(r) for r in rows]
