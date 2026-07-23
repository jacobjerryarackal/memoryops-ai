import os
import math
import pytest
import httpx
import anyio
from typing import List

from app.services import (
    EmbeddingService,
    GeminiEmbeddingService,
    FallbackEmbeddingService,
    get_embedding_service,
    OpenAIEmbeddingService,
)


# --- Gemini Embedding Service Tests ---

def test_gemini_embedding_constructor_key_resolution(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    # 1. Explicit key
    service_explicit = GeminiEmbeddingService(api_key="gemini-explicit-key")
    assert service_explicit._api_key == "gemini-explicit-key"

    # 2. Environment key fallback
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-env-key")
    service_env = GeminiEmbeddingService()
    assert service_env._api_key == "gemini-env-key"

    # 3. Missing key raises on invocation
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    service_missing = GeminiEmbeddingService()
    assert service_missing._api_key is None
    
    with pytest.raises(ValueError, match="Gemini API key must be provided"):
        anyio.run(service_missing.generate_embedding, "test")

    # 4. Whitespace-only key behaves similarly
    service_whitespace = GeminiEmbeddingService(api_key="   ")
    assert service_whitespace._api_key is None
    
    with pytest.raises(ValueError, match="Gemini API key must be provided"):
        anyio.run(service_whitespace.generate_embedding, "test")


def test_gemini_embedding_constructor_timeout_validation():
    # Valid timeout
    service = GeminiEmbeddingService(api_key="gemini-test", timeout_seconds=5.5)
    assert service._timeout == 5.5

    # Invalid timeout types/values
    for invalid in [0, -1, -5.5, float("inf"), float("-inf"), float("nan"), True, "10"]:
        with pytest.raises(ValueError, match="timeout_seconds must be a finite positive number"):
            GeminiEmbeddingService(api_key="gemini-test", timeout_seconds=invalid)


@pytest.mark.anyio
async def test_gemini_embedding_input_validation():
    service = GeminiEmbeddingService(api_key="gemini-test")

    # 1. Empty string
    with pytest.raises(ValueError, match="text input cannot be empty or whitespace-only"):
        await service.generate_embedding("")

    # 2. Whitespace-only string
    with pytest.raises(ValueError, match="text input cannot be empty or whitespace-only"):
        await service.generate_embedding("    ")


@pytest.mark.anyio
async def test_gemini_embedding_successful_response():
    # Gemini text-embedding-004 yields 768 dimensions
    vector = [0.1] * 768
    mock_payload = {
        "embedding": {
            "values": vector
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent"
        assert request.method == "POST"
        assert request.headers["x-goog-api-key"] == "gemini-test"
        assert request.headers["Content-Type"] == "application/json"
        
        # Verify body payload: preserving input
        import json
        body = json.loads(request.read())
        assert body["content"]["parts"][0]["text"] == "  Hello World  "

        return httpx.Response(200, json=mock_payload)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        service = GeminiEmbeddingService(api_key="gemini-test", client=client)
        result = await service.generate_embedding("  Hello World  ")
        
        assert isinstance(result, list)
        # Verify padded size
        assert len(result) == 1536
        assert all(isinstance(x, float) for x in result)
        # Verify first 768 dimensions are original, next 768 are 0.0
        assert result[:768] == vector
        assert result[768:] == [0.0] * 768


@pytest.mark.anyio
async def test_gemini_embedding_numeric_conversion():
    # Verify integers are accepted and converted to floats
    vector = [1] * 768
    mock_payload = {"embedding": {"values": vector}}
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=mock_payload))
    async with httpx.AsyncClient(transport=transport) as client:
        service = GeminiEmbeddingService(api_key="gemini-test", client=client)
        result = await service.generate_embedding("hello")
        assert len(result) == 1536
        assert all(isinstance(x, float) for x in result)
        assert all(x == 1.0 for x in result[:768])
        assert all(x == 0.0 for x in result[768:])


@pytest.mark.anyio
async def test_gemini_embedding_malformed_responses():
    def make_service(payload) -> GeminiEmbeddingService:
        transport = httpx.MockTransport(lambda req: httpx.Response(200, json=payload))
        client = httpx.AsyncClient(transport=transport)
        return GeminiEmbeddingService(api_key="gemini-test", client=client)

    # 1. Non-dict response payload
    with pytest.raises(ValueError, match="Response payload must be a JSON object"):
        await make_service([]).generate_embedding("hello")

    # 2. Missing embedding key
    with pytest.raises(ValueError, match="Response must contain an embedding object"):
        await make_service({}).generate_embedding("hello")

    # 3. Non-dict embedding
    with pytest.raises(ValueError, match="Response must contain an embedding object"):
        await make_service({"embedding": []}).generate_embedding("hello")

    # 4. Missing values key
    with pytest.raises(ValueError, match="values must be a sequence/list"):
        await make_service({"embedding": {}}).generate_embedding("hello")

    # 5. Non-list values
    with pytest.raises(ValueError, match="values must be a sequence/list"):
        await make_service({"embedding": {"values": "string"}}).generate_embedding("hello")

    # 6. Wrong vector dimension (not 768)
    with pytest.raises(ValueError, match="Gemini native embedding must be exactly 768 dimensions"):
        await make_service({"embedding": {"values": [0.1] * 100}}).generate_embedding("hello")

    # 7. NaN element
    with pytest.raises(ValueError, match="Embedding elements must be finite numeric values"):
        vector_nan = [0.1] * 767 + [float("nan")]
        await make_service({"embedding": {"values": vector_nan}}).generate_embedding("hello")

    # 8. Infinite element
    with pytest.raises(ValueError, match="Embedding elements must be finite numeric values"):
        vector_inf = [0.1] * 767 + [float("inf")]
        await make_service({"embedding": {"values": vector_inf}}).generate_embedding("hello")

    # 9. Boolean element
    with pytest.raises(ValueError, match="Embedding elements must be finite numeric values"):
        vector_bool = [0.1] * 767 + [True]
        await make_service({"embedding": {"values": vector_bool}}).generate_embedding("hello")

    # 10. String element
    with pytest.raises(ValueError, match="Embedding elements must be finite numeric values"):
        vector_str = [0.1] * 767 + ["0.5"]
        await make_service({"embedding": {"values": vector_str}}).generate_embedding("hello")


@pytest.mark.anyio
async def test_gemini_embedding_error_propagation():
    def make_error_service(status_code: int) -> GeminiEmbeddingService:
        transport = httpx.MockTransport(lambda req: httpx.Response(status_code))
        client = httpx.AsyncClient(transport=transport)
        return GeminiEmbeddingService(api_key="gemini-test", client=client)

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
        service_timeout = GeminiEmbeddingService(api_key="gemini-test", client=client_timeout)
        with pytest.raises(httpx.TimeoutException):
            await service_timeout.generate_embedding("hello")


# --- Fallback Embedding Service Tests ---

@pytest.mark.anyio
async def test_fallback_embedding_service():
    service = FallbackEmbeddingService()
    assert isinstance(service, EmbeddingService)

    # Rejects empty text
    with pytest.raises(ValueError, match="text input cannot be empty or whitespace-only"):
        await service.generate_embedding("   ")

    # Raises RuntimeError on valid invocation
    with pytest.raises(RuntimeError, match="Offline fallback mode is explicitly configured"):
        await service.generate_embedding("hello")


# --- Embedding Factory Tests ---

def test_embedding_factory_resolution(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-mock-key")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-mock-key")

    # 1. Default (when environment is unset, should yield OpenAI)
    monkeypatch.delenv("EMBEDDING_PROVIDER", raising=False)
    service_default = get_embedding_service()
    assert isinstance(service_default, OpenAIEmbeddingService)

    # 2. OpenAI explicit env
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    service_openai = get_embedding_service()
    assert isinstance(service_openai, OpenAIEmbeddingService)

    # 3. Gemini env
    monkeypatch.setenv("EMBEDDING_PROVIDER", "gemini")
    service_gemini = get_embedding_service()
    assert isinstance(service_gemini, GeminiEmbeddingService)

    # 4. Fallback env
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fallback")
    service_fallback = get_embedding_service()
    assert isinstance(service_fallback, FallbackEmbeddingService)

    # 5. Case-insensitivity and whitespace trimming
    monkeypatch.setenv("EMBEDDING_PROVIDER", "  GeMiNi  ")
    service_case = get_embedding_service()
    assert isinstance(service_case, GeminiEmbeddingService)

    # 6. Explicit parameter overrides env selection
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    service_param = get_embedding_service(provider="fallback")
    assert isinstance(service_param, FallbackEmbeddingService)

    # 7. Unsupported configuration throws ValueError
    monkeypatch.setenv("EMBEDDING_PROVIDER", "xai")  # xai is deferred/unsupported
    with pytest.raises(ValueError, match="Unsupported embedding provider"):
        get_embedding_service()

    # 8. Complete garbage value throws ValueError
    monkeypatch.setenv("EMBEDDING_PROVIDER", "garbage_provider")
    with pytest.raises(ValueError, match="Unsupported embedding provider"):
        get_embedding_service()
