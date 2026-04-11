# src/filterer.py
"""Helpers for filtering collected news items."""

import re
from typing import Any

_NOISE_TITLE_PATTERNS = (
    re.compile(r"\bwebinar\b", re.IGNORECASE),
    re.compile(r"\bsponsored\b", re.IGNORECASE),
    re.compile(r"\badvertorial\b", re.IGNORECASE),
    re.compile(r"\bpartner content\b", re.IGNORECASE),
    re.compile(r"\bmolotov cocktail\b", re.IGNORECASE),
    re.compile(r"\bsam altman[’']?s (?:home|house)\b", re.IGNORECASE),
    re.compile(r"\bkeep a man happy\b", re.IGNORECASE),
    re.compile(r"\bmeme machine\b", re.IGNORECASE),
    re.compile(r"\blego cartoons?\b", re.IGNORECASE),
    re.compile(r"\bcredit their virality\b", re.IGNORECASE),
    re.compile(r"\blove-hate relationship with ai\b", re.IGNORECASE),
)
_NOISE_LINK_PATTERNS = (
    re.compile(r"/spons/", re.IGNORECASE),
    re.compile(r"/webinars?/", re.IGNORECASE),
)
_SOURCE_TITLE_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "TechCrunch": (
        re.compile(r"\bstartup battlefield\b", re.IGNORECASE),
        re.compile(r"\btechcrunch disrupt\b", re.IGNORECASE),
    ),
    "The Verge": (
        re.compile(r"\bvergecast\b", re.IGNORECASE),
        re.compile(r"\bfear and loathing at\b", re.IGNORECASE),
    ),
    "Wired AI": (
        re.compile(r"\bwill force a .* reckoning\b", re.IGNORECASE),
        re.compile(r"\bjust not the one you think\b", re.IGNORECASE),
        re.compile(r"\bgave me terrible advice\b", re.IGNORECASE),
        re.compile(r"\bpay up to talk\b", re.IGNORECASE),
    ),
}
_SOURCE_TITLE_LINK_PATTERNS: dict[str, tuple[tuple[re.Pattern[str], re.Pattern[str]], ...]] = {
    "The Verge": (
        (
            re.compile(r"\bvergecast\b", re.IGNORECASE),
            re.compile(r"/podcast/", re.IGNORECASE),
        ),
        (
            re.compile(r"\bfear and loathing at\b", re.IGNORECASE),
            re.compile(r"/podcast/", re.IGNORECASE),
        ),
    ),
}
_SOURCE_TITLE_REQUIRED_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "Simon Willison": (
        re.compile(
            r"\b(ai|chatgpt|gpt-?\d|llm|llms|openai|anthropic|claude|meta|gemini|gemma|mistral|glm|llama|qwen|deepseek|model|models|agents?|inference|prompts?|reasoning|multimodal|embeddings?)\b",
            re.IGNORECASE,
        ),
    ),
}
_SOURCE_LINK_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "OpenAI News": (
        re.compile(r"/academy/", re.IGNORECASE),
    ),
    "Apple Machine Learning Research": (
        re.compile(r"/updates/", re.IGNORECASE),
    ),
}


def deduplicate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return items keeping only the newest entry for each ``id``."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for it in sorted(items, key=lambda x: x["published"], reverse=True):
        if it["id"] in seen:
            continue
        seen.add(it["id"])
        out.append(it)
    return out


def exclude_noise(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Drop obviously low-signal editorial or sponsored titles."""
    filtered: list[dict[str, Any]] = []
    skipped = 0

    for item in items:
        source = str(item.get("source", "")).strip()
        title = str(item.get("title", "")).strip()
        link = str(item.get("link", "")).strip()
        if any(pattern.search(title) for pattern in _NOISE_TITLE_PATTERNS):
            skipped += 1
            continue
        if any(pattern.search(link) for pattern in _NOISE_LINK_PATTERNS):
            skipped += 1
            continue
        if any(pattern.search(title) for pattern in _SOURCE_TITLE_PATTERNS.get(source, ())):
            skipped += 1
            continue
        if any(
            title_pattern.search(title) and link_pattern.search(link)
            for title_pattern, link_pattern in _SOURCE_TITLE_LINK_PATTERNS.get(source, ())
        ):
            skipped += 1
            continue
        if any(pattern.search(link) for pattern in _SOURCE_LINK_PATTERNS.get(source, ())):
            skipped += 1
            continue
        required_title_patterns = _SOURCE_TITLE_REQUIRED_PATTERNS.get(source, ())
        if required_title_patterns and not any(
            pattern.search(title) for pattern in required_title_patterns
        ):
            skipped += 1
            continue
        filtered.append(item)

    return filtered, skipped
