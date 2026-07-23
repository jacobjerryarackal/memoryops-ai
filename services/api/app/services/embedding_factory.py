import os
from typing import Optional
import httpx

from .embedding import EmbeddingService
from .openai_embedding import OpenAIEmbeddingService
from .gemini_embedding import GeminiEmbeddingService
from .fallback_embedding import FallbackEmbeddingService


def get_embedding_service(
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
    timeout_seconds: float = 10.0,
) -> EmbeddingService:
    """
    Factory function to resolve and instantiate the configured EmbeddingService.
    Reads `EMBEDDING_PROVIDER` from the environment if the `provider` argument is not supplied.
    
    Supported values:
    - 'openai' (default): OpenAI text-embedding-3-small
    - 'gemini': Google Gemini text-embedding-004
    - 'fallback': Offline fallback mode
    """
    env_provider = os.environ.get("EMBEDDING_PROVIDER", "openai")
    resolved_provider = (provider or env_provider).strip().lower()

    if resolved_provider == "openai":
        return OpenAIEmbeddingService(
            api_key=api_key,
            client=client,
            timeout_seconds=timeout_seconds,
        )
    elif resolved_provider == "gemini":
        return GeminiEmbeddingService(
            api_key=api_key,
            client=client,
            timeout_seconds=timeout_seconds,
        )
    elif resolved_provider == "fallback":
        return FallbackEmbeddingService()
    else:
        raise ValueError(
            f"Unsupported embedding provider: '{resolved_provider}'. "
            "Supported providers are: 'openai', 'gemini', 'fallback'."
        )
