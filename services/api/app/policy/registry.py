from enum import Enum
from typing import Dict, Optional, Tuple
from ..domain.enums import MemoryType

class SlotCardinality(Enum):
    SINGLE = "SINGLE"
    MULTI = "MULTI"

class StaticSlotRegistry:
    def __init__(self) -> None:
        # Bounded static initial vocabulary mappings: (MemoryType, identity_slot) -> SlotCardinality
        self._registry: Dict[Tuple[MemoryType, str], SlotCardinality] = {
            # Semantic slots
            (MemoryType.SEMANTIC, "profession"): SlotCardinality.SINGLE,
            (MemoryType.SEMANTIC, "residence"): SlotCardinality.SINGLE,
            (MemoryType.SEMANTIC, "technology_stack"): SlotCardinality.MULTI,
            (MemoryType.SEMANTIC, "project_built"): SlotCardinality.MULTI,
            # Procedural slots
            (MemoryType.PROCEDURAL, "explanation_style"): SlotCardinality.SINGLE,
            (MemoryType.PROCEDURAL, "formatting_hashtags"): SlotCardinality.SINGLE,
            (MemoryType.PROCEDURAL, "formatting_hyphens"): SlotCardinality.SINGLE,
            # Episodic slots remain completely unregistered
        }

    def get_cardinality(
        self,
        memory_type: MemoryType,
        identity_slot: str,
    ) -> Optional[SlotCardinality]:
        """
        Retrieves the cardinality setting of a registered slot coordinate.
        Returns None if the slot coordinate is unregistered.
        """
        return self._registry.get((memory_type, identity_slot))
