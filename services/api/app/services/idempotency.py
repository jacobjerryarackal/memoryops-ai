import json
import logging
from typing import Optional, Tuple
from fastapi import Request, Header, HTTPException, status
from fastapi.responses import JSONResponse

from app.repositories.postgres import scoped_connection, db_bypass_rls, rls_bypass
from app.repositories.postgres_connection import db_manager

logger = logging.getLogger("app.services.idempotency")


class IdempotencyService:
    def __init__(self) -> None:
        # In-memory dictionary fallback cache for tests/development
        self._in_memory_store = {}

    async def get_cached_response(
        self, key: str, tenant_id: str, user_id: str
    ) -> Optional[Tuple[int, dict]]:
        # 1. Try in-memory store
        mem_key = (key, tenant_id, user_id)
        if mem_key in self._in_memory_store:
            logger.info(f"Idempotency cache hit (in-memory) for key: {key}")
            return self._in_memory_store[mem_key]

        # 2. Try PostgreSQL store
        if db_manager.pool is not None:
            try:
                # Retrieve matching record under scoped connection
                async with scoped_connection(tenant_id, user_id) as conn:
                    row = await conn.fetchrow(
                        """
                        SELECT response_status, response_body FROM idempotency_records 
                        WHERE key = $1 AND tenant_id = $2 AND user_id = $3
                        """,
                        key, tenant_id, user_id
                    )
                    if row:
                        logger.info(f"Idempotency cache hit (PostgreSQL) for key: {key}")
                        return row["response_status"], json.loads(row["response_body"])
            except Exception as e:
                logger.error(f"Error reading idempotency key from PostgreSQL: {str(e)}")
                
        return None

    async def cache_response(
        self, key: str, tenant_id: str, user_id: str, status_code: int, body: dict
    ) -> None:
        mem_key = (key, tenant_id, user_id)
        self._in_memory_store[mem_key] = (status_code, body)

        if db_manager.pool is not None:
            try:
                async with scoped_connection(tenant_id, user_id) as conn:
                    await conn.execute(
                        """
                        INSERT INTO idempotency_records (key, tenant_id, user_id, response_status, response_body)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (key, tenant_id, user_id) DO NOTHING
                        """,
                        key, tenant_id, user_id, status_code, json.dumps(body)
                    )
            except Exception as e:
                logger.error(f"Error caching idempotency key in PostgreSQL: {str(e)}")

    def clear(self) -> None:
        self._in_memory_store.clear()


# Global instance
idempotency_service = IdempotencyService()
