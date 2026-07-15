import math
from typing import List, Set, Any
from app.services.retrieval import normalize_text


def calculate_lexical_token_overlap(query: str, content: str) -> float:
    """
    Diagnostic lexical token-overlap helper.
    Computes the Jaccard similarity coefficient between normalized tokens
    of query and content.
    
    This is NOT a semantic relevance metric or primary retrieval quality metric.
    
    Jaccard = |Q ∩ M| / |Q ∪ M|
    """
    if not query or not content:
        return 0.0

    query_tokens = set(normalize_text(query))
    content_tokens = set(normalize_text(content))

    if not query_tokens or not content_tokens:
        return 0.0

    intersection = query_tokens.intersection(content_tokens)
    union = query_tokens.union(content_tokens)

    return len(intersection) / len(union)


def calculate_precision_at_k(expected: List[str], retrieved: List[str], k: int = 10) -> float:
    """
    Calculates the Precision@K of the retrieved contents against the expected list.
    Precision@K = (Number of relevant retrieved items in top K) / min(len(retrieved), K)
    
    If expected is empty:
      - returns 1.0 if retrieved is empty
      - returns 0.0 if retrieved has items
    """
    if not expected:
        return 1.0 if not retrieved else 0.0

    limit = min(len(retrieved), k)
    if limit == 0:
        return 0.0

    expected_set = set(expected)
    relevant_retrieved = sum(1 for item in retrieved[:limit] if item in expected_set)
    return relevant_retrieved / limit


def calculate_recall_at_k(expected: List[str], retrieved: List[str], k: int = 10) -> float:
    """
    Calculates the Recall@K of the retrieved contents against the expected list.
    Recall@K = (Number of relevant retrieved items in top K) / len(expected)
    
    If expected is empty:
      - returns 1.0 if retrieved is empty
      - returns 0.0 if retrieved has items
    """
    if not expected:
        return 1.0 if not retrieved else 0.0

    limit = min(len(retrieved), k)
    if limit == 0:
        return 0.0

    expected_set = set(expected)
    relevant_retrieved = sum(1 for item in retrieved[:limit] if item in expected_set)
    return relevant_retrieved / len(expected)


def calculate_reciprocal_rank(expected: List[str], retrieved: List[str], k: int = 10) -> float:
    """
    Calculates the Reciprocal Rank of the first relevant retrieved item in the top K.
    RR = 1 / rank of the first relevant retrieved item (1-indexed).
    If no relevant item is retrieved in the top K, returns 0.0.
    
    If expected is empty:
      - returns 1.0 if retrieved is empty
      - returns 0.0 if retrieved has items
    """
    if not expected:
        return 1.0 if not retrieved else 0.0

    limit = min(len(retrieved), k)
    expected_set = set(expected)

    for i in range(limit):
        if retrieved[i] in expected_set:
            return 1.0 / (i + 1)

    return 0.0


def calculate_average_precision(expected: List[str], retrieved: List[str], k: int = 10) -> float:
    """
    Calculates the Average Precision@K of the retrieved contents against the expected list.
    Evaluates ranking order quality of retrieved items.
    
    Average Precision@K = [ Sum_{i=1..K} (P@i * relevance(i)) ] / min(len(expected), K)
    where P@i = (relevant items retrieved up to i) / i
    and relevance(i) = 1 if retrieved[i-1] in expected, else 0.
    
    If expected is empty:
      - returns 1.0 if retrieved is empty
      - returns 0.0 if retrieved has items
    """
    if not expected:
        return 1.0 if not retrieved else 0.0

    limit = min(len(retrieved), k)
    if limit == 0:
        return 0.0

    expected_set = set(expected)
    relevant_retrieved_count = 0
    precision_sum = 0.0

    for i in range(1, limit + 1):
        item = retrieved[i - 1]
        if item in expected_set:
            relevant_retrieved_count += 1
            precision_at_i = relevant_retrieved_count / i
            precision_sum += precision_at_i

    denominator = min(len(expected), k)
    if denominator == 0:
        return 0.0

    return precision_sum / denominator


def calculate_tenant_leakage(retrieved_memories: List[Any], expected_tenant_id: str) -> int:
    """
    Counts how many retrieved memories do not match the expected tenant_id.
    """
    leakage = 0
    for mem in retrieved_memories:
        if hasattr(mem, "tenant_id"):
            tid = mem.tenant_id
        elif hasattr(mem, "memory"):
            tid = mem.memory.tenant_id
        elif isinstance(mem, dict):
            tid = mem.get("tenant_id")
        else:
            continue
        if tid != expected_tenant_id:
            leakage += 1
    return leakage


def calculate_user_leakage(retrieved_memories: List[Any], expected_user_id: str) -> int:
    """
    Counts how many retrieved memories do not match the expected user_id.
    """
    leakage = 0
    for mem in retrieved_memories:
        if hasattr(mem, "user_id"):
            uid = mem.user_id
        elif hasattr(mem, "memory"):
            uid = mem.memory.user_id
        elif isinstance(mem, dict):
            uid = mem.get("user_id")
        else:
            continue
        if uid != expected_user_id:
            leakage += 1
    return leakage


def calculate_inactive_leakage(retrieved_memories: List[Any]) -> int:
    """
    Counts how many retrieved memories have status PENDING, REJECTED, or ARCHIVED.
    """
    from app.domain.enums import MemoryStatus
    leakage = 0
    for mem in retrieved_memories:
        if hasattr(mem, "status"):
            status = mem.status
        elif hasattr(mem, "memory"):
            status = mem.memory.status
        elif isinstance(mem, dict):
            status = mem.get("status")
        else:
            continue
        
        if status in (MemoryStatus.PENDING, MemoryStatus.REJECTED, MemoryStatus.ARCHIVED) or status in ("pending", "rejected", "archived"):
            leakage += 1
    return leakage


def calculate_deleted_leakage(retrieved_memories: List[Any]) -> int:
    """
    Counts how many retrieved memories have status DELETED.
    """
    from app.domain.enums import MemoryStatus
    leakage = 0
    for mem in retrieved_memories:
        if hasattr(mem, "status"):
            status = mem.status
        elif hasattr(mem, "memory"):
            status = mem.memory.status
        elif isinstance(mem, dict):
            status = mem.get("status")
        else:
            continue
        
        if status == MemoryStatus.DELETED or status == "deleted":
            leakage += 1
    return leakage


def check_budget_compliance(
    retrieved_memories: List[Any],
    max_memories: int = 10,
    max_characters: int = 4000,
) -> bool:
    """
    Verifies that the retrieved context conforms to count and character bounds.
    """
    if len(retrieved_memories) > max_memories:
        return False

    total_chars = 0
    for mem in retrieved_memories:
        if hasattr(mem, "content"):
            content = mem.content
        elif hasattr(mem, "memory"):
            content = mem.memory.content
        elif isinstance(mem, dict):
            content = mem.get("content", "")
        else:
            content = str(mem)

        total_chars += len(content)

    return total_chars <= max_characters
