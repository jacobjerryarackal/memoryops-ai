import math
import unicodedata
from datetime import datetime, timezone
from typing import List, Optional

from ..domain.enums import RetrievalMode
from ..domain.models import MemoryRecord
from ..domain.retrieval import RetrievalCandidate, ScoreBreakdown, RankedCandidate
from ..repositories.base import MemoryRepository


def normalize_text(text: str) -> List[str]:
    """
    Normalizes raw text according to the locked lexical sequence:
    1. Unicode NFKC normalization
    2. Lowercase using .lower()
    3. Replace non-alphanumeric characters with space (Unicode-aware)
    4. Split by whitespace and filter out empty tokens.
    """
    nfkc_norm = unicodedata.normalize("NFKC", text)
    lowercased = nfkc_norm.lower()
    
    # Unicode-aware replacement of non-alphanumeric characters
    cleaned_chars = [c if c.isalnum() else " " for c in lowercased]
    cleaned_text = "".join(cleaned_chars)
    
    # Split automatically removes consecutive spaces and empty tokens
    return [t for t in cleaned_text.split() if t]


class Retriever:
    def __init__(self, repository: MemoryRepository) -> None:
        self.repository = repository

    async def retrieve(
        self,
        tenant_id: str,
        user_id: str,
        query_text: str,
        query_embedding: Optional[List[float]],
        candidate_limit: int = 50,
    ) -> List[RetrievalCandidate]:
        # Delegate to repository to get scoped active candidate records
        repo_results = await self.repository.search_candidates(
            tenant_id=tenant_id,
            user_id=user_id,
            query_embedding=query_embedding,
            limit=candidate_limit,
        )

        if not repo_results:
            return []

        # Lexical normalization of incoming query
        normalized_query_tokens = normalize_text(query_text)
        unique_query_terms = set(normalized_query_tokens)
        total_unique_query_terms = len(unique_query_terms)

        candidates = []
        for record, raw_similarity in repo_results:
            # Lexical normalization of memory content
            normalized_mem_tokens = normalize_text(record.content)
            memory_terms = set(normalized_mem_tokens)

            matched_query_terms = len(unique_query_terms.intersection(memory_terms))

            # Construct RetrievalCandidate (None similarity is preserved exactly)
            candidates.append(
                RetrievalCandidate(
                    memory=record,
                    cosine_similarity=raw_similarity,
                    matched_query_terms=matched_query_terms,
                    total_unique_query_terms=total_unique_query_terms,
                )
            )

        return candidates


class Ranker:
    def rank(
        self,
        candidates: List[RetrievalCandidate],
        now: datetime,
    ) -> List[RankedCandidate]:
        if not candidates:
            return []

        # We must ensure 'now' is timezone-aware if the records are timezone-aware
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        scored_candidates = []
        for cand in candidates:
            # 1. Semantic score (unavailable cosine_similarity -> 0.0)
            if cand.cosine_similarity is None:
                semantic_score = 0.0
            else:
                semantic_score = max(0.0, min(cand.cosine_similarity, 1.0))

            # 2. Keyword score
            keyword_score = (
                cand.matched_query_terms / max(cand.total_unique_query_terms, 1)
                if cand.total_unique_query_terms > 0
                else 0.0
            )

            # 3. Importance score
            importance_score = cand.memory.importance / 10.0

            # 4. Confidence score
            confidence_score = max(0.0, min(cand.memory.confidence, 1.0))

            # 5. Recency score (bounded interpretation: future updated_at -> elapsed_days = 0.0 -> recency = 1.0)
            elapsed_seconds = (now - cand.memory.updated_at).total_seconds()
            age_days = max(elapsed_seconds / 86400.0, 0.0)
            recency_score = math.exp(-age_days / 30.0)

            # 6. Reinforcement score
            reinforcement_score = 1.0 - math.exp(-cand.memory.reinforcement_count / 5.0)

            # Construct breakdown (validates [0, 1] range and finiteness)
            breakdown = ScoreBreakdown(
                semantic_score=semantic_score,
                keyword_score=keyword_score,
                importance_score=importance_score,
                recency_score=recency_score,
                confidence_score=confidence_score,
                reinforcement_score=reinforcement_score,
            )

            # Calculate full-precision weighted final score (no pre-sort rounding)
            final_score = (
                0.35 * semantic_score
                + 0.20 * keyword_score
                + 0.15 * importance_score
                + 0.10 * recency_score
                + 0.10 * confidence_score
                + 0.10 * reinforcement_score
            )

            scored_candidates.append((cand.memory, final_score, breakdown))

        # Deterministic Sorting (Timsort is stable):
        # 1. ID ASC (lexicographical string ordering of UUID)
        scored_candidates.sort(key=lambda x: str(x[0].id))
        # 2. created_at DESC
        scored_candidates.sort(key=lambda x: x[0].created_at, reverse=True)
        # 3. final_score DESC
        scored_candidates.sort(key=lambda x: x[1], reverse=True)

        # Assign positional ranks and wrap in RankedCandidate
        ranked = []
        for i, (record, final_score, breakdown) in enumerate(scored_candidates):
            ranked.append(
                RankedCandidate(
                    memory=record,
                    final_score=final_score,
                    score_breakdown=breakdown,
                    rank=i + 1,
                )
            )

        return ranked
