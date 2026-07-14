import re
from typing import Optional
from ..domain.models import CandidateMemory, PolicyResult
from ..domain.enums import PolicyDecision, Sensitivity
from ..repositories.base import MemoryRepository
from .registry import StaticSlotRegistry, SlotCardinality

class PolicyBroker:
    def __init__(
        self,
        repository: MemoryRepository,
        registry: Optional[StaticSlotRegistry] = None,
    ) -> None:
        self.repository = repository
        self.registry = registry if registry is not None else StaticSlotRegistry()
        
        # Deterministic secret detection patterns:
        self._secret_patterns = [
            # OpenAI / generic API Key format: e.g. sk-xxxx...
            re.compile(r"\bsk-[a-zA-Z0-9-]{20,}\b"),
            # Key-value style credential assignments: e.g. password = "..." or apikey = "..."
            re.compile(
                r"\b(?:api_key|apikey|password|passwd|secret|access_token|bearer_token)\s*[:=]\s*[^\s]{8,}\b",
                re.IGNORECASE
            )
        ]

    async def evaluate(self, candidate: CandidateMemory) -> PolicyResult:
        # 1. Secret and credential detection (BLOCK)
        # Checked first because safety rules have the highest precedence.
        for pattern in self._secret_patterns:
            if pattern.search(candidate.content):
                return PolicyResult(
                    decision=PolicyDecision.BLOCK,
                    reason="Content matched a deterministic secret or credential pattern."
                )
                
        # 2. Sensitivity classification (PENDING_APPROVAL for high-sensitivity)
        if candidate.sensitivity == Sensitivity.HIGH:
            return PolicyResult(
                decision=PolicyDecision.PENDING_APPROVAL,
                reason="Candidate memory has high sensitivity classification and requires review."
            )
            
        # 3. None identity_slot check (SAVE)
        if candidate.identity_slot is None:
            return PolicyResult(
                decision=PolicyDecision.SAVE,
                reason="No mutation coordinate is assigned; candidate is conservatively admitted as a new memory."
            )

        # 4. Registry Gating
        cardinality = self.registry.get_cardinality(candidate.memory_type, candidate.identity_slot)
        if cardinality is None:
            return PolicyResult(
                decision=PolicyDecision.SAVE,
                reason="Candidate identity slot is unregistered; candidate is conservatively admitted as a new memory."
            )

        # 5. Known MULTI-slot behavior
        if cardinality == SlotCardinality.MULTI:
            return PolicyResult(
                decision=PolicyDecision.SAVE,
                reason="Candidate identity slot is registered as multi-valued; candidate is admitted as an additive memory."
            )

        # 6. Known SINGLE-slot active occupancy lookup
        # cardinality == SlotCardinality.SINGLE
        records = await self.repository.get_active_by_slot(
            tenant_id=candidate.tenant_id,
            user_id=candidate.user_id,
            memory_type=candidate.memory_type,
            identity_slot=candidate.identity_slot,
        )

        # 6a. SINGLE with zero active occupants (vacant slot)
        if len(records) == 0:
            return PolicyResult(
                decision=PolicyDecision.SAVE,
                reason="Candidate identity slot is vacant; candidate is admitted as a new memory."
            )

        # 6b. SINGLE with one active occupant (mutation target)
        if len(records) == 1:
            return PolicyResult(
                decision=PolicyDecision.UPDATE_EXISTING,
                reason="Candidate identity slot is occupied; candidate should evolve/replace the slot value.",
                target_memory_id=records[0].id
            )

        # 6c. SINGLE with multiple occupants (anomaly)
        return PolicyResult(
            decision=PolicyDecision.PENDING_APPROVAL,
            reason="Candidate identity slot has anomalous multiple active occupants and requires review."
        )

