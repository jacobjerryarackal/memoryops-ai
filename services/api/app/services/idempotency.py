import json
import logging
import hashlib
from typing import Optional, Tuple
from fastapi import Request, Header, HTTPException, status
from fastapi.responses import JSONResponse

from app.repositories.postgres import scoped_connection, db_bypass_rls, rls_bypass
from app.repositories.postgres_connection import db_manager

logger = logging.getLogger("app.services.idempotency")


class IdempotencyService:
    def __init__(self) -> None:
        # In-memory fallback cache: mem_key -> {"status": status_code, "body": body, "hash": request_hash, "in_progress": bool}
        self._in_memory_store = {}

    def _calculate_hash(self, payload: dict) -> str:
        # Sort keys to guarantee stable hashing of incoming payloads
        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    async def get_cached_response(
        self, key: str, tenant_id: str, user_id: str, request_payload: Optional[dict] = None
    ) -> Optional[Tuple[int, dict]]:
        """
        Retrieves cached response. Checks for payload conflicts.
        Raises 409 Conflict if payload doesn't match or request is in progress.
        If no cache hit is found, attempts to acquire the lock.
        """
        request_hash = self._calculate_hash(request_payload) if request_payload is not None else None
        mem_key = (key, tenant_id, user_id)

        # 1. Try PostgreSQL store first
        if db_manager.pool is not None:
            try:
                async with scoped_connection(tenant_id, user_id) as conn:
                    row = await conn.fetchrow(
                        """
                        SELECT response_status, response_body FROM idempotency_records 
                        WHERE key = $1 AND tenant_id = $2 AND user_id = $3
                        """,
                        key, tenant_id, user_id
                    )
                    if row:
                        response_status = row["response_status"]
                        # If status is 102, it means a concurrent request is processing it
                        if response_status == 102:
                            logger.warning(f"Concurrent request in progress for key: {key}")
                            raise HTTPException(
                                status_code=status.HTTP_409_CONFLICT,
                                detail="A concurrent request is already processing this idempotency key."
                            )
                        
                        # Unpack wrapped response to verify hash
                        try:
                            wrapped = json.loads(row["response_body"])
                            if isinstance(wrapped, dict) and "request_hash" in wrapped:
                                stored_hash = wrapped.get("request_hash")
                                actual_body = wrapped.get("response_body")
                            else:
                                stored_hash = None
                                actual_body = wrapped
                        except Exception:
                            stored_hash = None
                            actual_body = row["response_body"]
                        
                        if stored_hash is not None and request_hash is not None and stored_hash != request_hash:
                            logger.warning(f"Idempotency key conflict: payload mismatch for key: {key}")
                            raise HTTPException(
                                status_code=status.HTTP_409_CONFLICT,
                                detail="Idempotency key conflict: this key has already been used for a different request."
                            )
                        
                        logger.info(f"Idempotency cache hit (PostgreSQL) for key: {key}")
                        return response_status, actual_body
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error reading idempotency key from PostgreSQL: {str(e)}")

        # 2. Try in-memory store fallback
        if mem_key in self._in_memory_store:
            record = self._in_memory_store[mem_key]
            if record.get("in_progress"):
                logger.warning(f"Concurrent request (in-memory) in progress for key: {key}")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A concurrent request is already processing this idempotency key."
                )
            if record.get("hash") is not None and request_hash is not None and record.get("hash") != request_hash:
                logger.warning(f"Idempotency key conflict (in-memory): payload mismatch for key: {key}")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency key conflict: this key has already been used for a different request."
                )
            logger.info(f"Idempotency cache hit (in-memory) for key: {key}")
            # Resolve inner body if wrapped
            actual_mem_body = record["body"].get("response_body") if isinstance(record["body"], dict) and "response_body" in record["body"] else record["body"]
            return record["status"], actual_mem_body

        # No cache hit. Let's acquire the lock!
        await self.acquire_lock(key, tenant_id, user_id, request_payload or {})
        return None

    async def acquire_lock(
        self, key: str, tenant_id: str, user_id: str, request_payload: dict
    ) -> None:
        """
        Acquires the lock for processing a new request.
        Inserts status 102 into PostgreSQL, or sets in_progress in memory.
        """
        request_hash = self._calculate_hash(request_payload)
        mem_key = (key, tenant_id, user_id)

        # Set in-progress in memory
        self._in_memory_store[mem_key] = {
            "status": 102,
            "body": {},
            "hash": request_hash,
            "in_progress": True
        }

        if db_manager.pool is not None:
            try:
                # Wrap request hash in payload
                wrapped = {"request_hash": request_hash, "response_body": {}}
                async with scoped_connection(tenant_id, user_id) as conn:
                    # Try to insert atomically
                    res = await conn.execute(
                        """
                        INSERT INTO idempotency_records (key, tenant_id, user_id, response_status, response_body)
                        VALUES ($1, $2, $3, 102, $4)
                        ON CONFLICT (key, tenant_id, user_id) DO NOTHING
                        """,
                        key, tenant_id, user_id, json.dumps(wrapped)
                    )
                    # If insert failed (0 rows affected), fetch the current status
                    if res == "INSERT 0 0":
                        row = await conn.fetchrow(
                            "SELECT response_status, response_body FROM idempotency_records WHERE key = $1 AND tenant_id = $2 AND user_id = $3",
                            key, tenant_id, user_id
                        )
                        if row:
                            if row["response_status"] == 102:
                                raise HTTPException(
                                    status_code=status.HTTP_409_CONFLICT,
                                    detail="A concurrent request is already processing this idempotency key."
                                )
                            try:
                                wrapped_body = json.loads(row["response_body"])
                                stored_hash = wrapped_body.get("request_hash") if isinstance(wrapped_body, dict) else None
                            except Exception:
                                stored_hash = None
                            if stored_hash is not None and stored_hash != request_hash:
                                raise HTTPException(
                                    status_code=status.HTTP_409_CONFLICT,
                                    detail="Idempotency key conflict: this key has already been used for a different request."
                                )
                            # Completed by another thread while we tried to acquire
                            raise HTTPException(
                                status_code=status.HTTP_409_CONFLICT,
                                detail="Idempotency key already processed."
                            )
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error acquiring idempotency lock in PostgreSQL: {str(e)}")

    async def cache_response(
        self, key: str, tenant_id: str, user_id: str, status_code: int, body: dict, request_payload: Optional[dict] = None
    ) -> None:
        """
        Releases the lock and stores the completed response.
        """
        request_hash = self._calculate_hash(request_payload) if request_payload is not None else None
        mem_key = (key, tenant_id, user_id)

        # Update in memory
        self._in_memory_store[mem_key] = {
            "status": status_code,
            "body": {"request_hash": request_hash, "response_body": body} if request_hash is not None else body,
            "hash": request_hash,
            "in_progress": False
        }

        if db_manager.pool is not None:
            try:
                wrapped = {"request_hash": request_hash, "response_body": body} if request_hash is not None else body
                async with scoped_connection(tenant_id, user_id) as conn:
                    # Update status and body
                    await conn.execute(
                        """
                        INSERT INTO idempotency_records (key, tenant_id, user_id, response_status, response_body)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (key, tenant_id, user_id) DO UPDATE 
                        SET response_status = EXCLUDED.response_status, response_body = EXCLUDED.response_body
                        """,
                        key, tenant_id, user_id, status_code, json.dumps(wrapped)
                    )
            except Exception as e:
                logger.error(f"Error caching idempotency key in PostgreSQL: {str(e)}")

    async def remove_lock(self, key: str, tenant_id: str, user_id: str) -> None:
        """
        Removes the lock from both stores. Useful if request processing failed.
        """
        mem_key = (key, tenant_id, user_id)
        self._in_memory_store.pop(mem_key, None)

        if db_manager.pool is not None:
            try:
                async with scoped_connection(tenant_id, user_id) as conn:
                    await conn.execute(
                        "DELETE FROM idempotency_records WHERE key = $1 AND tenant_id = $2 AND user_id = $3",
                        key, tenant_id, user_id
                    )
            except Exception as e:
                logger.error(f"Error deleting idempotency key from PostgreSQL: {str(e)}")

    def clear(self) -> None:
        self._in_memory_store.clear()


# Global instance
idempotency_service = IdempotencyService()
