import asyncio
import httpx
import pytest
from app.llm.ollama_client import OllamaClient


class DummyAsyncClient:
    def __init__(self, *args, **kwargs):
        self._args = args
        self._kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, json=None):
        request = httpx.Request("POST", url)
        response = httpx.Response(404, request=request, content=b'{"error":"model not found"}')
        raise httpx.HTTPStatusError("model not found", request=request, response=response)


def test_request_with_retry_raises_clear_error_for_missing_model(monkeypatch):
    monkeypatch.setattr("app.llm.ollama_client.httpx.AsyncClient", DummyAsyncClient)

    with pytest.raises(RuntimeError, match="model is available|pull"):
        asyncio.run(OllamaClient._request_with_retry("POST", "/api/generate", {"model": "test-model"}))
