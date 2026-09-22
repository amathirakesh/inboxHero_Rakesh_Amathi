import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent

load_dotenv(
    BASE_DIR / ".env"
)


# --------------------------------------------------
# Provider selection
# --------------------------------------------------

LLM_PROVIDER = os.getenv(
    "LLM_PROVIDER",
    "ollama",
).lower()


# --------------------------------------------------
# Ollama
# --------------------------------------------------

OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434",
)

OLLAMA_MODEL = os.getenv(
    "OLLAMA_MODEL",
    "qwen2.5:3b",
)


# --------------------------------------------------
# Gemini
# --------------------------------------------------

GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY"
)

GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL"
)