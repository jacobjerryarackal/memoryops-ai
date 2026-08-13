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

# Contextvar to hold the stack of in-memory undo logs for nested rollback simulation
in_memory_tx_undo_logs = contextvars.ContextVar("in_memory_tx_undo_logs", default=None)


def log_in_memory_write(category: str, key: Any, original_value: Any) -> None:
    """
    Log original state of a key before modification to allow targeted rollback.
    """
    stack = in_memory_tx_undo_logs.get()
    if stack:
        current_log = stack[-1]
        if key not in current_log[category]:
            if original_value is not None:
                if hasattr(original_value, "model_copy"):
                    copied = original_value.model_copy(deep=True)
                else:
                    import copy
                    copied = copy.deepcopy(original_value)
            else:
                copied = None
            current_log[category][key] = copied


class TransactionManager:
    """
    Manages the lifecycle of transaction blocks. Supports both true PostgreSQL
    transactions (with nested SAVEPOINTs) and simulated in-memory rollbacks.
    """

    def __init__(self, force_in_memory: bool = False) -> None:
        self.force_in_memory = force_in_memory

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        from ..services.observability import obs
        with obs.span("TransactionManager.transaction"):
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
                # In-Memory simulated transaction rollback using undo logs
                from ..runtime import get_memory_repository, get_audit_service
                repo = get_memory_repository()
                audit = get_audit_service()

                has_records = hasattr(repo, "_records") and isinstance(repo._records, dict)
                has_events = hasattr(audit, "_events") and isinstance(audit._events, dict)

                # Initialize undo log for this level
                undo_log = {"records": {}, "events": {}}

                stack = in_memory_tx_undo_logs.get()
                token_stack = None
                if stack is None:
                    stack = []
                    token_stack = in_memory_tx_undo_logs.set(stack)

                stack.append(undo_log)
                logger.debug(f"Pushed in-memory undo log (stack depth: {len(stack)})")

                try:
                    yield
                    # Block completed successfully: discard undo log from stack
                    stack.pop()
                except Exception as e:
                    logger.warning(f"Exception raised in in-memory transaction: {e}. Restoring state via undo logs.")
                    # Rollback: pop and restore the captured keys for this block
                    log = stack.pop()
                    
                    if has_records:
                        for k, v in log["records"].items():
                            if v is None:
                                repo._records.pop(k, None)
                            else:
                                repo._records[k] = v
                                
                    if has_events:
                        for k, v in log["events"].items():
                            if v is None:
                                audit._events.pop(k, None)
                            else:
                                audit._events[k] = v
                    raise
                finally:
                    if token_stack is not None:
                        in_memory_tx_undo_logs.reset(token_stack)
