import math
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field, model_validator, field_validator

from .enums import MemoryType, RetrievalMode
from .models import MemoryRecord


class RetrievalCandidate(BaseModel):
    memory: MemoryRecord = Field(..., description="The underlying governed memory record")
    cosine_similarity: Optional[float] = Field(None, description="Raw cosine similarity score, or None if unavailable")
    matched_query_terms: int = Field(..., ge=0, description="Count of matched normalized query terms")
    total_unique_query_terms: int = Field(..., ge=0, description="Total count of unique query terms")

    @field_validator("cosine_similarity")
    @classmethod
    def validate_cosine_similarity(cls, v: Optional[float]) -> Optional[float]:
        if v is not None:
            if not math.isfinite(v):
                raise ValueError("cosine_similarity must be a finite float")
        return v

    @model_validator(mode="after")
    def validate_terms_ratio(self) -> "RetrievalCandidate":
        if self.matched_query_terms > self.total_unique_query_terms:
            raise ValueError("matched_query_terms cannot exceed total_unique_query_terms")
        return self


class ScoreBreakdown(BaseModel):
    semantic_score: float = Field(..., ge=0.0, le=1.0, description="Normalized semantic similarity score")
    keyword_score: float = Field(..., ge=0.0, le=1.0, description="Normalized keyword overlap score")
    importance_score: float = Field(..., ge=0.0, le=1.0, description="Normalized memory importance score")
    recency_score: float = Field(..., ge=0.0, le=1.0, description="Normalized memory recency score")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Normalized memory extraction confidence score")
    reinforcement_score: float = Field(..., ge=0.0, le=1.0, description="Normalized memory reinforcement score")

    @model_validator(mode="after")
    def validate_finiteness(self) -> "ScoreBreakdown":
        for field_name in [
            "semantic_score",
            "keyword_score",
            "importance_score",
            "recency_score",
            "confidence_score",
            "reinforcement_score"
        ]:
            val = getattr(self, field_name)
            if not math.isfinite(val):
                raise ValueError(f"{field_name} must be a finite float")
        return self


class RankedCandidate(BaseModel):
    memory: MemoryRecord = Field(..., description="The underlying memory record")
    final_score: float = Field(..., ge=0.0, le=1.0, description="Calculated final weighted score")
    score_breakdown: ScoreBreakdown = Field(..., description="Normalized score breakdown of individual signals")
    rank: int = Field(..., ge=1, description="1-indexed rank position")

    @field_validator("final_score")
    @classmethod
    def validate_final_score(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("final_score must be a finite float")
        return v


class UsedMemorySource(BaseModel):
    kind: str = Field(..., min_length=1, description="Origin channel kind")
    excerpt: Optional[str] = Field(None, description="Exact source context excerpt")


class UsedMemory(BaseModel):
    memory_id: UUID = Field(..., description="The ID of the memory record")
    content: str = Field(..., min_length=1, description="The memory content string")
    memory_type: MemoryType = Field(..., description="The type of the memory record")
    score: float = Field(..., ge=0.0, le=1.0, description="The calculated final weighted relevance score")
    reason: str = Field(..., min_length=1, description="Dynamic context selection explanation")
    score_breakdown: ScoreBreakdown = Field(..., description="Detailed normalized score breakdown")
    source: UsedMemorySource = Field(..., description="Source origin information")

    @field_validator("score")
    @classmethod
    def validate_score(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("score must be a finite float")
        return v
