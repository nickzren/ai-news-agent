"""
Centralized configuration for ai-news-agent
"""
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# Load .env before reading any environment variables
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_FILE)


def _get_env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value or default


def _get_env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {value!r}") from exc


# ── LLM Configuration ───────────────────────────────────────────
OPENAI_MODEL: str = _get_env_str("OPENAI_MODEL", "gpt-5-mini")
OPENAI_TIMEOUT_SECONDS: int = _get_env_int("OPENAI_TIMEOUT_SECONDS", 30)
OPENAI_RETRIES: int = _get_env_int("OPENAI_RETRIES", 2)
SHORTIFY_BATCH_SIZE: int = _get_env_int("SHORTIFY_BATCH_SIZE", 20)
DIGEST_OUTPUT_FILE: str = _get_env_str("DIGEST_OUTPUT_FILE", "news.md")

# ── Feed Limits ─────────────────────────────────────────────────
PAPER_LIMIT: int = _get_env_int("PAPER_LIMIT", 7)

# ── RSS Fetch Configuration ─────────────────────────────────────
RSS_TIMEOUT: int = _get_env_int("RSS_TIMEOUT", 10)
RSS_RETRIES: int = _get_env_int("RSS_RETRIES", 2)
RSS_MAX_WORKERS: int = _get_env_int("RSS_MAX_WORKERS", 8)
RSS_MAX_FEED_BYTES: int = _get_env_int("RSS_MAX_FEED_BYTES", 5_000_000)
RSS_USER_AGENT: str = "ai-news-agent/1.0 (+https://github.com/ai-news-agent)"

# ── Categories ──────────────────────────────────────────────────
CATEGORIES: List[str] = [
    "Breaking News",
    "Industry & Business",
    "Tools & Applications",
    "Research & Models",
    "Policy & Ethics",
    "Tutorials & Insights",
]

# Default fallback category for uncategorized items
DEFAULT_CATEGORY: str = "Industry & Business"

# ── Duplicate Detection ─────────────────────────────────────────
COMPANY_NAMES: List[str] = [
    "openai",
    "google",
    "microsoft",
    "meta",
    "anthropic",
    "amazon",
    "nvidia",
    "apple",
    "ibm",
    "deepmind",
    "hugging face",
    "stability",
    "mistral",
    "cohere",
]

# ── Logging ─────────────────────────────────────────────────────
LOG_LEVEL: str = _get_env_str("LOG_LEVEL", "INFO")
