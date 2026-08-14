import time
import json
import uuid
import sys
import logging
import asyncio
import functools
import inspect
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Callable

logger = logging.getLogger("app.observability")


class ObservabilityService:
    def __init__(self, logger_name: str = "app.observability") -> None:
        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            ch = logging.StreamHandler(sys.stdout)
            ch.setLevel(logging.INFO)
            formatter = logging.Formatter('%(message)s')
            ch.setFormatter(formatter)
            self.logger.addHandler(ch)
            self.logger.propagate = False
        self.recorded_events: List[Dict[str, Any]] = []
        self._test_mode: bool = False
        self._exporters_available: bool = True

    def set_test_mode(self, enabled: bool) -> None:
        self._test_mode = enabled
        self.recorded_events.clear()

    def set_exporters_available(self, available: bool) -> None:
        self._exporters_available = available

    def emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        # Telemetry failure isolation: satisfy the contract to never propagate errors
        if not self._exporters_available:
            self.logger.warning("Telemetry exporter unavailable. Event dropped.")
            return

        try:
            event = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_type": event_type,
                **data,
            }
            if self._test_mode:
                self.recorded_events.append(event)
            self.logger.info(json.dumps(event))
        except Exception:
            # Fail-safe: telemetry must never interfere with application logic
            pass

    def record_metric(self, name: str, value: Any, tags: Optional[Dict[str, Any]] = None) -> None:
        self.emit_event("metric", {
            "metric_name": name,
            "metric_value": value,
            "tags": tags or {},
        })

    def record_error(self, error_type: str, message: str, location: str, trace_id: Optional[str] = None) -> None:
        self.emit_event("error", {
            "error_type": error_type,
            "message": message,
            "location": location,
            "trace_id": trace_id,
        })

    @contextmanager
    def span(self, name: str, trace_id: Optional[str] = None, tags: Optional[Dict[str, Any]] = None):
        t_id = trace_id or f"trace-{uuid.uuid4()}"
        start_time = time.perf_counter()
        tags = tags or {}

        self.emit_event("span_start", {
            "span_name": name,
            "trace_id": t_id,
            "tags": tags,
        })

        try:
            yield t_id
        except Exception as e:
            self.record_error(
                error_type=type(e).__name__,
                message=str(e),
                location=f"span:{name}",
                trace_id=t_id
            )
            raise
        finally:
            duration = (time.perf_counter() - start_time) * 1000.0
            self.emit_event("span_end", {
                "span_name": name,
                "trace_id": t_id,
                "duration_ms": round(duration, 3),
                "tags": tags,
            })


# Global singleton instance
obs = ObservabilityService()


def trace_method(category: str) -> Callable:
    """
    Decorator to wrap methods with an observability span.
    Extracts tenant_id, user_id, and trace_id automatically if present in parameters.
    """
    def decorator(func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                class_name = args[0].__class__.__name__ if args else "Unknown"
                method_name = func.__name__
                span_name = f"{class_name}.{method_name}"

                tags = {"category": category}
                tenant_id = kwargs.get("tenant_id")
                user_id = kwargs.get("user_id")
                
                if not tenant_id or not user_id:
                    for arg in args[1:]:
                        if hasattr(arg, "tenant_id") and hasattr(arg, "user_id"):
                            tenant_id = tenant_id or getattr(arg, "tenant_id")
                            user_id = user_id or getattr(arg, "user_id")
                            break

                if tenant_id:
                    tags["tenant_id"] = tenant_id
                if user_id:
                    tags["user_id"] = user_id

                trace_id = kwargs.get("trace_id", None)
                sig = inspect.signature(func)
                if "trace_id" not in sig.parameters:
                    kwargs.pop("trace_id", None)
                else:
                    kwargs["trace_id"] = trace_id
                with obs.span(span_name, trace_id=trace_id, tags=tags):
                    return await func(*args, **kwargs)
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                class_name = args[0].__class__.__name__ if args else "Unknown"
                method_name = func.__name__
                span_name = f"{class_name}.{method_name}"

                tags = {"category": category}
                tenant_id = kwargs.get("tenant_id")
                user_id = kwargs.get("user_id")

                if not tenant_id or not user_id:
                    for arg in args[1:]:
                        if hasattr(arg, "tenant_id") and hasattr(arg, "user_id"):
                            tenant_id = tenant_id or getattr(arg, "tenant_id")
                            user_id = user_id or getattr(arg, "user_id")
                            break

                if tenant_id:
                    tags["tenant_id"] = tenant_id
                if user_id:
                    tags["user_id"] = user_id

                trace_id = kwargs.get("trace_id", None)
                sig = inspect.signature(func)
                if "trace_id" not in sig.parameters:
                    kwargs.pop("trace_id", None)
                else:
                    kwargs["trace_id"] = trace_id
                with obs.span(span_name, trace_id=trace_id, tags=tags):
                    return func(*args, **kwargs)
            return sync_wrapper
    return decorator


def trace_class(category: str) -> Callable:
    """
    Class decorator that wraps all public methods with trace_method.
    """
    def decorator(cls: type) -> type:
        for attr_name in dir(cls):
            if attr_name.startswith("_"):
                continue
            attr = getattr(cls, attr_name)
            if callable(attr):
                # Apply trace_method decorator to the callable attribute
                setattr(cls, attr_name, trace_method(category)(attr))
        return cls
    return decorator
