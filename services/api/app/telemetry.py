import functools
import time
import inspect
import uuid
import contextvars
from typing import Any, Callable, Optional

# ContextVar to propagate the active trace ID across tasks
active_trace_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("active_trace_id", default=None)

def trace_method(category: str, name: str):
    """
    Decorator to wrap a method (sync or async) and record its execution latency,
    errors, and span lifecycle. Propagates the active trace_id.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                from .services.observability import obs
                
                # Check for explicit trace_id in kwargs
                trace_id = kwargs.pop("trace_id", None)
                if not trace_id:
                    # Fall back to active context trace_id or generate a new one
                    trace_id = active_trace_id.get() or f"trace-{uuid.uuid4()}"
                
                # Set active trace_id context for downstream calls
                token = active_trace_id.set(trace_id)
                
                # Extract tenant and user if available in first argument or kwargs
                tenant_id = kwargs.get("tenant_id")
                user_id = kwargs.get("user_id")
                if not tenant_id and args:
                    # Try to extract from object properties or models
                    obj = args[0]
                    if hasattr(obj, "tenant_id"):
                        tenant_id = getattr(obj, "tenant_id")
                    if hasattr(obj, "user_id"):
                        user_id = getattr(obj, "user_id")
                
                tags = {"category": category}
                if tenant_id:
                    tags["tenant_id"] = tenant_id
                if user_id:
                    tags["user_id"] = user_id
                
                obs.emit_event("span_start", {
                    "span_name": f"{args[0].__class__.__name__}.{func.__name__}" if args else func.__name__,
                    "trace_id": trace_id,
                    "tags": tags
                })
                
                start_time = time.perf_counter()
                try:
                    res = await func(*args, **kwargs)
                    return res
                except Exception as e:
                    obs.record_error(
                        error_type=type(e).__name__,
                        message=str(e),
                        location=f"span:{args[0].__class__.__name__}.{func.__name__}" if args else f"span:{func.__name__}",
                        trace_id=trace_id
                    )
                    raise
                finally:
                    duration = (time.perf_counter() - start_time) * 1000.0
                    obs.emit_event("span_end", {
                        "span_name": f"{args[0].__class__.__name__}.{func.__name__}" if args else func.__name__,
                        "trace_id": trace_id,
                        "duration_ms": round(duration, 3),
                        "tags": tags
                    })
                    active_trace_id.reset(token)
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                from .services.observability import obs
                
                trace_id = kwargs.pop("trace_id", None)
                if not trace_id:
                    trace_id = active_trace_id.get() or f"trace-{uuid.uuid4()}"
                
                token = active_trace_id.set(trace_id)
                
                tenant_id = kwargs.get("tenant_id")
                user_id = kwargs.get("user_id")
                if not tenant_id and args:
                    obj = args[0]
                    if hasattr(obj, "tenant_id"):
                        tenant_id = getattr(obj, "tenant_id")
                    if hasattr(obj, "user_id"):
                        user_id = getattr(obj, "user_id")
                
                tags = {"category": category}
                if tenant_id:
                    tags["tenant_id"] = tenant_id
                if user_id:
                    tags["user_id"] = user_id
                
                obs.emit_event("span_start", {
                    "span_name": f"{args[0].__class__.__name__}.{func.__name__}" if args else func.__name__,
                    "trace_id": trace_id,
                    "tags": tags
                })
                
                start_time = time.perf_counter()
                try:
                    res = func(*args, **kwargs)
                    return res
                except Exception as e:
                    obs.record_error(
                        error_type=type(e).__name__,
                        message=str(e),
                        location=f"span:{args[0].__class__.__name__}.{func.__name__}" if args else f"span:{func.__name__}",
                        trace_id=trace_id
                    )
                    raise
                finally:
                    duration = (time.perf_counter() - start_time) * 1000.0
                    obs.emit_event("span_end", {
                        "span_name": f"{args[0].__class__.__name__}.{func.__name__}" if args else func.__name__,
                        "trace_id": trace_id,
                        "duration_ms": round(duration, 3),
                        "tags": tags
                    })
                    active_trace_id.reset(token)
            return sync_wrapper
    return decorator

def trace_class(category: str):
    """
    Class decorator that wraps all public methods of a class with trace_method.
    """
    def decorator(cls: type) -> type:
        for attr_name, attr_value in list(cls.__dict__.items()):
            if callable(attr_value) and not attr_name.startswith("__"):
                wrapped = trace_method(category, attr_name)(attr_value)
                setattr(cls, attr_name, wrapped)
        return cls
    return decorator
