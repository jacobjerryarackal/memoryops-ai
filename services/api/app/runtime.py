from .repositories.memory import InMemoryMemoryRepository
from .services.openai_embedding import OpenAIEmbeddingService
from .services.retrieval import Retriever, Ranker, ContextComposer, RetrievalCoordinator
from .services.retrieval_telemetry import StructuredRetrievalLogger

# Single process-lifetime repository instance
_shared_repository = InMemoryMemoryRepository()
_shared_telemetry = StructuredRetrievalLogger()


def get_memory_repository() -> InMemoryMemoryRepository:
    return _shared_repository


def get_retrieval_coordinator() -> RetrievalCoordinator:
    # Lazily construct the coordinator dependencies when requested
    embedding_service = OpenAIEmbeddingService()
    retriever = Retriever(_shared_repository)
    ranker = Ranker()
    context_composer = ContextComposer()
    return RetrievalCoordinator(
        embedding_service=embedding_service,
        retriever=retriever,
        ranker=ranker,
        context_composer=context_composer,
        telemetry=_shared_telemetry,
    )
