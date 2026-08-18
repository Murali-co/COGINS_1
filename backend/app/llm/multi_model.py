"""
Multi-model support for COGNIS
Allows users to select different Ollama models for LLM tasks
"""

import aiohttp
from app.config import settings

class MultiModelManager:
    """Manages available models and user model preferences"""
    
    @staticmethod
    async def get_available_models():
        """Fetch available models from Ollama"""
        if settings.LLM_PROVIDER == "gemini":
            return [
                {
                    "name": settings.GEMINI_MODEL,
                    "digest": "gemini",
                    "size": 0,
                    "modified_at": "cloud",
                }
            ]

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{settings.OLLAMA_BASE_URL}/api/tags") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = data.get("models", [])
                        return [
                            {
                                "name": m.get("name"),
                                "digest": m.get("digest"),
                                "size": m.get("size"),
                                "modified_at": m.get("modified_at"),
                            }
                            for m in models
                        ]
        except Exception as e:
            print(f"Error fetching models from Ollama: {e}")
        
        # Fallback: return default model
        return [
            {
                "name": settings.OLLAMA_MODEL,
                "digest": "unknown",
                "size": 0,
                "modified_at": "unknown",
            }
        ]
    
    @staticmethod
    async def get_model_info(model_name: str):
        """Get details about a specific model"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{settings.OLLAMA_BASE_URL}/api/show",
                    json={"name": model_name}
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            print(f"Error fetching model info: {e}")
        
        return None
    
    @staticmethod
    def get_default_model():
        """Get the default model from config"""
        return settings.OLLAMA_MODEL
    
    @staticmethod
    def get_recommended_models():
        """Get list of recommended models for different tasks"""
        return {
            "general": [
                {"name": "qwen2.5:7b", "description": "Fast, balanced model", "speed": "fast", "quality": "medium"},
                {"name": "llama2:7b", "description": "Classic, reliable model", "speed": "medium", "quality": "good"},
                {"name": "mistral:7b", "description": "Efficient, good reasoning", "speed": "fast", "quality": "good"},
            ],
            "conversation": [
                {"name": "neural-chat:7b", "description": "Optimized for chat", "speed": "fast", "quality": "excellent"},
                {"name": "openchat:7b", "description": "Conversational AI", "speed": "fast", "quality": "good"},
            ],
            "creative": [
                {"name": "dolphin-mixtral:8x7b", "description": "Creative, powerful", "speed": "slow", "quality": "excellent"},
                {"name": "wizard-vicuna-uncensored:13b", "description": "Unrestricted writing", "speed": "slow", "quality": "very_good"},
            ],
            "fast": [
                {"name": "qwen2.5:7b", "description": "Fastest option", "speed": "very_fast", "quality": "medium"},
                {"name": "phi:3.5b", "description": "Tiny, mobile-friendly", "speed": "very_fast", "quality": "poor"},
            ],
        }
