import uuid
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status, Header
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from app.services.idempotency import idempotency_service
from pydantic import BaseModel, Field

from ..domain.enums import MemoryStatus, MemoryType, Sensitivity
from ..domain.models import AuditEvent, MemoryRecord
from ..runtime import get_governance_service
from ..services.governance import (
    GovernanceInvalidTransitionError,
    GovernancePolicyBlockedError,
    GovernanceService,
    GovernanceTargetUnavailableError,
    GovernanceValidationError,
)

router = APIRouter()


class PatchMemoryRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    content: Optional[str] = None
    importance: Optional[int] = Field(None, ge=0, le=10)
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    status: Optional[MemoryStatus] = None
    sensitivity: Optional[Sensitivity] = None
    source_kind: Optional[str] = None
    source_conversation_id: Optional[str] = None
    source_excerpt: Optional[str] = None


class DeleteMemoryRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)


class DeleteMemoryResponse(BaseModel):
    memory_id: UUID
    status: MemoryStatus
    deleted_at: str


def make_error_response(code: str, message: str, trace_id: str) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "trace_id": trace_id
        }
    }


@router.get("/memories", response_model=List[MemoryRecord])
async def list_memories(
    tenant_id: str = Query(..., min_length=1),
    user_id: str = Query(..., min_length=1),
    status: Optional[MemoryStatus] = None,
    memory_type: Optional[MemoryType] = None,
    service: GovernanceService = Depends(get_governance_service),
):
    records = await service.list_memories(
        tenant_id=tenant_id, user_id=user_id, status=status, memory_type=memory_type
    )
    return records


@router.get("/memories/{memory_id}", response_model=MemoryRecord)
async def get_memory(
    memory_id: UUID,
    tenant_id: str = Query(..., min_length=1),
    user_id: str = Query(..., min_length=1),
    service: GovernanceService = Depends(get_governance_service),
):
    trace_id = f"trace-{uuid.uuid4()}"
    try:
        record = await service.get_memory_by_id(
            memory_id=memory_id, tenant_id=tenant_id, user_id=user_id
        )
        return record
    except GovernanceTargetUnavailableError as e:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=make_error_response("MEMORY_NOT_FOUND", str(e), trace_id),
        )


@router.get("/memories/{memory_id}/provenance", response_model=Dict[str, Any])
async def get_provenance(
    memory_id: UUID,
    tenant_id: str = Query(..., min_length=1),
    user_id: str = Query(..., min_length=1),
    service: GovernanceService = Depends(get_governance_service),
):
    trace_id = f"trace-{uuid.uuid4()}"
    try:
        prov = await service.get_memory_provenance(
            memory_id=memory_id, tenant_id=tenant_id, user_id=user_id
        )
        return prov
    except GovernanceTargetUnavailableError as e:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=make_error_response("MEMORY_NOT_FOUND", str(e), trace_id),
        )


from datetime import datetime

class EvidenceResponse(BaseModel):
    memory_id: UUID
    tenant_id: str
    user_id: str
    initial_policy_decision: str
    initial_policy_reason: str
    source_kind: str
    source_conversation_id: Optional[str] = None
    source_excerpt: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    audit_trail: List[AuditEvent]


@router.get("/memories/{memory_id}/evidence", response_model=EvidenceResponse)
async def get_evidence(
    memory_id: UUID,
    tenant_id: str = Query(..., min_length=1),
    user_id: str = Query(..., min_length=1),
    service: GovernanceService = Depends(get_governance_service),
):
    trace_id = f"trace-{uuid.uuid4()}"
    try:
        evidence = await service.get_memory_evidence(
            memory_id=memory_id, tenant_id=tenant_id, user_id=user_id
        )
        return evidence
    except GovernanceTargetUnavailableError as e:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=make_error_response("MEMORY_NOT_FOUND", str(e), trace_id),
        )


@router.get("/memories/{memory_id}/audit", response_model=List[AuditEvent])

async def get_audit(
    memory_id: UUID,
    tenant_id: str = Query(..., min_length=1),
    user_id: str = Query(..., min_length=1),
    limit: Optional[int] = Query(None, ge=1),
    service: GovernanceService = Depends(get_governance_service),
):
    trace_id = f"trace-{uuid.uuid4()}"
    try:
        events = await service.get_memory_audit(
            memory_id=memory_id, tenant_id=tenant_id, user_id=user_id, limit=limit
        )
        return events
    except GovernanceTargetUnavailableError as e:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=make_error_response("MEMORY_NOT_FOUND", str(e), trace_id),
        )


