import requests
import time
import random
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

# Exception Hierarchy
class MemoryOpsError(Exception):
    """Base exception for MemoryOps platform."""
    pass

class AuthenticationError(MemoryOpsError):
    """Raised on 401 Unauthenticated."""
    pass

class AuthorizationError(MemoryOpsError):
    """Raised on 403 Forbidden."""
    pass

class ConflictError(MemoryOpsError):
    """Raised on 409 Conflict (e.g. OCC version conflicts, concurrent locks, idempotency mismatch)."""
    pass

class NotFoundError(MemoryOpsError):
    """Raised on 404 Not Found."""
    pass

class PolicyDeniedError(MemoryOpsError):
    """Raised when a memory write or update is blocked/denied by policy."""
    pass

class ValidationError(MemoryOpsError):
    """Raised on 422 Validation Error or client-side type checks."""
    pass


# Backward compatibility alias
MemoryOpsClientError = MemoryOpsError


class MemoryOpsClient:
    """
    Production-grade typed Python SDK client for the MemoryOps AI platform.
    """
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        token: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
        self.timeout = timeout
        self.max_retries = max_retries

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
        headers: Optional[dict] = None,
        trace_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        
        req_headers = self.headers.copy()
        if headers:
            req_headers.update(headers)
        if trace_id:
            req_headers["X-Trace-ID"] = trace_id
        if idempotency_key:
            req_headers["X-Idempotency-Key"] = idempotency_key

        req_timeout = timeout if timeout is not None else self.timeout

        last_err = None
        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                # Exponential backoff with jitter
                backoff_factor = 0.5
                backoff_max = 8.0
                sleep_time = min(backoff_max, backoff_factor * (2 ** (attempt - 1)))
                sleep_time += random.uniform(0, 0.1 * sleep_time)
                time.sleep(sleep_time)

            try:
                resp = requests.request(
                    method,
                    url,
                    headers=req_headers,
                    params=params,
                    json=json,
                    timeout=req_timeout,
                )
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_err = e
                continue
            except requests.RequestException as e:
                raise MemoryOpsError(f"Network error: {str(e)}") from e

            # Retry on 429 or 5xx
            if resp.status_code in (429, 502, 503, 504):
                last_err = f"HTTP {resp.status_code}: {resp.text}"
                continue

            # Process response if status is not retryable
            if resp.status_code >= 400:
                try:
                    body = resp.json()
                    detail = body.get("detail", resp.text)
                    code = body.get("code")
                except Exception:
                    body = {}
                    detail = resp.text
                    code = None

                if resp.status_code == 401:
                    raise AuthenticationError(f"Authentication failed: {detail}")
                elif resp.status_code == 403:
                    raise AuthorizationError(f"Authorization failed: {detail}")
                elif resp.status_code == 404:
                    raise NotFoundError(f"Resource not found: {detail}")
                elif resp.status_code == 409:
                    raise ConflictError(f"Conflict encountered: {detail}")
                elif resp.status_code == 422:
                    if code == "POLICY_BLOCKED" or "policy" in str(detail).lower() or "blocked" in str(detail).lower():
                        raise PolicyDeniedError(f"Policy denied operation: {detail}")
                    else:
                        raise ValidationError(f"Validation error: {detail}")
                else:
                    raise MemoryOpsError(f"HTTP {resp.status_code}: {detail}")

            try:
                return resp.json()
            except Exception as e:
                if resp.status_code in (200, 204):
                    return {}
                raise MemoryOpsError(f"Failed to parse JSON response: {str(e)}") from e

        # If we exhausted retries
        if isinstance(last_err, Exception):
            raise MemoryOpsError(f"Request failed after {self.max_retries} retries: {str(last_err)}") from last_err
        else:
            raise MemoryOpsError(f"Request failed after {self.max_retries} retries: {last_err}")

    def chat(
        self,
        tenant_id: str,
        user_id: str,
        message: str,
        temporary_chat: bool = False,
        conversation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Sends a message to the chat interface. Handles context retrieval and candidate memory writes.
        """
        payload = {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "message": message,
            "temporary_chat": temporary_chat,
            "conversation_id": conversation_id,
        }
        return self._request(
            "POST",
            "/api/chat",
            json=payload,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
            timeout=timeout,
        )

    def remember(
        self,
        tenant_id: str,
        user_id: str,
        content: str,
        trace_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Syntactic sugar to persist a memory candidate by sending a 'remember that ...' chat instruction.
        """
        message = f"remember that {content}"
        return self.chat(
            tenant_id=tenant_id,
            user_id=user_id,
            message=message,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
            timeout=timeout,
        )

    def recall(
        self,
        tenant_id: str,
        user_id: str,
        query: str,
        trace_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Syntactic sugar to retrieve memories relevant to a query. Returns list of used memories.
        """
        res = self.chat(
            tenant_id=tenant_id,
            user_id=user_id,
            message=query,
            trace_id=trace_id,
            timeout=timeout,
        )
        return res.get("used_memories", [])

    def list_memories(
        self,
        tenant_id: str,
        user_id: str,
        status: Optional[str] = None,
        memory_type: Optional[str] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        trace_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Lists all memories scoped to the tenant/user.
        """
        params = {"tenant_id": tenant_id, "user_id": user_id}
        if status:
            params["status"] = status
        if memory_type:
            params["memory_type"] = memory_type
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        return self._request(
            "GET",
            "/api/memories",
            params=params,
            trace_id=trace_id,
            timeout=timeout,
        )

    def get_memory(
        self,
        memory_id: Union[UUID, str],
        tenant_id: str,
        user_id: str,
        trace_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Retrieves a single memory record.
        """
        params = {"tenant_id": tenant_id, "user_id": user_id}
        return self._request(
            "GET",
            f"/api/memories/{memory_id}",
            params=params,
            trace_id=trace_id,
            timeout=timeout,
        )

    def patch_memory(
        self,
        memory_id: Union[UUID, str],
        tenant_id: str,
        user_id: str,
        content: Optional[str] = None,
        importance: Optional[int] = None,
        confidence: Optional[float] = None,
        status: Optional[str] = None,
        sensitivity: Optional[str] = None,
        source_kind: Optional[str] = None,
        source_conversation_id: Optional[str] = None,
        source_excerpt: Optional[str] = None,
        trace_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Performs a governed partial update or state transition.
        """
        payload = {"tenant_id": tenant_id, "user_id": user_id}
        if content is not None:
            payload["content"] = content
        if importance is not None:
            payload["importance"] = importance
        if confidence is not None:
            payload["confidence"] = confidence
        if status is not None:
            payload["status"] = status
        if sensitivity is not None:
            payload["sensitivity"] = sensitivity
        if source_kind is not None:
            payload["source_kind"] = source_kind
        if source_conversation_id is not None:
            payload["source_conversation_id"] = source_conversation_id
        if source_excerpt is not None:
            payload["source_excerpt"] = source_excerpt

        return self._request(
            "PATCH",
            f"/api/memories/{memory_id}",
            json=payload,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
            timeout=timeout,
        )

    def delete(
        self,
        memory_id: Union[UUID, str],
        tenant_id: str,
        user_id: str,
        trace_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Deletes a single memory record.
        """
        payload = {"tenant_id": tenant_id, "user_id": user_id}
        return self._request(
            "DELETE",
            f"/api/memories/{memory_id}",
            json=payload,
            trace_id=trace_id,
            idempotency_key=idempotency_key,
            timeout=timeout,
        )

    def get_provenance(
        self,
        memory_id: Union[UUID, str],
        tenant_id: str,
        user_id: str,
        trace_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Gets memory metadata origin and policy decision context.
        """
        params = {"tenant_id": tenant_id, "user_id": user_id}
        return self._request(
            "GET",
            f"/api/memories/{memory_id}/provenance",
            params=params,
            trace_id=trace_id,
            timeout=timeout,
        )

    def explain(
        self,
        memory_id: Union[UUID, str],
        tenant_id: str,
        user_id: str,
        trace_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Retrieves the comprehensive evidence/provenance and audit trail bundle for the memory.
        """
        params = {"tenant_id": tenant_id, "user_id": user_id}
        return self._request(
            "GET",
            f"/api/memories/{memory_id}/evidence",
            params=params,
            trace_id=trace_id,
            timeout=timeout,
        )

    def list_audit_trail(
        self,
        tenant_id: str,
        user_id: Optional[str] = None,
        memory_id: Optional[Union[UUID, str]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        trace_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves historical audit trail records for governance compliance.
        """
        params = {"tenant_id": tenant_id}
        if user_id:
            params["user_id"] = user_id
        if memory_id:
            params["memory_id"] = str(memory_id)
        if limit is not None:
            params["limit"] = limit
        if offset is not None:
            params["offset"] = offset
        return self._request(
            "GET",
            "/api/audit",
            params=params,
            trace_id=trace_id,
            timeout=timeout,
        )
