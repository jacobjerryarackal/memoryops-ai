from .config import settings
from .repositories.base import MemoryRepository, LifecycleRepository
from .repositories.memory import InMemoryMemoryRepository, InMemoryLifecycleRepository
from .repositories.postgres import PostgreSQLMemoryRepository, PostgreSQLAuditRepository, PostgreSQLLifecycleRepository
from .repositories.transactions import TransactionManager
from .services.embedding_factory import get_embedding_service
from .services.retrieval import Retriever, Ranker, ContextComposer, RetrievalCoordinator
from .services.retrieval_telemetry import StructuredRetrievalLogger
from .services.audit import AuditService, InMemoryAuditService
from .services.governance import GovernanceService
from .services.lifecycle import LifecycleRunner, WorkerScheduler
from .policy.broker import PolicyBroker

db_type = settings.database_type

if db_type == "postgres":
    _shared_repository: MemoryRepository = PostgreSQLMemoryRepository()
    _shared_audit: AuditService = PostgreSQLAuditRepository()
    _shared_lifecycle_repo: LifecycleRepository = PostgreSQLLifecycleRepository()
else:
    _shared_repository: MemoryRepository = InMemoryMemoryRepository()
    _shared_audit: AuditService = InMemoryAuditService()
    _shared_lifecycle_repo: LifecycleRepository = InMemoryLifecycleRepository()

_shared_transaction_manager = TransactionManager()
_shared_telemetry = StructuredRetrievalLogger()
_shared_lifecycle_runner = LifecycleRunner(_shared_lifecycle_repo)
_shared_worker_scheduler = WorkerScheduler(_shared_lifecycle_runner)

# Register business workers
from .services.lifecycle import RetentionWorker, DecayWorker, ReflectionWorker, CompactionWorker
_shared_lifecycle_runner.register_worker(RetentionWorker(_shared_repository))
_shared_lifecycle_runner.register_worker(DecayWorker(_shared_repository))
_shared_lifecycle_runner.register_worker(ReflectionWorker(_shared_repository))
_shared_lifecycle_runner.register_worker(CompactionWorker(_shared_repository))



def get_memory_repository() -> MemoryRepository:
    return _shared_repository


def get_transaction_manager() -> TransactionManager:
    return _shared_transaction_manager


def get_audit_service() -> AuditService:
    return _shared_audit


def get_lifecycle_repository() -> LifecycleRepository:
    return _shared_lifecycle_repo


def get_lifecycle_runner() -> LifecycleRunner:
    return _shared_lifecycle_runner


def get_worker_scheduler() -> WorkerScheduler:
    return _shared_worker_scheduler


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
