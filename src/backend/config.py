"""
config.py — Centralized model tier and runtime configuration for LearnForge Edge AI.
Supports task-based tiered routing:
  - MODEL_FAST: lightweight model for topic naming, segment labeling, routing (e.g., LiquidAI/lfm2.5-350m)
  - MODEL_MAIN: main generation model for knowledge extraction, flashcards, quiz, RAG Q&A (e.g., LFM2.5-2.6B / llama3.2:1b)
"""
import os

# Base Ollama endpoints
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_URL = f"{OLLAMA_BASE_URL}/api/generate"
OLLAMA_CHAT_URL = f"{OLLAMA_BASE_URL}/api/chat"
OLLAMA_TAGS_URL = f"{OLLAMA_BASE_URL}/api/tags"

# Model Tier Strategy (override via environment variables in start.sh)
# Fast tier: topic titles, quality-gates (~400-700MB VRAM)
MODEL_FAST = os.environ.get("MODEL_FAST", "LiquidAI/lfm2.5-350m")

# Main tier: knowledge layer, flashcards, quiz, QA (~1.6-1.9GB VRAM)
MODEL_MAIN = os.environ.get("MODEL_MAIN", "LFM2.5-2.6B:Q4_K_M")

# Legacy / Universal fallback model identifier
MODEL_FALLBACK = os.environ.get("MODEL_FALLBACK", "llama3.2:1b")

# Runtime LLM Parameters (Jetson-tuned)
DEFAULT_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "4096"))
DEFAULT_TEMPERATURE = float(os.environ.get("OLLAMA_TEMPERATURE", "0.1"))
DEFAULT_NUM_PREDICT = int(os.environ.get("OLLAMA_NUM_PREDICT", "300"))
