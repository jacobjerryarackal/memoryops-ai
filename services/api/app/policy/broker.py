import re
from typing import Optional
from ..domain.models import CandidateMemory, PolicyResult
from ..domain.enums import PolicyDecision, Sensitivity
from ..repositories.base import MemoryRepository

class PolicyBroker:
    def __init__(self, repository: Optional[MemoryRepository] = None) -> None:
        self.repository = repository
        
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
            
        # 3. Utility checks (DROP_LOW_UTILITY if importance < 3 or confidence < 0.5)
        if candidate.importance < 3:
            return PolicyResult(
                decision=PolicyDecision.DROP_LOW_UTILITY,
                reason=f"Candidate importance score ({candidate.importance}) is below the utility threshold of 3."
            )
            
        if candidate.confidence < 0.5:
            return PolicyResult(
                decision=PolicyDecision.DROP_LOW_UTILITY,
                reason=f"Candidate extraction confidence ({candidate.confidence}) is below the utility threshold of 0.5."
            )
            
        # 4. SAVE fallback
        return PolicyResult(
            decision=PolicyDecision.SAVE,
            reason="Candidate memory passed all deterministic policy checks."
        )
