import math
import unicodedata
from datetime import datetime, timezone
from typing import List, Optional, Tuple


from ..domain.enums import RetrievalMode, MemoryStatus
from ..domain.models import MemoryRecord
from ..domain.retrieval import (
    RetrievalCandidate,
    ScoreBreakdown,
    RankedCandidate,
    UsedMemory,
    UsedMemorySource,
)
from ..repositories.base import MemoryRepository
from .embedding import EmbeddingService
import time
import uuid
from .retrieval_telemetry import RetrievalTelemetry, NoOpRetrievalTelemetry




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
            # Defensive validation: drop violating records before they reach the Ranker
            if (
                record.tenant_id != tenant_id
                or record.user_id != user_id
                or record.status != MemoryStatus.ACTIVE
            ):
                continue

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


class ContextComposer:
    def __init__(self, max_memories: int = 10, max_characters: int = 4000) -> None:
        if not isinstance(max_memories, int) or max_memories < 1:
            raise ValueError("max_memories must be an integer >= 1")
        if not isinstance(max_characters, int) or max_characters < 1:
            raise ValueError("max_characters must be an integer >= 1")
        self.max_memories = max_memories
        self.max_characters = max_characters

    def compose_context(
        self,
        candidates: List[RankedCandidate],
    ) -> Tuple[str, List[UsedMemory]]:
        if not candidates:
            return "", []

        selected_candidates = []
        used_characters = 0

        for cand in candidates:
            if len(selected_candidates) >= self.max_memories:
                break

            content_length = len(cand.memory.content)
            if used_characters + content_length > self.max_characters:
                continue

            selected_candidates.append(cand)
            used_characters += content_length

        if not selected_candidates:
            return "", []

        # Context Formatting
        context_lines = []
        for cand in selected_candidates:
            context_lines.append(f"- ({cand.memory.memory_type.value}) {cand.memory.content}")
        context = "\n".join(context_lines)

        # UsedMemory Serialization
        used_memories = []
        for cand in selected_candidates:
            # Deterministic reason generation
            semantic_contrib = 0.35 * cand.score_breakdown.semantic_score
            keyword_contrib = 0.20 * cand.score_breakdown.keyword_score

            if semantic_contrib > keyword_contrib and semantic_contrib > 0.0:
                reason = f"Selected (Rank #{cand.rank}): Semantically relevant to the query (Score: {cand.final_score:.2f})."
            elif keyword_contrib > semantic_contrib and keyword_contrib > 0.0:
                reason = f"Selected (Rank #{cand.rank}): Lexically relevant to the query (Score: {cand.final_score:.2f})."
            else:
                reason = f"Selected (Rank #{cand.rank}): Balanced relevance context (Score: {cand.final_score:.2f})."

            source_obj = UsedMemorySource(
                kind=cand.memory.source_kind,
                excerpt=cand.memory.source_excerpt,
            )

            # Preserve full precision score and breakdown
            used_memories.append(
                UsedMemory(
                    memory_id=cand.memory.id,
                    content=cand.memory.content,
                    memory_type=cand.memory.memory_type,
                    score=cand.final_score,
                    reason=reason,
                    score_breakdown=cand.score_breakdown,
                    source=source_obj,
                )
            )

        return context, used_memories


class RetrievalCoordinator:
    def __init__(
        self,
        embedding_service: EmbeddingService,
        retriever: Retriever,
        ranker: Ranker,
        context_composer: ContextComposer,
        telemetry: Optional[RetrievalTelemetry] = None,
    ) -> None:
        self._embedding_service = embedding_service
        self._retriever = retriever
        self._ranker = ranker
        self._context_composer = context_composer
        self._telemetry = telemetry if telemetry is not None else NoOpRetrievalTelemetry()

    async def retrieve_context(
        self,
        tenant_id: str,
        user_id: str,
        query_text: str,
        temporary_chat: bool = False,
        trace_id: Optional[str] = None,
    ) -> Tuple[str, List[UsedMemory], RetrievalMode]:
        # Upstream trace_id wins; generate one if absent (exists only for non-gateway service callers)
        if trace_id is None:
            trace_id = f"trace-{uuid.uuid4()}"

        if temporary_chat:
            telemetry_payload = {
                "event": "memory_retrieval",
                "trace_id": trace_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "retrieval_mode": RetrievalMode.NONE.value,
                "candidate_count": 0,
                "selected_memory_ids": [],
                "score_breakdown": {},
                "latency_ms": {
                    "retrieve": 0.0,
                    "rank": 0.0,
                    "compose": 0.0
                }
            }
            try:
                self._telemetry.emit(telemetry_payload)
            except Exception:
                pass
            return "", [], RetrievalMode.NONE

        try:
            query_embedding = await self._embedding_service.generate_embedding(query_text)
            retrieval_mode = RetrievalMode.HYBRID
        except Exception:
            query_embedding = None
            retrieval_mode = RetrievalMode.FALLBACK

        # Measure retrieve latency
        start_retrieve = time.perf_counter()
        candidates = await self._retriever.retrieve(
            tenant_id=tenant_id,
            user_id=user_id,
            query_text=query_text,
            query_embedding=query_embedding,
        )
        retrieve_latency = (time.perf_counter() - start_retrieve) * 1000.0

        # Measure rank latency
        start_rank = time.perf_counter()
        now = datetime.now(timezone.utc)
        ranked_candidates = self._ranker.rank(candidates, now=now)
        rank_latency = (time.perf_counter() - start_rank) * 1000.0

        # Measure compose latency
        start_compose = time.perf_counter()
        context, used_memories = self._context_composer.compose_context(ranked_candidates)
        compose_latency = (time.perf_counter() - start_compose) * 1000.0

        # Build score breakdown dictionary for selected candidates
        score_breakdown = {
            str(um.memory_id): um.score_breakdown.model_dump()
            for um in used_memories
        }

        # Build telemetry event payload
        telemetry_payload = {
            "event": "memory_retrieval",
            "trace_id": trace_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "retrieval_mode": retrieval_mode.value,
            "candidate_count": len(candidates),
            "selected_memory_ids": [str(um.memory_id) for um in used_memories],
            "score_breakdown": score_breakdown,
            "latency_ms": {
                "retrieve": retrieve_latency,
                "rank": rank_latency,
                "compose": compose_latency
            }
        }

        try:
            self._telemetry.emit(telemetry_payload)
        except Exception:
            pass

        return context, used_memories, retrieval_mode
