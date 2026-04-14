"""
Centralized configuration for ai-news-agent
"""
import os
from pathlib import Path

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
OPENAI_API_KEY: str = _get_env_str("OPENAI_API_KEY", "")
OPENAI_MODEL: str = _get_env_str("OPENAI_MODEL", "gpt-5-mini")
OPENAI_TIMEOUT_SECONDS: int = _get_env_int("OPENAI_TIMEOUT_SECONDS", 60)
OPENAI_RETRIES: int = _get_env_int("OPENAI_RETRIES", 2)
DIGEST_OUTPUT_FILE: str = _get_env_str("DIGEST_OUTPUT_FILE", "news.md")
DIGEST_STATUS_FILE: str = _get_env_str("DIGEST_STATUS_FILE", "digest-run-status.json")
DIGEST_ISSUE_REPO: str = _get_env_str("DIGEST_ISSUE_REPO", "nickzren/ai-news-agent")
DIGEST_ISSUE_LABEL: str = _get_env_str("DIGEST_ISSUE_LABEL", "ai-digest")
DIGEST_ISSUE_TITLE_PREFIX: str = _get_env_str("DIGEST_ISSUE_TITLE_PREFIX", "AI Headlines")
DIGEST_PUBLISH_WORKFLOW: str = _get_env_str("DIGEST_PUBLISH_WORKFLOW", "publish-digest.yml")
DIGEST_ACTIONS_REF: str = _get_env_str("DIGEST_ACTIONS_REF", "main")

# ── Feed Limits ─────────────────────────────────────────────────
PAPER_LIMIT: int = _get_env_int("PAPER_LIMIT", 7)
MAX_ITEMS_PER_SOURCE: int = _get_env_int("MAX_ITEMS_PER_SOURCE", 6)

# ── RSS Fetch Configuration ─────────────────────────────────────
RSS_TIMEOUT: int = _get_env_int("RSS_TIMEOUT", 10)
RSS_RETRIES: int = _get_env_int("RSS_RETRIES", 2)
RSS_MAX_WORKERS: int = _get_env_int("RSS_MAX_WORKERS", 8)
RSS_MAX_FEED_BYTES: int = _get_env_int("RSS_MAX_FEED_BYTES", 5_000_000)
RSS_USER_AGENT: str = "ai-news-agent/1.0 (+https://github.com/ai-news-agent)"

# ── Categories ──────────────────────────────────────────────────
CATEGORIES: list[str] = [
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
COMPANY_NAMES: list[str] = [
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
