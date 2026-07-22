import os
import time
from fastapi import FastAPI
from .routes.chat import router as chat_router
from .routes.governance import router as governance_router

app = FastAPI(title="MemoryOps AI Gateway API")

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
