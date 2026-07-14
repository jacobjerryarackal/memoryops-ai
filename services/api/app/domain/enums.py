from enum import Enum

class MemoryType(str, Enum):
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    EPISODIC = "episodic"


class MemoryStatus(str, Enum):
    ACTIVE = "active"
    PENDING = "pending"
    REJECTED = "rejected"
    ARCHIVED = "archived"
    DELETED = "deleted"


class Sensitivity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PolicyDecision(str, Enum):
    SAVE = "SAVE"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    BLOCK = "BLOCK"
    DROP_LOW_UTILITY = "DROP_LOW_UTILITY"
    UPDATE_EXISTING = "UPDATE_EXISTING"
    MERGE_WITH_EXISTING = "MERGE_WITH_EXISTING"


class AuditEventAction(str, Enum):
    MEMORY_CREATED = "memory_created"
    MEMORY_PENDING_APPROVAL = "memory_pending_approval"
    MEMORY_BLOCKED = "memory_blocked"
    MEMORY_DROPPED = "memory_dropped"
    MEMORY_UPDATED = "memory_updated"
    MEMORY_MERGED = "memory_merged"
    MEMORY_APPROVED = "memory_approved"
    MEMORY_REJECTED = "memory_rejected"
    MEMORY_ARCHIVED = "memory_archived"
    MEMORY_DELETED = "memory_deleted"


class RetrievalMode(str, Enum):
    HYBRID = "hybrid"
    FALLBACK = "fallback"
    NONE = "none"

