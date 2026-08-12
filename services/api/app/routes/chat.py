import uuid
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from ..domain.enums import MemoryType, Sensitivity, PolicyDecision, RetrievalMode, AuditEventAction
from ..domain.models import CandidateMemory, MemoryRecord
from ..domain.retrieval import UsedMemory
from ..runtime import get_retrieval_coordinator, get_memory_repository, get_audit_service
from ..services.retrieval import RetrievalCoordinator
from ..services.write import WriteService
from ..policy.broker import PolicyBroker

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from app.services.idempotency import idempotency_service

router = APIRouter()
logger = logging.getLogger("app.routes.chat")


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


def extract_candidate_from_message(message: str, tenant_id: str, user_id: str) -> Optional[CandidateMemory]:
    msg = message.strip()
    msg_lower = msg.lower()
    
    if not msg_lower.startswith("remember that "):
        return None
        
    statement = msg[len("remember that "):].strip()
    content_processed = statement
    
    # Pronoun normalization for standard user declarations
    if statement.lower().startswith("i prefer "):
        content_processed = "User prefers " + statement[len("i prefer "):]
    elif statement.lower().startswith("my api key is "):
        content_processed = statement
    elif statement.lower().startswith("i know "):
        content_processed = "User knows " + statement[len("i know "):]
        
    # Default values
    memory_type = MemoryType.SEMANTIC
    confidence = 0.90
    importance = 5
    sensitivity = Sensitivity.LOW
    identity_slot = None
    
    content_lower = content_processed.lower()
    
    if "api key" in content_lower or "password" in content_lower or "sk-" in content_lower:
        memory_type = MemoryType.SEMANTIC
        confidence = 0.95
        importance = 8
        sensitivity = Sensitivity.LOW
        identity_slot = None
    elif "prefer" in content_lower:
        memory_type = MemoryType.PROCEDURAL
        confidence = 0.92
        importance = 8
        sensitivity = Sensitivity.LOW
        
        if "style" in content_lower or "explanation" in content_lower:
            identity_slot = "explanation_style"
        elif "hashtag" in content_lower:
            identity_slot = "formatting_hashtags"
        elif "hyphen" in content_lower:
            identity_slot = "formatting_hyphens"
    elif "live in" in content_lower or "residence" in content_lower:
        memory_type = MemoryType.SEMANTIC
        confidence = 0.90
        importance = 6
        sensitivity = Sensitivity.LOW
        identity_slot = "residence"
    elif "engineer" in content_lower or "profession" in content_lower or "work as" in content_lower:
        memory_type = MemoryType.SEMANTIC
        confidence = 0.92
        importance = 7
        sensitivity = Sensitivity.LOW
        identity_slot = "profession"
    elif "python" in content_lower or "rust" in content_lower or "backend" in content_lower:
        memory_type = MemoryType.SEMANTIC
        confidence = 0.90
        importance = 7
        sensitivity = Sensitivity.LOW
        identity_slot = "technology_stack"
        
    return CandidateMemory(
        tenant_id=tenant_id,
        user_id=user_id,
        content=content_processed,
        memory_type=memory_type,
        confidence=confidence,
        importance=importance,
        sensitivity=sensitivity,
        source_kind="chat",
        source_conversation_id="conversation_demo",
        source_excerpt=msg,
        identity_slot=identity_slot
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    coordinator: RetrievalCoordinator = Depends(get_retrieval_coordinator),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
):
    if x_idempotency_key:
        cached = await idempotency_service.get_cached_response(
            x_idempotency_key, request.tenant_id, request.user_id
        )
        if cached:
            status_code, body = cached
            return JSONResponse(status_code=status_code, content=body)

    # Dynamic per-request UUID string for trace_id boundary placeholder
    trace_id = f"trace-{uuid.uuid4()}"
    logger.info(f"[{trace_id}] Entered chat route. Message: '{request.message}', Tenant: '{request.tenant_id}', User: '{request.user_id}'")

    # 1. Execute read-path retrieval context through the coordinator
    logger.info(f"[{trace_id}] Invoking RetrievalCoordinator...")
    context, used_memories, retrieval_mode = await coordinator.retrieve_context(
        tenant_id=request.tenant_id,
        user_id=request.user_id,
        query_text=request.message,
        temporary_chat=request.temporary_chat,
        trace_id=trace_id,
    )
    logger.info(f"[{trace_id}] Retrieval completed. Mode: {retrieval_mode}, Used memories: {len(used_memories)}")

    candidate_memories = []
    audit_event_ids = []

    # 2. Execute write-path extraction, policy validation, and persistence if not temporary chat
    if not request.temporary_chat:
        logger.info(f"[{trace_id}] Extracting candidate memory...")
        candidate = extract_candidate_from_message(request.message, request.tenant_id, request.user_id)
        
        if candidate:
            logger.info(f"[{trace_id}] Candidate extracted: content='{candidate.content}', type={candidate.memory_type}, slot={candidate.identity_slot}")
            
            # Instantiate Policy Broker and Write Service
            repository = get_memory_repository()
            audit_service = get_audit_service()
            broker = PolicyBroker(repository=repository)
            write_service = WriteService(broker=broker, repository=repository, audit_service=audit_service)
            
            logger.info(f"[{trace_id}] Invoking WriteService.process()...")
            try:
                write_result = await write_service.process(candidate, trace_id=trace_id)
                logger.info(f"[{trace_id}] WriteService completed. Decision: {write_result.policy_result.decision}, Reason: '{write_result.policy_result.reason}'")
                
                # Capture audit event
                if write_result.audit_event_id:
                    audit_event_ids.append(write_result.audit_event_id)
                    logger.info(f"[{trace_id}] Recorded audit event ID: {write_result.audit_event_id}")

                res_candidate = ChatResponseCandidate(
                    content=candidate.content,
                    memory_type=candidate.memory_type,
                    confidence=candidate.confidence,
                    importance=candidate.importance,
                    sensitivity=candidate.sensitivity,
                    decision=write_result.policy_result.decision,
                    reason=write_result.policy_result.reason,
                    memory_id=str(write_result.memory.id) if write_result.memory else None
                )
                candidate_memories.append(res_candidate)

                # 3. Post-commit embedding generation (Non-blocking / Graceful Degradation)
                if write_result.memory and write_result.policy_result.decision in [PolicyDecision.SAVE, PolicyDecision.UPDATE_EXISTING]:
                    logger.info(f"[{trace_id}] Generating vector embedding post-commit for content: '{write_result.memory.content}'")
                    try:
                        embedding = await coordinator._embedding_service.generate_embedding(write_result.memory.content)
                        updated_rec = write_result.memory.model_copy(deep=True)
                        updated_rec.embedding = embedding
                        await repository.update(updated_rec)
                        logger.info(f"[{trace_id}] Embedding generated and persisted successfully.")
                        res_candidate.memory_id = str(updated_rec.id)
                    except Exception as emb_err:
                        logger.warning(f"[{trace_id}] Failed to generate embedding for written memory (degrading gracefully): {emb_err}")
                        
            except Exception as write_err:
                logger.exception(f"[{trace_id}] Error in write pipeline processing: {write_err}")
                # We do not fail the chat response, but log it and continue
        else:
            logger.info(f"[{trace_id}] No candidate memory extracted from message.")
    else:
        logger.info(f"[{trace_id}] Bypassing write path: temporary_chat is True")

    resp_obj = ChatResponse(
        assistant_message="Understood.",
        used_memories=used_memories,
        candidate_memories=candidate_memories,
        audit_event_ids=audit_event_ids,
        temporary_chat=request.temporary_chat,
        retrieval_mode=retrieval_mode,
        trace_id=trace_id,
    )

    encoded = jsonable_encoder(resp_obj)
    if x_idempotency_key:
        await idempotency_service.cache_response(
            x_idempotency_key, request.tenant_id, request.user_id, 200, encoded
        )

    return resp_obj

