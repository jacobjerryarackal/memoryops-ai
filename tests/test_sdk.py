import sys
import os
import pytest
from unittest.mock import patch, MagicMock
from uuid import uuid4

# Add sdk path to python path to allow imports during test execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../sdk/memoryops-sdk")))

from memoryops_sdk import MemoryOpsClient, MemoryOpsClientError


def test_sdk_headers_initialization():
    client_no_token = MemoryOpsClient("http://testserver")
    assert "Authorization" not in client_no_token.headers

    client_token = MemoryOpsClient("http://testserver", token="mytestsecret")
    assert client_token.headers["Authorization"] == "Bearer mytestsecret"


def test_sdk_chat_invocation():
    with patch("requests.request") as mock_request:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "assistant_message": "Hello user!",
            "used_memories": [],
            "candidate_memories": [],
            "audit_event_ids": [],
            "temporary_chat": False,
            "retrieval_mode": "hybrid",
            "trace_id": "trace-123"
        }
        mock_request.return_value = mock_response

        client = MemoryOpsClient("http://api.memoryops.local", token="secret")
        res = client.chat(
            tenant_id="tenant_x",
            user_id="user_y",
            message="Remember that I love coding.",
            temporary_chat=False,
            conversation_id="conv_1"
        )

        assert res["assistant_message"] == "Hello user!"
        mock_request.assert_called_once_with(
            "POST",
            "http://api.memoryops.local/api/chat",
            headers={"Authorization": "Bearer secret"},
            params=None,
            json={
                "tenant_id": "tenant_x",
                "user_id": "user_y",
                "message": "Remember that I love coding.",
                "temporary_chat": False,
                "conversation_id": "conv_1"
            }
        )


def test_sdk_syntactic_sugar():
    with patch("requests.request") as mock_request:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"used_memories": [{"content": "Matched memory"}]}
        mock_request.return_value = mock_response

        client = MemoryOpsClient("http://api.memoryops.local")
        
        # 1. Test remember()
        client.remember(tenant_id="t1", user_id="u1", content="Seattle is beautiful.")
        assert mock_request.call_args[1]["json"]["message"] == "remember that Seattle is beautiful."

        # 2. Test recall()
        memories = client.recall(tenant_id="t1", user_id="u1", query="Seattle")
        assert len(memories) == 1
        assert memories[0]["content"] == "Matched memory"


def test_sdk_evidence_explain():
    mid = uuid4()
    with patch("requests.request") as mock_request:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "memory_id": str(mid),
            "tenant_id": "t1",
            "user_id": "u1",
            "audit_trail": []
        }
        mock_request.return_value = mock_response

        client = MemoryOpsClient("http://api.memoryops.local")
        res = client.explain(memory_id=mid, tenant_id="t1", user_id="u1")
        
        assert res["memory_id"] == str(mid)
        mock_request.assert_called_once_with(
            "GET",
            f"http://api.memoryops.local/api/memories/{mid}/evidence",
            headers={},
            params={"tenant_id": "t1", "user_id": "u1"},
            json=None
        )


def test_sdk_error_handling():
    with patch("requests.request") as mock_request:
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"detail": "Scope unauthorized."}
        mock_request.return_value = mock_response

        client = MemoryOpsClient("http://api.memoryops.local")
        
        with pytest.raises(MemoryOpsClientError) as exc_info:
            client.delete(memory_id=uuid4(), tenant_id="wrong_tenant", user_id="u1")
            
        assert "HTTP 403" in str(exc_info.value)
        assert "Scope unauthorized" in str(exc_info.value)
