from typing import Any

import httpx

from backend.app.core.config import get_settings

settings = get_settings()


def check_ollama_connection() -> dict[str, Any]:
    """Tests connectivity to Ollama server and checks model availability."""
    url = f"{settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags"
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                models: list[str] = [m.get("name", "") for m in data.get("models", [])]
                model_present = settings.OLLAMA_MODEL in models
                return {
                    "status": "connected",
                    "base_url": settings.OLLAMA_BASE_URL,
                    "target_model": settings.OLLAMA_MODEL,
                    "target_model_available": model_present,
                    "available_models": models,
                }
            else:
                return {
                    "status": "error",
                    "base_url": settings.OLLAMA_BASE_URL,
                    "status_code": resp.status_code,
                    "detail": resp.text,
                }
    except Exception as e:
        return {
            "status": "error",
            "base_url": settings.OLLAMA_BASE_URL,
            "error": str(e),
        }
