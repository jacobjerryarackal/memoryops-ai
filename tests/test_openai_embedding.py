import math
import os
import pytest
import httpx
from typing import List

from app.services import EmbeddingService, OpenAIEmbeddingService


def test_openai_embedding_constructor_key_resolution(monkeypatch):
    # Clear env to test explicit resolution
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    # 1. Explicit key
    service_explicit = OpenAIEmbeddingService(api_key="sk-explicit-key")
    assert service_explicit._api_key == "sk-explicit-key"

    # 2. Environment key fallback
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-key")
    service_env = OpenAIEmbeddingService()
    assert service_env._api_key == "sk-env-key"

    # 3. Missing key does not raise during construction, but raises on invocation
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    service_missing = OpenAIEmbeddingService()
    assert service_missing._api_key is None
    
    with pytest.raises(ValueError, match="API key must be provided"):
        pytest.find_code = True  # dummy line
        import anyio
        anyio.run(service_missing.generate_embedding, "test")

    # 4. Whitespace-only key behaves similarly
    service_whitespace = OpenAIEmbeddingService(api_key="   ")
    assert service_whitespace._api_key is None
    
    with pytest.raises(ValueError, match="API key must be provided"):
        anyio.run(service_whitespace.generate_embedding, "test")


def test_openai_embedding_constructor_timeout_validation():
    # Valid timeout
    service = OpenAIEmbeddingService(api_key="sk-test", timeout_seconds=5.5)
    assert service._timeout == 5.5

    # Invalid timeout types/values
    for invalid in [0, -1, -5.5, float("inf"), float("-inf"), float("nan"), True, "10"]:
        with pytest.raises(ValueError, match="timeout_seconds must be a finite positive number"):
            OpenAIEmbeddingService(api_key="sk-test", timeout_seconds=invalid)


@pytest.mark.anyio
async def test_openai_embedding_input_validation():
    service = OpenAIEmbeddingService(api_key="sk-test")

    # 1. Empty string
    with pytest.raises(ValueError, match="text input cannot be empty or whitespace-only"):
        await service.generate_embedding("")

    # 2. Whitespace-only string
    with pytest.raises(ValueError, match="text input cannot be empty or whitespace-only"):
        await service.generate_embedding("    ")


