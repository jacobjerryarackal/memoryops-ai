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
    except Exception as e:
        logger.error(f"Failed to register pgvector on database connection: {e}")
        # Note: If the vector extension is not yet installed in the target DB,
        # register_vector may fail. We log this and propagate to prevent silent failures.
        raise


class DatabaseConnectionManager:
    """
    Manages the lifespan of the PostgreSQL connection pool.
    """

    def __init__(self) -> None:
        self.pool: Optional[asyncpg.Pool] = None

    async def initialize(self) -> None:
        if self.pool is not None:
            return

        host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
        port = os.environ.get("POSTGRES_PORT", "5432")
        db = os.environ.get("POSTGRES_DB", "postgres")
        user = os.environ.get("POSTGRES_USER", "postgres")
        password = os.environ.get("POSTGRES_PASSWORD", "postgres")

        logger.info(f"Initializing PostgreSQL connection pool on {host}:{port}/{db}...")

        try:
            self.pool = await asyncpg.create_pool(
                host=host,
                port=int(port),
                database=db,
                user=user,
                password=password,
                min_size=2,
                max_size=10,
                timeout=10.0,
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
