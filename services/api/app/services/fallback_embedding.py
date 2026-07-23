from typing import List
from .embedding import EmbeddingService


class FallbackEmbeddingService(EmbeddingService):
    """
    Offline fallback embedding service implementation that immediately
    raises an exception on any embedding generation request to trigger 
    the system's offline lexical fallback retrieval mode.
    """

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def generate_embedding(self, text: str) -> List[float]:
        # Input validation still applies to satisfy the abstract contract
        if not text or not text.strip():
            raise ValueError("text input cannot be empty or whitespace-only")

        raise RuntimeError("Offline fallback mode is explicitly configured. Semantic search is disabled.")
