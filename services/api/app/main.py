from fastapi import FastAPI
from .routes.chat import router as chat_router

app = FastAPI(title="MemoryOps AI Gateway API")

# Include the routes with prefix /api
app.include_router(chat_router, prefix="/api")
