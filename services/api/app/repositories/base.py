from abc import ABC, abstractmethod
from uuid import UUID
from typing import List, Optional

from ..domain.models import MemoryRecord
from ..domain.enums import MemoryStatus, MemoryType

class MemoryRepository(ABC):
    @abstractmethod
    async def create(self, record: MemoryRecord) -> MemoryRecord:
        """
        Stores a new governed MemoryRecord.

        Args:
            record: The MemoryRecord to persist.

        Returns:
            The persisted MemoryRecord with generated fields populated.
        """
        pass

    @abstractmethod
    async def get_by_id(
        self, memory_id: UUID, tenant_id: str, user_id: str
    ) -> Optional[MemoryRecord]:
        """
        Retrieves a single memory record by identifier within tenant_id and user_id scope.

        Args:
            memory_id: The UUID of the memory.
            tenant_id: The tenant scope identifier.
            user_id: The user scope identifier.

        Returns:
            The MemoryRecord if found and authorized under scope, otherwise None.
        """
        pass

    @abstractmethod
    async def update(self, record: MemoryRecord) -> MemoryRecord:
        """
        Updates an existing governed MemoryRecord.

        Repository implementations must enforce the following invariants:
        1. Scope Isolation: The update query must match the record by its `id`, `tenant_id`, 
           and `user_id` to prevent cross-tenant/user leakage or unauthorized scope transfer. 
           Scope fields (tenant_id, user_id) are immutable and must never be altered.
        2. Terminal Deletion: If the persisted record already has `status = deleted`, the update 
           must be rejected (e.g., raise ValueError). Deleted memory is terminal and cannot be restored.
        3. Segregation of Deletion: The update call must not transition a record's status to `deleted`. 
           Logical deletion must occur exclusively through the delete() method.
        4. Identity Coordinate Immutability: The update must not alter the record's core mutation coordinate.
           `memory_type` and `identity_slot` are immutable after admission and must match the persisted record exactly.
        5. Admission Provenance Immutability: Immutable admission fields (`initial_policy_decision`, 
           `initial_policy_reason`) must not be updated during mutation and must match the persisted record exactly.

        Args:
            record: The updated MemoryRecord to persist.

        Returns:
            The updated MemoryRecord.

        Raises:
            ValueError: If any database-level lifecycle invariant is violated.
        """
        pass

    @abstractmethod
    async def delete(
        self, memory_id: UUID, tenant_id: str, user_id: str
    ) -> MemoryRecord:
        """
        Logically deletes a memory record by transition to status = deleted.

        The deleted memory remains structurally excluded from context composition
        and default search queries. This operation is idempotent and terminal;
        deleted records must never transition back to an active state.

        Args:
            memory_id: The UUID of the memory.
            tenant_id: The tenant scope identifier.
            user_id: The user scope identifier.

        Returns:
            The updated deleted MemoryRecord.
        """
        pass

    @abstractmethod
    async def list_by_status(
        self, tenant_id: str, user_id: str, status: MemoryStatus
    ) -> List[MemoryRecord]:
        """
        Lists memory records matching the specific status scoped by tenant and user.

        Allows governance control plane processes to read non-active states 
        (e.g., pending review or archived memories) under strict scope isolation.

        Args:
            tenant_id: The tenant scope identifier.
            user_id: The user scope identifier.
            status: The targeted MemoryStatus.

        Returns:
            A list of matching MemoryRecords.
        """
        pass

    @abstractmethod
    async def list_active(
        self, tenant_id: str, user_id: str, limit: int = 100
    ) -> List[MemoryRecord]:
        """
        Lists active memory records for a given user under tenant scope up to a specified limit.

        This method is strictly a bounded write-path lookup helper used by the Policy Broker 
        to locate duplication or conflict candidates for UPDATE_EXISTING and MERGE_WITH_EXISTING decisions.
        It does not perform vector search or keyword query matching (which belong to Phase 2 retrieval), 
        and does not itself guarantee exclusion from future RAG context retrieval (which is owned 
        by Phase 2 retrieval contracts).

        Args:
            tenant_id: The tenant scope identifier.
            user_id: The user scope identifier.
            limit: The maximum number of records to return to prevent unbounded scans.

        Returns:
            A list of active MemoryRecords.
        """
        pass

    @abstractmethod
    async def get_active_by_slot(
        self,
        tenant_id: str,
        user_id: str,
        memory_type: MemoryType,
        identity_slot: str,
    ) -> List[MemoryRecord]:
        """
        Retrieves active memory records occupying the specified identity slot.

        The matching is strictly owner-scoped and active-only, returning only records where:
        - record.tenant_id == tenant_id
        - record.user_id == user_id
        - record.memory_type == memory_type
        - record.identity_slot == identity_slot
        - record.status == MemoryStatus.ACTIVE

        Bounded Results Semantics:
        - len(result) == 0: No active occupant exists (vacant slot).
        - len(result) == 1: Exactly one active occupant was found (current mutation target).
        - len(result) == 2: At least two active occupants exist; two records are sufficient evidence of 
          an anomalous duplicate state for a known SINGLE slot.

        Deterministic Ordering:
        - The results must be ordered by created_at DESC, then id ASC.

        Args:
            tenant_id: The tenant scope identifier.
            user_id: The user scope identifier.
            memory_type: The memory type namespace.
            identity_slot: The canonical slot string.

        Returns:
            A list of active MemoryRecords (length 0, 1, or 2).
        """
        pass

