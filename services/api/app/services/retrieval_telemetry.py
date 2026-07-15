import json
import logging
from abc import ABC, abstractmethod
from typing import Mapping, Any


class RetrievalTelemetry(ABC):
    @abstractmethod
    def emit(self, event: Mapping[str, Any]) -> None:
        """
        Emits a structured retrieval telemetry event.
        Must not raise exceptions or interfere with the caller's execution.
        """
        pass


class NoOpRetrievalTelemetry(RetrievalTelemetry):
    def emit(self, event: Mapping[str, Any]) -> None:
        pass


class StructuredRetrievalLogger(RetrievalTelemetry):
    def __init__(self, logger_name: str = "app.retrieval_telemetry") -> None:
        self.logger = logging.getLogger(logger_name)

    def emit(self, event: Mapping[str, Any]) -> None:
        try:
            # Emit the structured operational telemetry as a single line JSON log
            self.logger.info(json.dumps(event))
        except Exception:
            # Telemetry failure isolation: satisfy the contract to never propagate errors
            pass
