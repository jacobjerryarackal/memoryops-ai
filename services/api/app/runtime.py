from .repositories.memory import InMemoryMemoryRepository
from .services.openai_embedding import OpenAIEmbeddingService
from .services.retrieval import Retriever, Ranker, ContextComposer, RetrievalCoordinator
from .services.retrieval_telemetry import StructuredRetrievalLogger
from .services.audit import InMemoryAuditService
from .services.governance import GovernanceService
from .policy.broker import PolicyBroker

# Single process-lifetime repository and audit instance
_shared_repository = InMemoryMemoryRepository()
_shared_audit = InMemoryAuditService()
_shared_telemetry = StructuredRetrievalLogger()


def get_memory_repository() -> InMemoryMemoryRepository:
    return _shared_repository


def get_audit_service() -> InMemoryAuditService:
    return _shared_audit


def get_governance_service() -> GovernanceService:
    broker = PolicyBroker(_shared_repository)
    return GovernanceService(
        repository=_shared_repository,
        audit_service=_shared_audit,
        broker=broker,
    )


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
