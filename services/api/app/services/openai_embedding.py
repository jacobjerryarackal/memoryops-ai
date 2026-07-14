import os
import math
import httpx
from typing import List, Optional

from .embedding import EmbeddingService


class OpenAIEmbeddingService(EmbeddingService):
    """
    Concrete production implementation of EmbeddingService utilizing
    the OpenAI Embeddings REST API with text-embedding-3-small.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        client: Optional[httpx.AsyncClient] = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        # Validate API Key
        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not resolved_key or not resolved_key.strip():
            raise ValueError(
                "A valid, non-empty OpenAI API key must be provided or configured in the environment."
            )
        self._api_key = resolved_key.strip()

        # Validate Timeout
        if not isinstance(timeout_seconds, (int, float)) or isinstance(timeout_seconds, bool):
            raise ValueError("timeout_seconds must be a finite positive number")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a finite positive number")

        self._timeout = float(timeout_seconds)
        self._client = client

    async def generate_embedding(self, text: str) -> List[float]:
        # Validate input contract
        if not text or not text.strip():
            raise ValueError("text input cannot be empty or whitespace-only")

        url = "https://api.openai.com/v1/embeddings"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": "text-embedding-3-small",
            "input": text,
        }

        # Outbound request execution
        if self._client is not None:
            # Reuses caller-managed injected client (lifespan handled by caller)
            response = await self._client.post(
                url, json=payload, headers=headers, timeout=self._timeout
            )
        else:
            # Uses short-lived client context (lifespan handled locally)
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    url, json=payload, headers=headers
                )

        # Propagate non-success HTTP status codes
        response.raise_for_status()

        # Strict response parsing and validation
        res_json = response.json()
        
        data = res_json.get("data")
        if not isinstance(data, list) or len(data) != 1:
            raise ValueError("Response data must contain exactly one item")

        item = data[0]
        if not isinstance(item, dict) or "embedding" not in item:
            raise ValueError("Response item must contain an embedding field")

        emb = item["embedding"]
        if not isinstance(emb, list):
            raise ValueError("Embedding must be a sequence/list")

        if len(emb) != 1536:
            raise ValueError(f"Embedding must be exactly 1536 dimensions, got {len(emb)}")

        validated_floats = []
        for val in emb:
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
                raise ValueError("Embedding elements must be finite numeric values")
            validated_floats.append(float(val))

        return validated_floats
