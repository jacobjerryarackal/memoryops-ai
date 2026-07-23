import os
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .routes.chat import router as chat_router
from .routes.governance import router as governance_router
from .repositories.postgres_connection import db_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Only initialize postgres pool if configured to run with postgres
    db_type = os.environ.get("DATABASE_TYPE", "memory").strip().lower()
    if db_type == "postgres":
        await db_manager.initialize()
    yield
    if db_type == "postgres":
        await db_manager.close()


app = FastAPI(title="MemoryOps AI Gateway API", lifespan=lifespan)

START_TIME = time.time()


@app.get("/healthz")
async def healthz():
    return {
        "status": "ok",
        "version": "0.1.0",
        "uptime_seconds": int(time.time() - START_TIME)
    }


@app.get("/readyz")
async def readyz():
    has_key = bool(os.environ.get("OPENAI_API_KEY"))
    return {
        "ready": has_key,
        "storage": "ready",
        "llm_provider": "ready",
        "embeddings_provider": "ready" if has_key else "unconfigured",
        "detail": {}
    }


# Include the routes with prefix /api
app.include_router(chat_router, prefix="/api")
app.include_router(governance_router, prefix="/api")
