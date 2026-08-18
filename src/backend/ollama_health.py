"""
ollama_health.py — Shared Ollama connectivity and model tier inspector.
Verifies server liveness and checks available model tags.
"""
import requests
from config import OLLAMA_BASE_URL, OLLAMA_TAGS_URL, MODEL_FAST, MODEL_MAIN, MODEL_FALLBACK

_ollama_available: bool | None = None
_available_models: list[str] | None = None


def check_ollama_available(ollama_url: str = "http://localhost:11434/api/generate") -> bool:
    """
    Performs a fast check against the Ollama API root.
    Returns True if Ollama responds within 2 seconds, False otherwise.
    Caches the result for the lifetime of the process.
    """
    global _ollama_available
    if _ollama_available is not None:
        return _ollama_available

    base_url = ollama_url.replace("/api/generate", "").replace("/api/chat", "")
    try:
        resp = requests.get(base_url, timeout=2.0)
        _ollama_available = resp.status_code < 500
    except Exception:
        _ollama_available = False

    status = "ONLINE" if _ollama_available else "OFFLINE"
    print(f"[LearnForge] Ollama health check: {status} ({base_url})")
    return _ollama_available


def get_available_models() -> list[str]:
    """Fetch all locally installed model tags from Ollama."""
    global _available_models
    if _available_models is not None:
        return _available_models

    _available_models = []
    try:
        resp = requests.get(OLLAMA_TAGS_URL, timeout=3.0)
        if resp.status_code == 200:
            models_data = resp.json().get("models", [])
            _available_models = [m.get("name", "") for m in models_data]
            print(f"[LearnForge] Local Ollama models: {_available_models}")
    except Exception:
        pass
    return _available_models


def resolve_model(preferred_model: str) -> str:
    """
    Resolves the best model to use.
    If preferred_model is pulled in Ollama, returns it.
    Otherwise falls back to MODEL_FALLBACK or whatever is installed.
    """
    models = get_available_models()
    if not models:
        return preferred_model

    # Check if preferred_model is directly present (or prefix matches)
    pref_base = preferred_model.split(":")[0].lower()
    for m in models:
        if m.lower() == preferred_model.lower() or m.lower().startswith(pref_base):
            return m

    # Check if fallback model is available
    fallback_base = MODEL_FALLBACK.split(":")[0].lower()
    for m in models:
        if fallback_base in m.lower():
            return m

    # Return first available model if any exists
    return models[0] if models else preferred_model


def reset_ollama_cache():
    """Call this if you want to re-check Ollama availability."""
    global _ollama_available, _available_models
    _ollama_available = None
    _available_models = None
