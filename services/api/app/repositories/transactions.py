import os
import logging
import contextvars
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any, List
import asyncpg

from .postgres_connection import db_manager

logger = logging.getLogger("app.repositories.transactions")

# Contextvar to hold the active PostgreSQL connection for the transaction
db_tx_conn = contextvars.ContextVar("db_tx_conn", default=None)

# Contextvar to hold the stack of in-memory snapshots for nested rollback simulation
in_memory_tx_snapshots = contextvars.ContextVar("in_memory_tx_snapshots", default=None)


class TransactionManager:
    """
    Manages the lifecycle of transaction blocks. Supports both true PostgreSQL
    transactions (with nested SAVEPOINTs) and simulated in-memory rollbacks.
    """

    def __init__(self, force_in_memory: bool = False) -> None:
        self.force_in_memory = force_in_memory

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        db_type = os.environ.get("DATABASE_TYPE", "memory").strip().lower()

        if db_type == "postgres" and not self.force_in_memory:
            conn = db_tx_conn.get()
            if conn is not None:
                # Nested transaction: asyncpg uses database SAVEPOINTs under the hood
                logger.debug("Entering nested PostgreSQL transaction (SAVEPOINT)")
                async with conn.transaction():
                    yield
            else:
                # Root transaction: acquire a connection from the pool and start a transaction
                logger.debug("Beginning root PostgreSQL transaction")
                
                # Import ensure_active_pool dynamically to avoid circular dependency
                from .postgres import ensure_active_pool
                await ensure_active_pool()

                async with db_manager.pool.acquire() as new_conn:
                    token = db_tx_conn.set(new_conn)
                    try:
                        async with new_conn.transaction():
                            yield
                    finally:
                        db_tx_conn.reset(token)
        else:
            # In-Memory simulated transaction rollback
            from ..runtime import get_memory_repository, get_audit_service
            repo = get_memory_repository()
            audit = get_audit_service()

            # Detect internal dictionary storage
            has_records = hasattr(repo, "_records") and isinstance(repo._records, dict)
            has_events = hasattr(audit, "_events") and isinstance(audit._events, dict)

            # Capture snapshot of state
            snapshot = {}
            if has_records:
                snapshot["records"] = dict(repo._records)
            if has_events:
                snapshot["events"] = dict(audit._events)

            # Get or initialize the snapshot stack in contextvars
            stack = in_memory_tx_snapshots.get()
            token_stack = None
            if stack is None:
                stack = []
                token_stack = in_memory_tx_snapshots.set(stack)

            stack.append(snapshot)
            logger.debug(f"Pushed in-memory snapshot (stack depth: {len(stack)})")

            try:
                yield
                # Block completed successfully: discard the snapshot from stack
                stack.pop()
            except Exception as e:
                logger.warning(f"Exception raised in in-memory transaction: {e}. Restoring snapshot state.")
                # Rollback: pop and restore the captured snapshot
                snap = stack.pop()
                if has_records and "records" in snap:
                    repo._records.clear()
                    repo._records.update(snap["records"])
                if has_events and "events" in snap:
                    audit._events.clear()
                    audit._events.update(snap["events"])
                raise
            finally:
                if token_stack is not None:
                    in_memory_tx_snapshots.reset(token_stack)