@pytest.mark.anyio
async def test_openai_embedding_successful_response():
    # Injected MockTransport to simulate OpenAI API response
    vector = [0.1] * 1536
    mock_payload = {
        "data": [
            {
                "embedding": vector
            }
        ]
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.openai.com/v1/embeddings"
        assert request.method == "POST"
        assert request.headers["Authorization"] == "Bearer sk-test"
        assert request.headers["Content-Type"] == "application/json"
        
        # Verify body payload: model and input preservation
        import json
        body = json.loads(request.read())
        assert body["model"] == "text-embedding-3-small"
        assert body["input"] == "  Hello World  "  # leading/trailing spaces preserved

        return httpx.Response(200, json=mock_payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = OpenAIEmbeddingService(api_key="sk-test", client=client)
        result = await service.generate_embedding("  Hello World  ")
        
        assert isinstance(result, list)
        assert len(result) == 1536
        assert all(isinstance(x, float) for x in result)
        assert result == vector


@pytest.mark.anyio
async def test_openai_embedding_malformed_responses():
    def make_service(payload) -> OpenAIEmbeddingService:
        transport = httpx.MockTransport(lambda req: httpx.Response(200, json=payload))
        client = httpx.AsyncClient(transport=transport)
        return OpenAIEmbeddingService(api_key="sk-test", client=client)

    # 1. Missing data
    with pytest.raises(ValueError, match="Response data must contain exactly one item"):
        await make_service({}).generate_embedding("hello")

    # 2. Empty data list
    with pytest.raises(ValueError, match="Response data must contain exactly one item"):
        await make_service({"data": []}).generate_embedding("hello")

    # 3. Multiple data items (strict cardinality contract: Option A)
    with pytest.raises(ValueError, match="Response data must contain exactly one item"):
        await make_service({"data": [{"embedding": []}, {"embedding": []}]}).generate_embedding("hello")

    # 4. Missing embedding field
    with pytest.raises(ValueError, match="Response item must contain an embedding field"):
        await make_service({"data": [{"another": []}]}).generate_embedding("hello")

    # 5. Null embedding
    with pytest.raises(ValueError, match="Embedding must be a sequence/list"):
        await make_service({"data": [{"embedding": None}]}).generate_embedding("hello")

    # 6. Non-list embedding
    with pytest.raises(ValueError, match="Embedding must be a sequence/list"):
        await make_service({"data": [{"embedding": "string"}]}).generate_embedding("hello")

    # 7. Wrong vector dimension (not 1536)
    with pytest.raises(ValueError, match="Embedding must be exactly 1536 dimensions"):
        await make_service({"data": [{"embedding": [0.1] * 100}]}).generate_embedding("hello")

    # 8. NaN element
    with pytest.raises(ValueError, match="Embedding elements must be finite numeric values"):
        vector_nan = [0.1] * 1535 + [float("nan")]
        await make_service({"data": [{"embedding": vector_nan}]}).generate_embedding("hello")

    # 9. Infinite element
    with pytest.raises(ValueError, match="Embedding elements must be finite numeric values"):
        vector_inf = [0.1] * 1535 + [float("inf")]
        await make_service({"data": [{"embedding": vector_inf}]}).generate_embedding("hello")

    # 10. Boolean element
    with pytest.raises(ValueError, match="Embedding elements must be finite numeric values"):
        vector_bool = [0.1] * 1535 + [True]
        await make_service({"data": [{"embedding": vector_bool}]}).generate_embedding("hello")

    # 11. String element
    with pytest.raises(ValueError, match="Embedding elements must be finite numeric values"):
        vector_str = [0.1] * 1535 + ["0.5"]
        await make_service({"data": [{"embedding": vector_str}]}).generate_embedding("hello")


@pytest.mark.anyio
async def test_openai_embedding_numeric_conversion_option_a():
    # Verify integers are accepted and converted to floats (Option A)
    vector = [1] * 1536
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"data": [{"embedding": vector}]}))
    async with httpx.AsyncClient(transport=transport) as client:
        service = OpenAIEmbeddingService(api_key="sk-test", client=client)
        result = await service.generate_embedding("hello")
        assert len(result) == 1536
        assert all(isinstance(x, float) for x in result)
        assert all(x == 1.0 for x in result)


@pytest.mark.anyio
async def test_openai_embedding_error_propagation():
    def make_error_service(status_code: int) -> OpenAIEmbeddingService:
        transport = httpx.MockTransport(lambda req: httpx.Response(status_code))
        client = httpx.AsyncClient(transport=transport)
        return OpenAIEmbeddingService(api_key="sk-test", client=client)

    # 1. HTTP 401 Authentication error
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await make_error_service(401).generate_embedding("hello")
    assert exc_info.value.response.status_code == 401

    # 2. HTTP 429 Rate limit error
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await make_error_service(429).generate_embedding("hello")
    assert exc_info.value.response.status_code == 429

    # 3. HTTP 500 Server error
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await make_error_service(500).generate_embedding("hello")
    assert exc_info.value.response.status_code == 500

    # 4. Timeout Exception
    def timeout_handler(request: httpx.Request):
        raise httpx.TimeoutException("Timeout")
    
    transport_timeout = httpx.MockTransport(timeout_handler)
    async with httpx.AsyncClient(transport=transport_timeout) as client_timeout:
        service_timeout = OpenAIEmbeddingService(api_key="sk-test", client=client_timeout)
        with pytest.raises(httpx.TimeoutException):
            await service_timeout.generate_embedding("hello")

    # 5. Connection Error
    def connect_handler(request: httpx.Request):
        raise httpx.ConnectError("Connection failed")
        
    transport_connect = httpx.MockTransport(connect_handler)
    async with httpx.AsyncClient(transport=transport_connect) as client_connect:
        service_connect = OpenAIEmbeddingService(api_key="sk-test", client=client_connect)
        with pytest.raises(httpx.ConnectError):
            await service_connect.generate_embedding("hello")
