from abc import ABC, abstractmethod
from typing import List


class EmbeddingService(ABC):
    """
    Abstract base class defining the provider-neutral contract for generating 
    text vector embeddings. 
    
    Both query text and memory content must use the same underlying model 
    contract to ensure vector space compatibility.
    """

    @abstractmethod
    async def generate_embedding(self, text: str) -> List[float]:
        """
        Generates a 1536-dimensional vector embedding for the given text.

        Args:
            text: The raw text string to embed. Must not be empty or whitespace-only.

        Returns:
            A list of exactly 1536 floats representing the text embedding.

        Raises:
            ValueError: If the text is empty or whitespace-only.
            Exception: On external provider or network failure.
        """
        pass
