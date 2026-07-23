import os
import sys
import asyncio
import logging
from pathlib import Path
import asyncpg

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migration_runner")


async def run_migrations() -> None:
    # Resolve DB credentials
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "postgres")
    user = os.environ.get("POSTGRES_USER", "postgres")
    password = os.environ.get("POSTGRES_PASSWORD", "postgres")

    logger.info(f"Connecting to database {host}:{port}/{db}...")
    try:
        conn = await asyncpg.connect(
            host=host,
            port=int(port),
            database=db,
            user=user,
            password=password,
        )
    except Exception as e:
        logger.error(f"Failed to connect to PostgreSQL database: {e}")
        sys.exit(1)

    try:
        # Create migrations tracking table if not exists
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS migrations_applied (
                migration_name TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """)

        # Find migration SQL files
        migrations_dir = Path(__file__).parent / "migrations"
        if not migrations_dir.exists():
            logger.error(f"Migrations directory not found: {migrations_dir}")
            sys.exit(1)

        sql_files = sorted(migrations_dir.glob("*.sql"))
        logger.info(f"Found {len(sql_files)} migration files.")

        for sql_file in sql_files:
            migration_name = sql_file.name
            
            # Check if migration already applied
            already_applied = await conn.fetchval(
                "SELECT EXISTS(SELECT 1 FROM migrations_applied WHERE migration_name = $1)",
                migration_name
            )

            if already_applied:
                logger.info(f"Migration {migration_name} is already applied. Skipping.")
                continue

            logger.info(f"Applying migration {migration_name}...")
            sql_content = sql_file.read_text(encoding="utf-8")

            # Execute migration in transaction block
            async with conn.transaction():
                await conn.execute(sql_content)
                await conn.execute(
                    "INSERT INTO migrations_applied (migration_name) VALUES ($1)",
                    migration_name
                )
            logger.info(f"Migration {migration_name} applied successfully.")

    except Exception as e:
        logger.error(f"Migration execution failed: {e}")
        sys.exit(1)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_migrations())
