import asyncio
import math
from datetime import datetime, timezone
from uuid import UUID
from typing import Dict, List, Optional, Tuple

from ..domain.models import MemoryRecord
from ..domain.enums import MemoryStatus, MemoryType
from .base import MemoryRepository


class InMemoryMemoryRepository(MemoryRepository):
    def __init__(self) -> None:
        self._records: Dict[UUID, MemoryRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self, record: MemoryRecord) -> MemoryRecord:
        async with self._lock:
            if record.id in self._records:
                raise ValueError(f"Duplicate key: Memory record with ID {record.id} already exists.")
            
            # Deep copy to protect the database state from external modification
            copied = record.model_copy(deep=True)
            self._records[record.id] = copied
            
            # Return a deep copy to prevent mutation of stored state by the caller
            return copied.model_copy(deep=True)

    async def get_by_id(
        self, memory_id: UUID, tenant_id: str, user_id: str
    ) -> Optional[MemoryRecord]:
        async with self._lock:
            persisted = self._records.get(memory_id)
            if persisted is None:
                return None
            
            # Verify tenant and user scope isolation
            if persisted.tenant_id != tenant_id or persisted.user_id != user_id:
                return None
                
            return persisted.model_copy(deep=True)

    async def update(self, record: MemoryRecord) -> MemoryRecord:
        async with self._lock:
            persisted = self._records.get(record.id)
            if persisted is None:
                raise ValueError(f"Missing target: Memory record with ID {record.id} does not exist.")
            
            # Verify immutable scope isolation
            if persisted.tenant_id != record.tenant_id or persisted.user_id != record.user_id:
                raise ValueError("Scope mismatch: tenant_id and user_id are immutable and cannot be altered.")
                
            # Verify immutable admission provenance
            if persisted.initial_policy_decision != record.initial_policy_decision or persisted.initial_policy_reason != record.initial_policy_reason:
                raise ValueError("Immutable admission provenance: initial_policy_decision and initial_policy_reason cannot be altered.")
                
            # Verify immutable coordinates (ADR-006)
            if persisted.memory_type != record.memory_type:
                raise ValueError("Core coordinate mismatch: memory_type is immutable and cannot be altered.")
            if persisted.identity_slot != record.identity_slot:
                raise ValueError("Core coordinate mismatch: identity_slot is immutable and cannot be altered.")

            # Verify terminal logical deletion
            if persisted.status == MemoryStatus.DELETED:
                raise ValueError("Terminal deletion: cannot update a logically deleted memory record.")
                
            # Enforce segregation of deletion
            if record.status == MemoryStatus.DELETED:
                raise ValueError("Segregation of deletion: logical deletion must occur via the delete() method.")
                
            copied = record.model_copy(deep=True)
            copied.updated_at = datetime.now(timezone.utc)
            
            self._records[record.id] = copied
            return copied.model_copy(deep=True)

    async def delete(
        self, memory_id: UUID, tenant_id: str, user_id: str
    ) -> MemoryRecord:
        async with self._lock:
            persisted = self._records.get(memory_id)
            if persisted is None:
                raise ValueError(f"Missing target: Memory record with ID {memory_id} does not exist.")
                
            # Verify tenant and user scope isolation
            if persisted.tenant_id != tenant_id or persisted.user_id != user_id:
                raise ValueError("Scope mismatch: unauthorized deletion attempt.")
                
            if persisted.status == MemoryStatus.DELETED:
                return persisted.model_copy(deep=True)
                
            persisted.status = MemoryStatus.DELETED
            persisted.deleted_at = datetime.now(timezone.utc)
            persisted.updated_at = datetime.now(timezone.utc)
            
            return persisted.model_copy(deep=True)

    async def list_by_status(
        self, tenant_id: str, user_id: str, status: MemoryStatus
    ) -> List[MemoryRecord]:
        async with self._lock:
            return [
                r.model_copy(deep=True)
                for r in self._records.values()
                if r.tenant_id == tenant_id and r.user_id == user_id and r.status == status
            ]

    async def list_active(
        self, tenant_id: str, user_id: str, limit: int = 100
    ) -> List[MemoryRecord]:
        if limit <= 0:
            raise ValueError("Limit must be a positive integer greater than zero.")
            
        async with self._lock:
            active_records = [
                r
                for r in self._records.values()
                if r.tenant_id == tenant_id and r.user_id == user_id and r.status == MemoryStatus.ACTIVE
            ]
            
            # Deterministic stable ordering: (created_at DESC, id ASC)
            # Step 1: Sort by ID ascending
            active_records.sort(key=lambda r: r.id)
            # Step 2: Sort by created_at descending (stable sort preserves the ID ordering)
            active_records.sort(key=lambda r: r.created_at, reverse=True)
            
            sliced = active_records[:limit]
            return [r.model_copy(deep=True) for r in sliced]

    async def get_active_by_slot(
        self,
        tenant_id: str,
        user_id: str,
        memory_type: MemoryType,
        identity_slot: str,
    ) -> List[MemoryRecord]:
        async with self._lock:
            matching = [
                r
                for r in self._records.values()
                if (r.tenant_id == tenant_id and
                    r.user_id == user_id and
                    r.memory_type == memory_type and
                    r.identity_slot == identity_slot and
                    r.status == MemoryStatus.ACTIVE)
            ]
            
            # Stable deterministic sort: created_at DESC, then id ASC
            matching.sort(key=lambda r: r.id)
            matching.sort(key=lambda r: r.created_at, reverse=True)
            
            sliced = matching[:2]
            return [r.model_copy(deep=True) for r in sliced]

    async def search_candidates(
        self,
        tenant_id: str,
        user_id: str,
        query_embedding: Optional[List[float]],
        limit: int = 50,
    ) -> List[Tuple[MemoryRecord, Optional[float]]]:
        if limit < 1:
            raise ValueError("limit must be >= 1")

        if query_embedding is not None and len(query_embedding) != 1536:
            raise ValueError("query_embedding must be exactly 1536 dimensions")

        async with self._lock:
            active_records = [
                r
                for r in self._records.values()
                if r.tenant_id == tenant_id and r.user_id == user_id and r.status == MemoryStatus.ACTIVE
            ]

            if query_embedding is None:
                # Deterministic stable ordering: created_at DESC, then id ASC
                active_records.sort(key=lambda r: r.id)
                active_records.sort(key=lambda r: r.created_at, reverse=True)

                sliced = active_records[:limit]
                return [(r.model_copy(deep=True), None) for r in sliced]

            # Otherwise calculate similarity
            candidates_with_sim = []
            for r in active_records:
                if r.embedding is None:
                    continue

                # Cosine similarity calculation
                dot = sum(a * b for a, b in zip(query_embedding, r.embedding))
                norm_u = math.sqrt(sum(a * a for a in query_embedding))
                norm_v = math.sqrt(sum(a * a for a in r.embedding))
                sim = dot / (norm_u * norm_v) if (norm_u > 0.0 and norm_v > 0.0) else 0.0
                candidates_with_sim.append((r, sim))

            # Deterministic sorting:
            # Primary: similarity DESC
            # Secondary: created_at DESC
            # Tertiary: id ASC
            # We perform stable sorts from least significant key to most significant key:
            # 1. ID ASC
            candidates_with_sim.sort(key=lambda x: x[0].id)
            # 2. created_at DESC
            candidates_with_sim.sort(key=lambda x: x[0].created_at, reverse=True)
            # 3. similarity DESC
            candidates_with_sim.sort(key=lambda x: x[1], reverse=True)

            sliced = candidates_with_sim[:limit]
            return [(r.model_copy(deep=True), sim) for r, sim in sliced]
