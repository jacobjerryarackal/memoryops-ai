import os
import math
import httpx
import logging
from typing import List, Optional

from .embedding import EmbeddingService

logger = logging.getLogger("app.services.gemini_embedding")


class GeminiEmbeddingService(EmbeddingService):
    """
    Concrete production implementation of EmbeddingService utilizing
    the Google Gemini Embeddings API with text-embedding-004.
    
    This service natively retrieves a 768-dimensional vector, which is 
    then zero-padded to 1536 dimensions to satisfy the strict database 
    and domain model dimensionality constraints, preserving cosine similarity.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        client: Optional[httpx.AsyncClient] = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        # Validate API Key lazily
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key or not resolved_key.strip():
            logger.warning(
                "GEMINI_API_KEY is not configured in the environment. "
                "Semantic embeddings are disabled; falling back to offline lexical retrieval mode."
            )
            self._api_key = None
        else:
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

        if not self._api_key:
            raise ValueError(
                "A valid, non-empty Gemini API key must be provided or configured in the environment."
            )

        url = "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent"
        headers = {
            "x-goog-api-key": self._api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "content": {
                "parts": [
                    {
                        "text": text
                    }
                ]
            }
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
        if not isinstance(res_json, dict):
            raise ValueError("Response payload must be a JSON object")

        embedding_data = res_json.get("embedding")
        if not isinstance(embedding_data, dict):
            raise ValueError("Response must contain an embedding object")

        values = embedding_data.get("values")
        if not isinstance(values, list):
            raise ValueError("Embedding values must be a sequence/list")

        if len(values) != 768:
            raise ValueError(f"Gemini native embedding must be exactly 768 dimensions, got {len(values)}")

        # Validate elements and cast to float
        validated_floats = []
        for val in values:
            if isinstance(val, bool) or not isinstance(val, (int, float)) or not math.isfinite(val):
                raise ValueError("Embedding elements must be finite numeric values")
            validated_floats.append(float(val))

        # Pad remaining 768 dimensions with 0.0 to satisfy 1536-dimensional database constraint
        padded_floats = validated_floats + [0.0] * 768

        return padded_floats
