import asyncio
from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID

from ..domain.models import AuditEvent

class AuditService(ABC):
    @abstractmethod
    async def record(self, event: AuditEvent) -> AuditEvent:
        """
        Appends a pre-validated AuditEvent to the append-only governance log.
        Raises ValueError if the event ID is a duplicate.
        """
        pass

    @abstractmethod
    async def list_events(
        self,
        tenant_id: str,
        user_id: Optional[str] = None,
        memory_id: Optional[UUID] = None,
        limit: Optional[int] = None,
    ) -> List[AuditEvent]:
        """
        Retrieves a filtered timeline of audit events scoped to a tenant.
        Allows optional user_id and memory_id filtering.
        Returns a list ordered by created_at DESC, then id ASC.
        """
        pass

class InMemoryAuditService(AuditService):
    def __init__(self) -> None:
        self._events: dict[UUID, AuditEvent] = {}
        self._lock = asyncio.Lock()

    async def record(self, event: AuditEvent) -> AuditEvent:
        async with self._lock:
            if event.id in self._events:
                raise ValueError(f"Duplicate audit event ID: {event.id} already exists.")
            
            copied = event.model_copy(deep=True)
            self._events[event.id] = copied
            return copied.model_copy(deep=True)

    async def list_events(
        self,
        tenant_id: str,
        user_id: Optional[str] = None,
        memory_id: Optional[UUID] = None,
        limit: Optional[int] = None,
    ) -> List[AuditEvent]:
        if limit is not None and limit <= 0:
            raise ValueError("Limit must be a positive integer greater than zero.")
            
        async with self._lock:
            filtered = [
                e
                for e in self._events.values()
                if (
                    e.tenant_id == tenant_id
                    and (user_id is None or e.user_id == user_id)
                    and (memory_id is None or e.memory_id == memory_id)
                )
            ]
            
            # Stable deterministic sort: created_at DESC, then id ASC
            # Step 1: Sort by ID ascending
            filtered.sort(key=lambda e: e.id)
            # Step 2: Sort by created_at descending (stable sort preserves the ID ordering)
            filtered.sort(key=lambda e: e.created_at, reverse=True)
            
            sliced = filtered[:limit] if limit is not None else filtered
            return [e.model_copy(deep=True) for e in sliced]
