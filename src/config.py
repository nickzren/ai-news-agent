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

# ── LLM Configuration ───────────────────────────────────────────
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# ── Feed Limits ─────────────────────────────────────────────────
PAPER_LIMIT: int = int(os.getenv("PAPER_LIMIT", "7"))

# ── RSS Fetch Configuration ─────────────────────────────────────
RSS_TIMEOUT: int = int(os.getenv("RSS_TIMEOUT", "10"))
RSS_RETRIES: int = int(os.getenv("RSS_RETRIES", "2"))
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
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
