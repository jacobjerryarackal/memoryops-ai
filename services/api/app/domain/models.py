from datetime import datetime, timezone
from uuid import UUID, uuid4
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator

from .enums import MemoryType, MemoryStatus, Sensitivity, PolicyDecision, AuditEventAction

class CandidateMemory(BaseModel):
    tenant_id: str = Field(..., min_length=1, description="Tenant scope identifier")
    user_id: str = Field(..., min_length=1, description="User scope identifier")
    content: str = Field(..., min_length=1, description="Proposed memory content")
    memory_type: MemoryType = Field(..., description="Type of memory")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence probability")
    importance: int = Field(..., ge=0, le=10, description="Estimated long-term importance")
    sensitivity: Sensitivity = Field(..., description="Sensitivity classification")
    source_kind: str = Field("chat", description="Origin channel kind")
    source_conversation_id: Optional[str] = Field(None, description="Source conversation identifier")
    source_excerpt: Optional[str] = Field(None, description="Exact source context excerpt")


class PolicyResult(BaseModel):
    decision: PolicyDecision = Field(..., description="Broker disposition decision")
    reason: str = Field(..., min_length=1, description="Human-readable reason for the decision")
    target_memory_id: Optional[UUID] = Field(None, description="Affected target memory for update or merge")

    @model_validator(mode="after")
    def validate_target_memory(self) -> "PolicyResult":
        if self.decision in (PolicyDecision.UPDATE_EXISTING, PolicyDecision.MERGE_WITH_EXISTING) and self.target_memory_id is None:
            raise ValueError(f"target_memory_id is required when decision is '{self.decision}'")
        return self


class MemoryRecord(BaseModel):
    id: UUID = Field(default_factory=uuid4, description="Primary key UUID")
    tenant_id: str = Field(..., min_length=1, description="Tenant scope identifier")
    user_id: str = Field(..., min_length=1, description="User scope identifier")
    content: str = Field(..., min_length=1, description="Persisted memory content")
    memory_type: MemoryType = Field(..., description="Type of memory")
    status: MemoryStatus = Field(MemoryStatus.ACTIVE, description="Lifecycle status")
    sensitivity: Sensitivity = Field(Sensitivity.LOW, description="Sensitivity level")
    importance: int = Field(5, ge=0, le=10, description="Durable importance score")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Extraction confidence")
    reinforcement_count: int = Field(0, ge=0, description="Reinforcement counter")
    embedding: Optional[List[float]] = Field(None, description="1536-dimensional vector embedding")
    source_kind: str = Field("chat", description="Source origin channel")
    source_conversation_id: Optional[str] = Field(None, description="Source conversation identifier")
    source_excerpt: Optional[str] = Field(None, description="Exact source excerpt")
    initial_policy_decision: PolicyDecision = Field(..., description="Immutable admission policy decision")
    initial_policy_reason: str = Field(..., min_length=1, description="Immutable admission policy reason")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Record creation timestamp")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Record update timestamp")
    archived_at: Optional[datetime] = Field(None, description="Archival timestamp")
    deleted_at: Optional[datetime] = Field(None, description="Logical deletion timestamp")

    @field_validator("embedding")
    @classmethod
    def validate_embedding_dimensions(cls, v: Optional[List[float]]) -> Optional[List[float]]:
        if v is not None and len(v) != 1536:
            raise ValueError("Embedding must be exactly 1536 dimensions")
        return v

    @model_validator(mode="after")
    def validate_lifecycle_timestamps(self) -> "MemoryRecord":
        if self.status == MemoryStatus.DELETED and self.deleted_at is None:
            raise ValueError("deleted_at timestamp is required when status is 'deleted'")
        if self.status == MemoryStatus.ARCHIVED and self.archived_at is None:
            raise ValueError("archived_at timestamp is required when status is 'archived'")
        return self


class AuditEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4, description="Unique audit event identifier")
    tenant_id: str = Field(..., min_length=1, description="Tenant scope")
    user_id: Optional[str] = Field(None, description="User scope")
    memory_id: Optional[UUID] = Field(None, description="Affected memory identifier")
    action: AuditEventAction = Field(..., description="Governance action executed")
    reason: Optional[str] = Field(None, description="Context explanation")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Audit event metadata payload")
    trace_id: Optional[str] = Field(None, description="Correlated trace identifier")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Event timestamp")
