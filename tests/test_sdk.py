import sys
import os
import pytest
from unittest.mock import patch, MagicMock
from uuid import uuid4
import requests

# Add sdk path to python path to allow imports during test execution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../sdk/memoryops-sdk")))

from memoryops_sdk import (
    MemoryOpsClient,
    MemoryOpsError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
    NotFoundError,
    PolicyDeniedError,
    ValidationError,
)


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
            conversation_id="conv_1",
            trace_id="trace-custom",
            idempotency_key="idem-key"
        )

        assert res["assistant_message"] == "Hello user!"
        mock_request.assert_called_once_with(
            "POST",
            "http://api.memoryops.local/api/chat",
            headers={
                "Authorization": "Bearer secret",
                "X-Trace-ID": "trace-custom",
                "X-Idempotency-Key": "idem-key"
            },
            params=None,
            json={
                "tenant_id": "tenant_x",
                "user_id": "user_y",
                "message": "Remember that I love coding.",
                "temporary_chat": False,
                "conversation_id": "conv_1"
            },
            timeout=30.0
        )


def test_sdk_pagination():
    with patch("requests.request") as mock_request:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = []
        mock_request.return_value = mock_response

        client = MemoryOpsClient("http://api.memoryops.local")
        client.list_memories(
            tenant_id="t1",
            user_id="u1",
            limit=10,
            offset=20,
            trace_id="trace-list"
        )

        mock_request.assert_called_once_with(
            "GET",
            "http://api.memoryops.local/api/memories",
            headers={"X-Trace-ID": "trace-list"},
            params={"tenant_id": "t1", "user_id": "u1", "limit": 10, "offset": 20},
            json=None,
            timeout=30.0
        )


def test_sdk_exception_mapping():
    client = MemoryOpsClient("http://api.memoryops.local")

    # Map status code and JSON responses to verification functions
    test_cases = [
        (401, {}, AuthenticationError),
        (403, {}, AuthorizationError),
        (404, {}, NotFoundError),
        (409, {}, ConflictError),
        (422, {"code": "POLICY_BLOCKED", "detail": "blocked"}, PolicyDeniedError),
        (422, {"detail": "validation failed"}, ValidationError),
        (500, {}, MemoryOpsError),
    ]

    for status_code, body, exc_type in test_cases:
        with patch("requests.request") as mock_request:
            mock_response = MagicMock()
            mock_response.status_code = status_code
            mock_response.json.return_value = body
            mock_response.text = "Error detail"
            mock_request.return_value = mock_response

            with pytest.raises(exc_type):
                client.get_memory(memory_id=uuid4(), tenant_id="t1", user_id="u1")


def test_sdk_retries_on_503():
    with patch("requests.request") as mock_request:
        # Mock 2 failures followed by 1 success
        mock_fail = MagicMock()
        mock_fail.status_code = 503
        mock_fail.text = "Service Unavailable"

        mock_success = MagicMock()
        mock_success.status_code = 200
        mock_success.json.return_value = {"status": "ok"}

        mock_request.side_effect = [mock_fail, mock_fail, mock_success]

        client = MemoryOpsClient("http://api.memoryops.local", max_retries=2)
        
        # Patch time.sleep to run quickly
        with patch("time.sleep") as mock_sleep:
            res = client.list_memories(tenant_id="t1", user_id="u1")
            assert res == {"status": "ok"}
            assert mock_request.call_count == 3
            assert mock_sleep.call_count == 2
