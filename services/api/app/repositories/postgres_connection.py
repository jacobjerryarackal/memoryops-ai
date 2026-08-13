import os
import logging
import asyncpg
from typing import Optional
from pgvector.asyncpg import register_vector

logger = logging.getLogger("app.repositories.postgres_connection")


async def init_connection(conn: asyncpg.Connection) -> None:
    """
    Callback to initialize every connection acquired from the pool.
    Registers the pgvector custom type handler.
    """
    try:
        await register_vector(conn)
        
        # Check if connected as superuser and log a warning
        is_super = await conn.fetchval("SELECT usesuper FROM pg_user WHERE usename = current_user")
        if is_super:
            logger.warning(
                "DATABASE SECURITY WARNING: Connected to PostgreSQL as a superuser. "
                "Row-Level Security (RLS) policies will be bypassed by default for all queries."
            )
    except Exception as e:
        logger.error(f"Failed to register pgvector on database connection: {e}")
        # Note: If the vector extension is not yet installed in the target DB,
        # register_vector may fail. We log this and propagate to prevent silent failures.
        raise


import ssl
from typing import Optional, Any
from ..config import settings


class DatabaseConnectionManager:
    """
    Manages the lifespan of the PostgreSQL connection pool.
    """

    def __init__(self) -> None:
        self.pool: Optional[asyncpg.Pool] = None

    async def initialize(self) -> None:
        if self.pool is not None:
            return

        logger.info(f"Initializing PostgreSQL connection pool on {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}...")

        ssl_mode = settings.postgres_ssl.strip().lower()
        ssl_param = None
        if ssl_mode == "disable":
            ssl_param = False
        elif ssl_mode == "prefer":
            ssl_param = "prefer"
        elif ssl_mode == "require":
            ssl_param = True
        elif ssl_mode in ("verify-ca", "verify-full"):
            ssl_context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
            if ssl_mode == "verify-ca":
                ssl_context.check_hostname = False
            else:
                ssl_context.check_hostname = True
            ssl_context.verify_mode = ssl.CERT_REQUIRED
            ssl_param = ssl_context

        try:
            self.pool = await asyncpg.create_pool(
                host=settings.postgres_host,
                port=settings.postgres_port,
                database=settings.postgres_db,
                user=settings.postgres_user,
                password=settings.postgres_password,
                min_size=settings.postgres_min_pool_size,
                max_size=settings.postgres_max_pool_size,
                timeout=settings.postgres_connection_timeout,
                ssl=ssl_param,
                init=init_connection,
            )
            logger.info("PostgreSQL connection pool initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL connection pool: {e}")
            raise

    async def close(self) -> None:
        if self.pool is not None:
            logger.info("Closing PostgreSQL connection pool...")
            await self.pool.close()
            self.pool = None
            logger.info("PostgreSQL connection pool closed.")


# Shared global instance of connection manager
db_manager = DatabaseConnectionManager()
