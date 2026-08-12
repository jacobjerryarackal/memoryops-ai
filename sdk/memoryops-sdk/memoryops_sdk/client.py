import requests
from typing import Any, Dict, List, Optional
from uuid import UUID


class MemoryOpsClientError(Exception):
    """Base exception for MemoryOps SDK client errors."""
    pass


class MemoryOpsClient:
    """
    Production-grade typed Python SDK client for the MemoryOps AI platform.
    """
    def __init__(self, base_url: str = "http://127.0.0.1:8000", token: Optional[str] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def _request(
        self, method: str, path: str, params: Optional[dict] = None, json: Optional[dict] = None
    ) -> Any:
        url = f"{self.base_url}{path}"
        try:
            resp = requests.request(method, url, headers=self.headers, params=params, json=json)
            if resp.status_code >= 400:
                detail = resp.json().get("detail", resp.text)
                raise MemoryOpsClientError(f"HTTP {resp.status_code}: {detail}")
            return resp.json()
        except requests.RequestException as e:
            raise MemoryOpsClientError(f"Network error: {str(e)}")

    def chat(
        self, tenant_id: str, user_id: str, message: str, temporary_chat: bool = False, conversation_id: Optional[str] = None
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
        return self._request("POST", "/api/chat", json=payload)

    def remember(self, tenant_id: str, user_id: str, content: str) -> Dict[str, Any]:
        """
        Syntactic sugar to persist a memory candidate by sending a 'remember that ...' chat instruction.
        """
        message = f"remember that {content}"
        return self.chat(tenant_id=tenant_id, user_id=user_id, message=message)

    def recall(self, tenant_id: str, user_id: str, query: str) -> List[Dict[str, Any]]:
        """
        Syntactic sugar to retrieve memories relevant to a query. Returns list of used memories.
        """
        res = self.chat(tenant_id=tenant_id, user_id=user_id, message=query)
        return res.get("used_memories", [])

    def list_memories(
        self, tenant_id: str, user_id: str, status: Optional[str] = None, memory_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Lists all memories scoped to the tenant/user.
        """
        params = {"tenant_id": tenant_id, "user_id": user_id}
        if status:
            params["status"] = status
        if memory_type:
            params["memory_type"] = memory_type
        return self._request("GET", "/api/memories", params=params)

    def get_memory(self, memory_id: UUID, tenant_id: str, user_id: str) -> Dict[str, Any]:
        """
        Retrieves a single memory record.
        """
        params = {"tenant_id": tenant_id, "user_id": user_id}
        return self._request("GET", f"/api/memories/{memory_id}", params=params)

    def delete(self, memory_id: UUID, tenant_id: str, user_id: str) -> Dict[str, Any]:
        """
        Deletes a single memory record.
        """
        payload = {"tenant_id": tenant_id, "user_id": user_id}
        return self._request("DELETE", f"/api/memories/{memory_id}", json=payload)

    def get_provenance(self, memory_id: UUID, tenant_id: str, user_id: str) -> Dict[str, Any]:
        """
        Gets memory metadata origin and policy decision context.
        """
        params = {"tenant_id": tenant_id, "user_id": user_id}
        return self._request("GET", f"/api/memories/{memory_id}/provenance", params=params)

    def explain(self, memory_id: UUID, tenant_id: str, user_id: str) -> Dict[str, Any]:
        """
        Retrieves the comprehensive evidence/provenance and audit trail bundle for the memory.
        """
        params = {"tenant_id": tenant_id, "user_id": user_id}
        return self._request("GET", f"/api/memories/{memory_id}/evidence", params=params)

    def list_audit_trail(
        self, tenant_id: str, user_id: Optional[str] = None, memory_id: Optional[UUID] = None, limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Retrieves historical audit trail records for governance compliance.
        """
        params = {"tenant_id": tenant_id}
        if user_id:
            params["user_id"] = user_id
        if memory_id:
            params["memory_id"] = str(memory_id)
        if limit:
            params["limit"] = limit
        return self._request("GET", "/api/audit", params=params)
