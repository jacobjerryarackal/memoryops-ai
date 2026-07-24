from typing import Optional
from uuid import UUID
from pydantic import BaseModel

from ..domain.models import CandidateMemory, MemoryRecord, PolicyResult, AuditEvent
from ..domain.enums import PolicyDecision, MemoryStatus, AuditEventAction
from ..repositories.base import MemoryRepository
from ..repositories.transactions import TransactionManager
from ..policy.broker import PolicyBroker
from .audit import AuditService


class WriteResult(BaseModel):
    policy_result: PolicyResult
    memory: Optional[MemoryRecord] = None


class WriteServiceError(Exception):
    pass


class TargetUnavailableError(WriteServiceError):
    pass


class InvalidPolicyResultError(WriteServiceError):
    pass


class UnsupportedDecisionError(WriteServiceError):
    pass


class WriteService:
    def __init__(
        self,
        broker: PolicyBroker,
        repository: MemoryRepository,
        audit_service: AuditService,
        transaction_manager: Optional[TransactionManager] = None,
    ) -> None:
        self.broker = broker
        self.repository = repository
        self.audit_service = audit_service
        if transaction_manager is None:
            from ..repositories.postgres import PostgreSQLMemoryRepository
            if isinstance(repository, PostgreSQLMemoryRepository):
                from ..runtime import get_transaction_manager
                transaction_manager = get_transaction_manager()
            else:
                from ..repositories.transactions import TransactionManager
                transaction_manager = TransactionManager(force_in_memory=True)
        self.transaction_manager = transaction_manager

    async def process(self, candidate: CandidateMemory) -> WriteResult:
        async with self.transaction_manager.transaction():
            # 1. Evaluate candidate using the Policy Broker
            policy_result = await self.broker.evaluate(candidate)
            
            # 2. Branch explicitly on each PolicyDecision enum member
            if policy_result.decision == PolicyDecision.SAVE:
                # Create a new active MemoryRecord
                record = MemoryRecord(
                    tenant_id=candidate.tenant_id,
                    user_id=candidate.user_id,
                    content=candidate.content,
                    memory_type=candidate.memory_type,
                    status=MemoryStatus.ACTIVE,
                    sensitivity=candidate.sensitivity,
                    importance=candidate.importance,
                    confidence=candidate.confidence,
                    source_kind=candidate.source_kind,
                    source_conversation_id=candidate.source_conversation_id,
                    source_excerpt=candidate.source_excerpt,
                    initial_policy_decision=PolicyDecision.SAVE,
                    initial_policy_reason=policy_result.reason,
                    identity_slot=candidate.identity_slot,
                    embedding=None
                )
                created = await self.repository.create(record)
                
                # Emit audit log
                audit_event = AuditEvent(
                    tenant_id=candidate.tenant_id,
                    user_id=candidate.user_id,
                    memory_id=created.id,
                    action=AuditEventAction.MEMORY_CREATED,
                    reason=policy_result.reason,
                    metadata={"decision": PolicyDecision.SAVE.value}
                )
                await self.audit_service.record(audit_event)
                
                return WriteResult(policy_result=policy_result, memory=created)
                
            elif policy_result.decision == PolicyDecision.PENDING_APPROVAL:
                # Create a pending MemoryRecord
                record = MemoryRecord(
                    tenant_id=candidate.tenant_id,
                    user_id=candidate.user_id,
                    content=candidate.content,
                    memory_type=candidate.memory_type,
                    status=MemoryStatus.PENDING,
                    sensitivity=candidate.sensitivity,
                    importance=candidate.importance,
                    confidence=candidate.confidence,
                    source_kind=candidate.source_kind,
                    source_conversation_id=candidate.source_conversation_id,
                    source_excerpt=candidate.source_excerpt,
                    initial_policy_decision=PolicyDecision.PENDING_APPROVAL,
                    initial_policy_reason=policy_result.reason,
                    identity_slot=candidate.identity_slot,
                    embedding=None
                )
                created = await self.repository.create(record)
                
                # Emit audit log
                audit_event = AuditEvent(
                    tenant_id=candidate.tenant_id,
                    user_id=candidate.user_id,
                    memory_id=created.id,
                    action=AuditEventAction.MEMORY_PENDING_APPROVAL,
                    reason=policy_result.reason,
                    metadata={"decision": PolicyDecision.PENDING_APPROVAL.value}
                )
                await self.audit_service.record(audit_event)
                
                return WriteResult(policy_result=policy_result, memory=created)
                
            elif policy_result.decision == PolicyDecision.BLOCK:
                # Emit safe audit log with no candidate content
                audit_event = AuditEvent(
                    tenant_id=candidate.tenant_id,
                    user_id=candidate.user_id,
                    memory_id=None,
                    action=AuditEventAction.MEMORY_BLOCKED,
                    reason=policy_result.reason,
                    metadata={"decision": PolicyDecision.BLOCK.value}
                )
                await self.audit_service.record(audit_event)
                
                return WriteResult(policy_result=policy_result, memory=None)
                
            elif policy_result.decision == PolicyDecision.DROP_LOW_UTILITY:
                # Emit audit log
                audit_event = AuditEvent(
                    tenant_id=candidate.tenant_id,
                    user_id=candidate.user_id,
                    memory_id=None,
                    action=AuditEventAction.MEMORY_DROPPED,
                    reason=policy_result.reason,
                    metadata={"decision": PolicyDecision.DROP_LOW_UTILITY.value}
                )
                await self.audit_service.record(audit_event)
                
                return WriteResult(policy_result=policy_result, memory=None)
                
            elif policy_result.decision == PolicyDecision.UPDATE_EXISTING:
                # Validate target_memory_id is present
                if policy_result.target_memory_id is None:
                    raise InvalidPolicyResultError("target_memory_id is required for UPDATE_EXISTING decisions.")
                    
                # Re-fetch target under tenant + user scope
                target = await self.repository.get_by_id(
                    policy_result.target_memory_id,
                    candidate.tenant_id,
                    candidate.user_id
                )
                if target is None:
                    raise TargetUnavailableError("Target memory record does not exist or is out of scope.")
                    
                # Target must be active
                if target.status != MemoryStatus.ACTIVE:
                    raise TargetUnavailableError("Target memory record is not ACTIVE.")
                    
                # Coordinate consistency validation
                if (target.tenant_id != candidate.tenant_id or
                    target.user_id != candidate.user_id or
                    target.memory_type != candidate.memory_type or
                    target.identity_slot != candidate.identity_slot):
                    raise InvalidPolicyResultError("Coordinate mismatch between candidate and target memory.")
                    
                # Perform mutation copy
                updated = target.model_copy(deep=True)
                updated.content = candidate.content
                updated.confidence = candidate.confidence
                updated.importance = candidate.importance
                updated.sensitivity = candidate.sensitivity
                updated.source_kind = candidate.source_kind
                updated.source_conversation_id = candidate.source_conversation_id
                updated.source_excerpt = candidate.source_excerpt
                updated.embedding = None  # Clear derived embedding atomically (ADR-006)
                
                # Persist update
                updated_record = await self.repository.update(updated)
                
                # Emit audit event listing only mutated field names
                changed_fields = [
                    "content", "confidence", "importance", "sensitivity", 
                    "source_kind", "source_conversation_id", "source_excerpt", "embedding"
                ]
                audit_event = AuditEvent(
                    tenant_id=candidate.tenant_id,
                    user_id=candidate.user_id,
                    memory_id=updated_record.id,
                    action=AuditEventAction.MEMORY_UPDATED,
                    reason=policy_result.reason,
                    metadata={
                        "decision": PolicyDecision.UPDATE_EXISTING.value,
                        "changed_fields": changed_fields
                    }
                )
                await self.audit_service.record(audit_event)
                
                return WriteResult(policy_result=policy_result, memory=updated_record)
                
            elif policy_result.decision == PolicyDecision.MERGE_WITH_EXISTING:
                raise UnsupportedDecisionError("MERGE_WITH_EXISTING is not supported in the Phase 1 MVP.")
                
            else:
                raise UnsupportedDecisionError(f"Unhandled policy decision: {policy_result.decision}")