@router.patch("/memories/{memory_id}", response_model=MemoryRecord)
async def patch_memory(
    memory_id: UUID,
    request: PatchMemoryRequest,
    service: GovernanceService = Depends(get_governance_service),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
):
    if x_idempotency_key:
        cached = await idempotency_service.get_cached_response(
            x_idempotency_key, request.tenant_id, request.user_id
        )
        if cached:
            status_code, body = cached
            return JSONResponse(status_code=status_code, content=body)

    trace_id = f"trace-{uuid.uuid4()}"
    try:
        updated = await service.patch_memory(
            memory_id=memory_id,
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            content=request.content,
            importance=request.importance,
            confidence=request.confidence,
            status=request.status,
            sensitivity=request.sensitivity,
            source_kind=request.source_kind,
            source_conversation_id=request.source_conversation_id,
            source_excerpt=request.source_excerpt,
            trace_id=trace_id,
        )
        
        encoded = jsonable_encoder(updated)
        if x_idempotency_key:
            await idempotency_service.cache_response(
                x_idempotency_key, request.tenant_id, request.user_id, 200, encoded
            )
        return updated
    except GovernanceTargetUnavailableError as e:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=make_error_response("MEMORY_NOT_FOUND", str(e), trace_id),
        )
    except GovernanceInvalidTransitionError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=make_error_response("INVALID_LIFECYCLE_TRANSITION", str(e), trace_id),
        )
    except GovernanceValidationError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=make_error_response("VALIDATION_ERROR", str(e), trace_id),
        )
    except GovernancePolicyBlockedError as e:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=make_error_response("POLICY_BLOCKED", str(e), trace_id),
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=make_error_response("INTERNAL_ERROR", str(e), trace_id),
        )


@router.delete("/memories/{memory_id}", response_model=DeleteMemoryResponse)
async def delete_memory(
    memory_id: UUID,
    request: DeleteMemoryRequest,
    service: GovernanceService = Depends(get_governance_service),
    x_idempotency_key: Optional[str] = Header(None, alias="X-Idempotency-Key"),
):
    if x_idempotency_key:
        cached = await idempotency_service.get_cached_response(
            x_idempotency_key, request.tenant_id, request.user_id
        )
        if cached:
            status_code, body = cached
            return JSONResponse(status_code=status_code, content=body)

    trace_id = f"trace-{uuid.uuid4()}"
    try:
        deleted = await service.delete_memory(
            memory_id=memory_id,
            tenant_id=request.tenant_id,
            user_id=request.user_id,
            trace_id=trace_id,
        )
        # Format the deleted_at date in ISO format
        deleted_at_str = deleted.deleted_at.isoformat() if deleted.deleted_at else ""
        resp_obj = DeleteMemoryResponse(
            memory_id=deleted.id,
            status=deleted.status,
            deleted_at=deleted_at_str,
        )
        
        encoded = jsonable_encoder(resp_obj)
        if x_idempotency_key:
            await idempotency_service.cache_response(
                x_idempotency_key, request.tenant_id, request.user_id, 200, encoded
            )
        return resp_obj
    except GovernanceTargetUnavailableError as e:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=make_error_response("MEMORY_NOT_FOUND", str(e), trace_id),
        )
    except Exception as e:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=make_error_response("INTERNAL_ERROR", str(e), trace_id),
        )


@router.get("/audit", response_model=List[AuditEvent])
async def list_audit(
    tenant_id: str = Query(..., min_length=1),
    user_id: Optional[str] = Query(None),
    memory_id: Optional[UUID] = Query(None),
    limit: Optional[int] = Query(None, ge=1),
    service: GovernanceService = Depends(get_governance_service),
):
    events = await service.audit_service.list_events(
        tenant_id=tenant_id,
        user_id=user_id,
        memory_id=memory_id,
        limit=limit,
    )
    return events


@router.get("/metrics", response_model=Dict[str, Any])
async def get_metrics(
    tenant_id: str = Query(..., min_length=1),
    service: GovernanceService = Depends(get_governance_service),
):
    metrics = await service.get_metrics(tenant_id=tenant_id)
    return metrics
