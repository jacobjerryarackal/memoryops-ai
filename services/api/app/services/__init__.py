import importlib

_MODULE_MAPPING = {
    "AuditService": ".audit",
    "InMemoryAuditService": ".audit",
    "WriteService": ".write",
    "WriteResult": ".write",
    "WriteServiceError": ".write",
    "TargetUnavailableError": ".write",
    "InvalidPolicyResultError": ".write",
    "UnsupportedDecisionError": ".write",
    "Retriever": ".retrieval",
    "Ranker": ".retrieval",
    "ContextComposer": ".retrieval",
    "EmbeddingService": ".embedding",
    "RetrievalCoordinator": ".retrieval",
    "OpenAIEmbeddingService": ".openai_embedding",
    "GeminiEmbeddingService": ".gemini_embedding",
    "FallbackEmbeddingService": ".fallback_embedding",
    "get_embedding_service": ".embedding_factory",
    "GovernanceService": ".governance",
    "GovernanceError": ".governance",
    "GovernanceTargetUnavailableError": ".governance",
    "GovernanceInvalidTransitionError": ".governance",
    "GovernanceValidationError": ".governance",
    "GovernancePolicyBlockedError": ".governance",
}

def __getattr__(name: str):
    if name in _MODULE_MAPPING:
        module_path = _MODULE_MAPPING[name]
        module = importlib.import_module(module_path, __package__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

def __dir__():
    return list(_MODULE_MAPPING.keys())
