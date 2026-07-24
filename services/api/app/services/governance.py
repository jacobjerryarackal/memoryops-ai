from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from ..domain.enums import (
    AuditEventAction,
    MemoryStatus,
    MemoryType,
    PolicyDecision,
    Sensitivity,
)
from ..domain.models import AuditEvent, CandidateMemory, MemoryRecord
from ..policy.broker import PolicyBroker
from ..policy.registry import SlotCardinality
from ..repositories.base import MemoryRepository
from ..repositories.transactions import TransactionManager
from .audit import AuditService


class GovernanceError(Exception):
    pass


class GovernanceTargetUnavailableError(GovernanceError):
    pass


class GovernanceInvalidTransitionError(GovernanceError):
    pass


class GovernanceValidationError(GovernanceError):
    pass


class GovernancePolicyBlockedError(GovernanceError):
    pass


class GovernanceService:
    def __init__(
        self,
        repository: MemoryRepository,
        audit_service: AuditService,
        broker: PolicyBroker,
        transaction_manager: Optional[TransactionManager] = None,
    ) -> None:
        self.repository = repository
        self.audit_service = audit_service
        self.broker = broker
        if transaction_manager is None:
            from ..repositories.postgres import PostgreSQLMemoryRepository
            if isinstance(repository, PostgreSQLMemoryRepository):
                from ..runtime import get_transaction_manager
                transaction_manager = get_transaction_manager()
            else:
                from ..repositories.transactions import TransactionManager
                transaction_manager = TransactionManager(force_in_memory=True)
        self.transaction_manager = transaction_manager

    async def list_memories(
        self,
        tenant_id: str,
        user_id: str,
        status: Optional[MemoryStatus] = None,
        memory_type: Optional[MemoryType] = None,
    ) -> List[MemoryRecord]:
        """
        Lists memories scoped by tenant and user, with optional filters.
        Deleted memories are excluded by default if status is not explicitly requested.
        """
        if status is not None:
            records = await self.repository.list_by_status(tenant_id, user_id, status)
        else:
            # Default behavior: exclude DELETED. Gather active, pending, rejected, archived.
            records = []
            for s in [
                MemoryStatus.ACTIVE,
                MemoryStatus.PENDING,
                MemoryStatus.REJECTED,
                MemoryStatus.ARCHIVED,
            ]:
                records.extend(await self.repository.list_by_status(tenant_id, user_id, s))

        # Filter by memory type if provided
        if memory_type is not None:
            records = [r for r in records if r.memory_type == memory_type]

        # Deterministic stable ordering: created_at DESC, then id ASC
        records.sort(key=lambda r: r.id)
        records.sort(key=lambda r: r.created_at, reverse=True)

        return records

    async def get_memory_by_id(
        self, memory_id: UUID, tenant_id: str, user_id: str
    ) -> MemoryRecord:
        """
        Retrieves a single memory record by ID under tenant/user scope.
        Excludes DELETED records.
        """
        record = await self.repository.get_by_id(memory_id, tenant_id, user_id)
        if record is None or record.status == MemoryStatus.DELETED:
            raise GovernanceTargetUnavailableError(
                "Memory was not found within the requested scope."
            )
        return record

    async def get_memory_provenance(
        self, memory_id: UUID, tenant_id: str, user_id: str
    ) -> Dict[str, Any]:
        """
        Retrieves memory record provenance details and audit event IDs.
        """
        record = await self.get_memory_by_id(memory_id, tenant_id, user_id)
        events = await self.audit_service.list_events(
            tenant_id=tenant_id, user_id=user_id, memory_id=memory_id
        )
        # Stable sort: created_at DESC, then id ASC
        events.sort(key=lambda e: e.id)
        events.sort(key=lambda e: e.created_at, reverse=True)

        return {
            "memory_id": record.id,
            "source_kind": record.source_kind,
            "source_conversation_id": record.source_conversation_id,
            "source_excerpt": record.source_excerpt,
            "initial_policy_decision": record.initial_policy_decision,
            "initial_policy_reason": record.initial_policy_reason,
            "status": record.status,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
            "archived_at": record.archived_at,
            "deleted_at": record.deleted_at,
            "reinforcement_count": record.reinforcement_count,
            "importance": record.importance,
            "confidence": record.confidence,
            "audit_event_ids": [str(e.id) for e in events],
        }

    async def get_memory_audit(
        self, memory_id: UUID, tenant_id: str, user_id: str, limit: Optional[int] = None
    ) -> List[AuditEvent]:
        """
        Retrieves the audit timeline for one memory record.
        """
        # Ensure the record exists and is not deleted
        await self.get_memory_by_id(memory_id, tenant_id, user_id)
        return await self.audit_service.list_events(
            tenant_id=tenant_id, user_id=user_id, memory_id=memory_id, limit=limit
        )

    async def get_metrics(self, tenant_id: str) -> Dict[str, Any]:
        """
        Returns tenant-scoped business and governance metrics.
        """
        # Read from repo using back-channel for InMemoryMemoryRepository
        records = []
        if hasattr(self.repository, "_records"):
            records = [
                r
                for r in self.repository._records.values()
                if r.tenant_id == tenant_id
            ]

        by_status = {
            "active": 0,
            "pending": 0,
            "rejected": 0,
            "archived": 0,
            "deleted": 0,
        }
        for r in records:
            status_val = r.status.value
            if status_val in by_status:
                by_status[status_val] += 1

        events = await self.audit_service.list_events(tenant_id=tenant_id)
        by_action = {
            "memory_created": 0,
            "memory_deleted": 0,
            "memory_approved": 0,
        }
        for e in events:
            action_val = e.action.value
            if action_val in by_action:
                by_action[action_val] += 1

        return {
            "total_memories": len(records),
            "by_status": by_status,
            "audit_events": len(events),
            "by_action": by_action,
        }

    async def patch_memory(
        self,
        memory_id: UUID,
        tenant_id: str,
        user_id: str,
        content: Optional[str] = None,
        importance: Optional[int] = None,
        confidence: Optional[float] = None,
        status: Optional[MemoryStatus] = None,
        sensitivity: Optional[Sensitivity] = None,
        source_kind: Optional[str] = None,
        source_conversation_id: Optional[str] = None,
        source_excerpt: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> MemoryRecord:
        """
        Performs a manual governed memory update or lifecycle transition.
        Enforces coordinate immutability and content-safety gating.
        """
        async with self.transaction_manager.transaction():
            existing = await self.repository.get_by_id(memory_id, tenant_id, user_id)
            if existing is None or existing.status == MemoryStatus.DELETED:
                raise GovernanceTargetUnavailableError(
                    "Memory was not found within the requested scope."
                )

            primary_action = AuditEventAction.MEMORY_UPDATED
            updated_status = existing.status

            # 1. Validate status transition
            if status is not None and status != existing.status:
                allowed = False
                if existing.status == MemoryStatus.PENDING:
                    if status == MemoryStatus.ACTIVE:
                        allowed = True
                        primary_action = AuditEventAction.MEMORY_APPROVED
                    elif status == MemoryStatus.REJECTED:
                        allowed = True
                        primary_action = AuditEventAction.MEMORY_REJECTED
                elif existing.status == MemoryStatus.ACTIVE:
                    if status == MemoryStatus.ARCHIVED:
                        allowed = True
                        primary_action = AuditEventAction.MEMORY_ARCHIVED
                elif existing.status == MemoryStatus.ARCHIVED:
                    if status == MemoryStatus.ACTIVE:
                        allowed = True
                        primary_action = AuditEventAction.MEMORY_APPROVED

                if not allowed:
                    raise GovernanceInvalidTransitionError(
                        f"Invalid lifecycle transition from {existing.status.value} to {status.value}."
                    )
                
                # Single-valued slot approval-time revalidation (ADR-006)
                if existing.status == MemoryStatus.PENDING and status == MemoryStatus.ACTIVE and existing.identity_slot is not None:
                    cardinality = self.broker.registry.get_cardinality(existing.memory_type, existing.identity_slot)
                    if cardinality == SlotCardinality.SINGLE:
                        active_occupants = await self.repository.get_active_by_slot(
                            tenant_id=tenant_id,
                            user_id=user_id,
                            memory_type=existing.memory_type,
                            identity_slot=existing.identity_slot,
                        )
                        if len(active_occupants) > 0:
                            raise GovernanceValidationError(
                                f"Slot '{existing.identity_slot}' is registered as SINGLE and is already occupied by active record '{active_occupants[0].id}'."
                            )
                
                updated_status = status

            # 2. Safety Broker gating on content change (INV-004, ADR-003)
            updated_content = existing.content
            embedding_to_set = existing.embedding
            if content is not None and content != existing.content:
                candidate = CandidateMemory(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    content=content,
                    memory_type=existing.memory_type,
                    confidence=confidence if confidence is not None else existing.confidence,
                    importance=importance if importance is not None else existing.importance,
                    sensitivity=sensitivity if sensitivity is not None else existing.sensitivity,
                    source_kind=source_kind if source_kind is not None else existing.source_kind,
                    source_conversation_id=source_conversation_id if source_conversation_id is not None else existing.source_conversation_id,
                    source_excerpt=source_excerpt if source_excerpt is not None else existing.source_excerpt,
                    identity_slot=existing.identity_slot,
                )
                policy_result = await self.broker.evaluate(candidate)
                if policy_result.decision == PolicyDecision.BLOCK:
                    raise GovernancePolicyBlockedError(policy_result.reason)
                elif policy_result.decision == PolicyDecision.PENDING_APPROVAL:
                    # If content safety forces PENDING_APPROVAL, route status back to pending
                    updated_status = MemoryStatus.PENDING
                    primary_action = AuditEventAction.MEMORY_PENDING_APPROVAL

                updated_content = content
                # Clear embedding derived-state atomically on content update (INV-006)
                embedding_to_set = None

            # 3. Apply updates
            updated_record = existing.model_copy(deep=True)
            updated_record.content = updated_content
            updated_record.status = updated_status
            updated_record.embedding = embedding_to_set

            if importance is not None:
                updated_record.importance = importance
            if confidence is not None:
                updated_record.confidence = confidence
            if sensitivity is not None:
                updated_record.sensitivity = sensitivity
            if source_kind is not None:
                updated_record.source_kind = source_kind
            if source_conversation_id is not None:
                updated_record.source_conversation_id = source_conversation_id
            if source_excerpt is not None:
                updated_record.source_excerpt = source_excerpt

            now = datetime.now(timezone.utc)
            if updated_status == MemoryStatus.ARCHIVED and existing.status != MemoryStatus.ARCHIVED:
                updated_record.archived_at = now
            elif updated_status == MemoryStatus.ACTIVE:
                updated_record.archived_at = None

            saved = await self.repository.update(updated_record)

            # 4. Record Audit Trail (INV-008 / Phase 15)
            audit_event = AuditEvent(
                tenant_id=tenant_id,
                user_id=user_id,
                memory_id=saved.id,
                action=primary_action,
                reason="Manual governance mutation via PATCH.",
                metadata={
                    "previous_status": existing.status.value,
                    "new_status": saved.status.value,
                    "content_changed": content is not None and content != existing.content,
                },
                trace_id=trace_id,
            )
            await self.audit_service.record(audit_event)

            return saved

    async def delete_memory(
        self,
        memory_id: UUID,
        tenant_id: str,
        user_id: str,
        trace_id: Optional[str] = None,
    ) -> MemoryRecord:
        """
        Logically deletes a memory record by transition to status = deleted.
        Idempotent: if already deleted, returns the existing record without generating audit events.
        """
        async with self.transaction_manager.transaction():
            existing = await self.repository.get_by_id(memory_id, tenant_id, user_id)
            if existing is None:
                raise GovernanceTargetUnavailableError(
                    "Memory was not found within the requested scope."
                )

            if existing.status == MemoryStatus.DELETED:
                return existing

            # Mark deleted
            deleted = await self.repository.delete(memory_id, tenant_id, user_id)

            # Emit audit trail
            audit_event = AuditEvent(
                tenant_id=tenant_id,
                user_id=user_id,
                memory_id=deleted.id,
                action=AuditEventAction.MEMORY_DELETED,
                reason="Logical deletion via DELETE.",
                metadata={
                    "previous_status": existing.status.value,
                    "new_status": deleted.status.value,
                },
                trace_id=trace_id,
            )
            await self.audit_service.record(audit_event)

            return deleted
