import uuid
from typing import List, Optional
from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from ..domain.enums import MemoryType, Sensitivity, PolicyDecision, RetrievalMode
from ..domain.retrieval import UsedMemory

router = APIRouter()


class ChatRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    message: str
    temporary_chat: bool = False
    conversation_id: Optional[str] = None

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("message cannot be empty or whitespace-only")
        return v


class ChatResponseCandidate(BaseModel):
    content: str
    memory_type: MemoryType
    confidence: float = Field(..., ge=0.0, le=1.0)
    importance: int = Field(..., ge=0, le=10)
    sensitivity: Sensitivity
    decision: PolicyDecision
    reason: str
    memory_id: Optional[str] = None


class ChatResponse(BaseModel):
    assistant_message: str
    used_memories: List[UsedMemory]
    candidate_memories: List[ChatResponseCandidate]
    audit_event_ids: List[str]
    temporary_chat: bool
    retrieval_mode: RetrievalMode
    trace_id: str


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    # Dynamic per-request UUID string for trace_id boundary placeholder
    trace_id = f"trace-{uuid.uuid4()}"
    return ChatResponse(
        assistant_message="Understood.",
        used_memories=[],
        candidate_memories=[],
        audit_event_ids=[],
        temporary_chat=request.temporary_chat,
        retrieval_mode=RetrievalMode.NONE,
        trace_id=trace_id,
    )
