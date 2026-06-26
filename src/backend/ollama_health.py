"""
Shared Ollama connectivity helper.
Call check_ollama_available() once per generation session.
"""
import requests

_ollama_available: bool | None = None  # None = not yet checked

def check_ollama_available(ollama_url: str = "http://localhost:11434/api/generate") -> bool:
    """
    Performs a fast HEAD/GET check against the Ollama API root.
    Returns True if Ollama responds within 2 seconds, False otherwise.
    Caches the result for the lifetime of the process (resets on server restart).
    """
    global _ollama_available
    if _ollama_available is not None:
        return _ollama_available

    base_url = ollama_url.replace("/api/generate", "")
    try:
        resp = requests.get(base_url, timeout=2.0)
        _ollama_available = resp.status_code < 500
    except Exception:
        _ollama_available = False

    status = "ONLINE" if _ollama_available else "OFFLINE"
    print(f"[LearnForge] Ollama health check: {status} ({base_url})")
    return _ollama_available


def reset_ollama_cache():
    """Call this if you want to re-check Ollama availability."""
    global _ollama_available
    _ollama_available = None
