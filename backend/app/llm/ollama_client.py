import httpx
import asyncio
import json
from typing import AsyncGenerator, Optional, Dict, Any
from app.config import settings

class GeminiClient:
    TIMEOUT = 120.0

    @classmethod
    async def generate(cls, prompt: str, system: Optional[str] = None, format: Optional[str] = None) -> str:
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set in environment settings.")
        
        model = settings.GEMINI_MODEL
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        
        contents = [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ]
        
        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.3
            }
        }
        
        if system:
            payload["systemInstruction"] = {
                "parts": [{"text": system}]
            }
            
        if format == "json":
            payload["generationConfig"]["responseMimeType"] = "application/json"
            
        headers = {"Content-Type": "application/json"}
        
        async with httpx.AsyncClient(timeout=cls.TIMEOUT) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            res_data = response.json()
            try:
                return res_data["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError) as e:
                raise RuntimeError(f"Unexpected response structure from Gemini API: {res_data}. Error: {e}")

    @classmethod
    async def generate_stream(cls, prompt: str, system: Optional[str] = None, format: Optional[str] = None) -> AsyncGenerator[str, None]:
        api_key = settings.GEMINI_API_KEY
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is not set in environment settings.")
            
        model = settings.GEMINI_MODEL
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent?alt=sse&key={api_key}"
        
        contents = [
            {
                "role": "user",
                "parts": [{"text": prompt}]
            }
        ]
        
        payload: Dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": 0.3
            }
        }
        
        if system:
            payload["systemInstruction"] = {
                "parts": [{"text": system}]
            }
            
        if format == "json":
            payload["generationConfig"]["responseMimeType"] = "application/json"
            
        headers = {"Content-Type": "application/json"}
        
        async with httpx.AsyncClient(timeout=cls.TIMEOUT) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        json_str = line[len("data: "):]
                        try:
                            chunk = json.loads(json_str)
                            candidates = chunk.get("candidates", [])
                            if candidates:
                                text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                                if text:
                                    yield text
                        except json.JSONDecodeError:
                            continue


class OllamaClient:
    TIMEOUT = 120.0
    MAX_RETRIES = 3

    @classmethod
    def get_base_url(cls) -> str:
        return settings.OLLAMA_BASE_URL

    @classmethod
    def get_model(cls) -> str:
        return settings.OLLAMA_MODEL

    @classmethod
    async def _request_with_retry(cls, method: str, path: str, payload: Dict[str, Any], retries: int = None) -> httpx.Response:
        if retries is None:
            retries = cls.MAX_RETRIES

        url = f"{cls.get_base_url().rstrip('/')}{path}"
        backoff = 1.0
        
        async with httpx.AsyncClient(timeout=cls.TIMEOUT) as client:
            for attempt in range(retries):
                try:
                    if method.upper() == "POST":
                        response = await client.post(url, json=payload)
                    else:
                        response = await client.get(url)
                    response.raise_for_status()
                    return response
                except httpx.HTTPStatusError as e:
                    detail = ""
                    if e.response is not None:
                        try:
                            detail = e.response.text
                        except Exception:
                            detail = ""
                    if e.response is not None and e.response.status_code in {400, 404}:
                        raise RuntimeError(
                            f"Ollama rejected the request for model '{cls.get_model()}': {e}. "
                            f"Make sure the model is available and pulled with 'ollama pull {cls.get_model()}'."
                        ) from e
                    if attempt == retries - 1:
                        raise RuntimeError(f"Ollama API request failed after {retries} attempts: {e}") from e
                    print(f"Ollama connection attempt {attempt+1} failed. Retrying in {backoff}s...")
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
                except (httpx.HTTPError, httpx.NetworkError) as e:
                    if attempt == retries - 1:
                        raise RuntimeError(f"Ollama API request failed after {retries} attempts: {e}") from e
                    print(f"Ollama connection attempt {attempt+1} failed. Retrying in {backoff}s...")
                    await asyncio.sleep(backoff)
                    backoff *= 2.0
            raise RuntimeError("Ollama API request failed after retries.")

    @classmethod
    async def generate(cls, prompt: str, system: Optional[str] = None, format: Optional[str] = None) -> str:
        if settings.LLM_PROVIDER == "gemini":
            return await GeminiClient.generate(prompt, system, format)

        payload = {
            "model": cls.get_model(),
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_ctx": 2048,      # reduce context window
                "num_predict": 512,   # limit output tokens
                "temperature": 0.3    # lower = faster, more deterministic
            }
        }
        if system:
            payload["system"] = system
        if format:
            payload["format"] = format  # e.g., "json"

        response = await cls._request_with_retry("POST", "/api/generate", payload)
        response_data = response.json()
        return response_data.get("response", "")

    @classmethod
    async def generate_stream(cls, prompt: str, system: Optional[str] = None, format: Optional[str] = None) -> AsyncGenerator[str, None]:
        if settings.LLM_PROVIDER == "gemini":
            async for token in GeminiClient.generate_stream(prompt, system, format):
                yield token
            return

        url = f"{cls.get_base_url().rstrip('/')}/api/generate"
        payload = {
            "model": cls.get_model(),
            "prompt": prompt,
            "stream": True,
            "options": {
                "num_ctx": 2048,      # reduce context window
                "num_predict": 512,   # limit output tokens
                "temperature": 0.3    # lower = faster, more deterministic
            }
        }
        if system:
            payload["system"] = system
        if format:
            payload["format"] = format

        backoff = 1.0
        retries = cls.MAX_RETRIES
        
        # Try to connect, support simple streaming
        for attempt in range(retries):
            try:
                # We open a stream context
                async with httpx.AsyncClient(timeout=cls.TIMEOUT) as client:
                    async with client.stream("POST", url, json=payload) as response:
                        response.raise_for_status()
                        async for line in response.aiter_lines():
                            if not line.strip():
                                continue
                            try:
                                chunk = json.loads(line)
                                token = chunk.get("response", "")
                                if token:
                                    yield token
                            except json.JSONDecodeError:
                                continue
                return # Successfully completed stream
            except httpx.HTTPStatusError as e:
                if e.response is not None and e.response.status_code in {400, 404}:
                    raise RuntimeError(
                        f"Ollama rejected the streaming request for model '{cls.get_model()}': {e}. "
                        f"Make sure the model is available and pulled with 'ollama pull {cls.get_model()}'."
                    ) from e
                if attempt == retries - 1:
                    raise RuntimeError(f"Ollama streaming connection failed: {e}") from e
                print(f"Ollama stream attempt {attempt+1} failed. Retrying in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff *= 2.0
            except (httpx.HTTPError, httpx.NetworkError) as e:
                if attempt == retries - 1:
                    raise RuntimeError(f"Ollama streaming connection failed: {e}") from e
                print(f"Ollama stream attempt {attempt+1} failed. Retrying in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff *= 2.0
