import pytest
from typing import List
from app.services import EmbeddingService


class FakeEmbeddingService(EmbeddingService):
    """
    Fake implementation of EmbeddingService for testing contract compliance.
    """

    async def generate_embedding(self, text: str) -> List[float]:
        # Validate input contract: empty or whitespace-only strings rejected
        if not text or not text.strip():
            raise ValueError("text input cannot be empty or whitespace-only")
        
        # Simulating provider generation failure for special text
        if text == "fail-me":
            raise RuntimeError("Provider failed to generate embedding")
            
        # Returns a mock 1536-dimensional float vector
        return [0.1] * 1536


@pytest.mark.anyio
async def test_embedding_service_interface_and_fake():
    # 1. Verify ABC import and faking
    service = FakeEmbeddingService()
    assert isinstance(service, EmbeddingService)

    # 2. Verify normal text returns List[float] with 1536 dimension
    vector = await service.generate_embedding("Hello world")
    assert isinstance(vector, list)
    assert len(vector) == 1536
    assert all(isinstance(x, float) for x in vector)


@pytest.mark.anyio
async def test_embedding_service_rejects_empty_input():
    service = FakeEmbeddingService()

    # 1. Empty string
    with pytest.raises(ValueError, match="text input cannot be empty or whitespace-only"):
        await service.generate_embedding("")

    # 2. Whitespace-only string
    with pytest.raises(ValueError, match="text input cannot be empty or whitespace-only"):
        await service.generate_embedding("   ")


@pytest.mark.anyio
async def test_embedding_service_failure_propagation():
    service = FakeEmbeddingService()

    # Verify RuntimeError propagates on failure
    with pytest.raises(RuntimeError, match="Provider failed to generate embedding"):
        await service.generate_embedding("fail-me")
