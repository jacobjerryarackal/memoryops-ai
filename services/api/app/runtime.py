import os
from .repositories.base import MemoryRepository
from .repositories.memory import InMemoryMemoryRepository
from .repositories.postgres import PostgreSQLMemoryRepository, PostgreSQLAuditRepository
from .services.embedding_factory import get_embedding_service
from .services.retrieval import Retriever, Ranker, ContextComposer, RetrievalCoordinator
from .services.retrieval_telemetry import StructuredRetrievalLogger
from .services.audit import AuditService, InMemoryAuditService
from .services.governance import GovernanceService
from .policy.broker import PolicyBroker

db_type = os.environ.get("DATABASE_TYPE", "memory").strip().lower()

if db_type == "postgres":
    _shared_repository: MemoryRepository = PostgreSQLMemoryRepository()
    _shared_audit: AuditService = PostgreSQLAuditRepository()
else:
    _shared_repository: MemoryRepository = InMemoryMemoryRepository()
    _shared_audit: AuditService = InMemoryAuditService()

_shared_telemetry = StructuredRetrievalLogger()


def get_memory_repository() -> MemoryRepository:
    return _shared_repository


def get_audit_service() -> AuditService:
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
    embedding_service = get_embedding_service()
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
