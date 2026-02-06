"""
LangGraph pipeline for ai-news-agent

Flow:
    collect ─▶ filter ─▶ shortify ─▶ categorize ─▶ render
"""
from __future__ import annotations

import logging
import os
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import StateGraph
from openai import (
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    OpenAI,
    RateLimitError,
)
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

try:
    from collector import collect_items
    from config import (
        CATEGORIES,
        COMPANY_NAMES,
        DIGEST_OUTPUT_FILE,
        DEFAULT_CATEGORY,
        OPENAI_MODEL,
        OPENAI_RETRIES,
        OPENAI_TIMEOUT_SECONDS,
        PAPER_LIMIT,
        SHORTIFY_BATCH_SIZE,
    )
    from filterer import deduplicate
    from renderer import to_markdown
except ModuleNotFoundError:  # pragma: no cover - module execution fallback
    from .collector import collect_items
    from .config import (
        CATEGORIES,
        COMPANY_NAMES,
        DIGEST_OUTPUT_FILE,
        DEFAULT_CATEGORY,
        OPENAI_MODEL,
        OPENAI_RETRIES,
        OPENAI_TIMEOUT_SECONDS,
        PAPER_LIMIT,
        SHORTIFY_BATCH_SIZE,
    )
    from .filterer import deduplicate
    from .renderer import to_markdown

logger = logging.getLogger(__name__)


def _resolve_output_file(path_value: str) -> Path:
    output = Path(path_value)
    if output.is_absolute():
        return output
    return (Path(__file__).resolve().parent.parent / output).resolve()


_NEWS_FILE = _resolve_output_file(DIGEST_OUTPUT_FILE)
_DUPLICATE_STOP_WORDS = {
    "about",
    "after",
    "announces",
    "artificial",
    "been",
    "breaking",
    "from",
    "have",
    "into",
    "launches",
    "latest",
    "named",
    "says",
    "that",
    "their",
    "this",
    "what",
    "with",
    "word",
    "year",
}


# ──────────────────────────────────────────────────────────────
# 1. Shared state definition
class DigestState(TypedDict, total=False):
    items: list[dict[str, Any]]  # list of headline dicts
    markdown: str  # final rendered MD


def _log_openai_retry(retry_state) -> None:  # type: ignore[no-untyped-def]
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    logger.warning(
        "OpenAI request attempt %s failed, retrying: %s",
        retry_state.attempt_number,
        exc,
    )


@lru_cache(maxsize=1)
def _get_openai_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key, timeout=OPENAI_TIMEOUT_SECONDS)


@retry(
    stop=stop_after_attempt(OPENAI_RETRIES + 1),
    wait=wait_exponential(multiplier=1, min=1, max=20),
    retry=retry_if_exception_type(
        (APITimeoutError, APIConnectionError, RateLimitError, InternalServerError)
    ),
    before_sleep=_log_openai_retry,
    reraise=True,
)
def _chat_completion_text(client: OpenAI, prompt: str) -> str:
    response = client.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[{"role": "user", "content": prompt}],
    )
    content = response.choices[0].message.content
    return content.strip() if content else ""


def _strip_line_number(line: str) -> str:
    return re.sub(r"^\d+[\.\):\-]\s*", "", line).strip()


def _significant_tokens(title: str) -> set[str]:
    return {
        token
        for token in re.findall(r"\b[a-z0-9]+\b", title.lower())
        if len(token) > 3 and token not in _DUPLICATE_STOP_WORDS
    }


def _mentioned_company(title: str) -> str | None:
    title_lower = title.lower()
    for company in COMPANY_NAMES:
        company_name = str(company)
        if company_name in title_lower:
            return company_name
    return None


def _is_high_confidence_duplicate(
    existing: dict[str, Any],
    candidate: dict[str, Any],
) -> bool:
    existing_tokens = _significant_tokens(existing.get("title", ""))
    candidate_tokens = _significant_tokens(candidate.get("title", ""))
    if len(existing_tokens) < 4 or len(candidate_tokens) < 4:
        return False

    overlap = existing_tokens & candidate_tokens
    if len(overlap) < 4:
        return False

    overlap_ratio = len(overlap) / min(len(existing_tokens), len(candidate_tokens))
    existing_company = _mentioned_company(existing.get("title", ""))
    candidate_company = _mentioned_company(candidate.get("title", ""))

    if existing_company or candidate_company:
        if existing_company != candidate_company:
            return False
        return overlap_ratio >= 0.8

    return overlap_ratio >= 0.9 and len(overlap) >= 5


# ──────────────────────────────────────────────────────────────
# 2. Nodes
def node_collect(state: DigestState) -> DigestState:
    items = collect_items()
    logger.info(f"Collected {len(items)} items")
    state["items"] = items
    return state


def node_filter(state: DigestState) -> DigestState:
    items = deduplicate(state.get("items", []))

    # Limit papers to avoid overwhelming the digest
    paper_count = 0
    filtered_items = []
    skipped_papers = 0

    for item in sorted(items, key=lambda x: x["published"], reverse=True):
        if "Papers" in item.get("source", "") and paper_count >= PAPER_LIMIT:
            logger.debug(f"Skipping paper: {item['title'][:50]}...")
            skipped_papers += 1
            continue
        if "Papers" in item.get("source", ""):
            paper_count += 1
        filtered_items.append(item)

    logger.info(f"After deduplication: {len(items)} items")
    if skipped_papers > 0:
        logger.info(f"Skipped {skipped_papers} additional papers (kept top {PAPER_LIMIT})")
    logger.info(f"After limiting papers: {len(filtered_items)} items")
    state["items"] = filtered_items
    return state


def node_shortify(state: DigestState) -> DigestState:
    """Shorten titles to ≤10 words for cleaner digest and better duplicate detection."""
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        logger.warning("No OPENAI_API_KEY found, skipping shortify")
        return state

    if not state.get("items"):
        logger.warning("No items to shortify")
        return state

    client = _get_openai_client(api_key)
    items = state["items"]
    shortified_count = 0

    for batch_start in range(0, len(items), SHORTIFY_BATCH_SIZE):
        batch = items[batch_start:batch_start + SHORTIFY_BATCH_SIZE]

        # Create numbered list of titles
        titles_text = "\n".join([
            f"{i + 1}. {item['title']}"
            for i, item in enumerate(batch)
        ])

        prompt = f"""Rewrite each headline in ≤10 words, keep the core idea.
Return one shortened headline per line, in the same order.

Headlines:
{titles_text}

Shortened (one per line, {len(batch)} lines total):"""

        try:
            response_text = _chat_completion_text(client, prompt)
            lines = [line.strip() for line in response_text.split("\n") if line.strip()]

            # Remove any numbering from response lines (e.g., "1. Title" -> "Title")
            cleaned_lines = [_strip_line_number(line) for line in lines]

            # Apply shortened titles
            if len(cleaned_lines) != len(batch):
                logger.warning(
                    "Shortify line mismatch for batch [%s:%s]: expected %s, got %s",
                    batch_start,
                    batch_start + len(batch),
                    len(batch),
                    len(cleaned_lines),
                )

            for i, item in enumerate(batch):
                if i < len(cleaned_lines) and cleaned_lines[i]:
                    item["title"] = cleaned_lines[i]
                    shortified_count += 1
                else:
                    logger.warning("No shortened title for: %s", item["title"][:80])

        except Exception as exc:
            logger.warning(
                "LLM shortify batch error [%s:%s]: %s",
                batch_start,
                batch_start + len(batch),
                exc,
            )

    logger.info(f"Shortified {shortified_count}/{len(items)} items")
    return state


def _fallback_categorize(item: dict[str, Any]) -> str:
    """Keyword-based fallback categorization."""
    category_hint = item.get("category")
    if isinstance(category_hint, str) and category_hint in CATEGORIES:
        return category_hint

    title = item.get("title", "").lower()
    source = item.get("source", "").lower()

    # Source-based categorization first
    if "papers" in source:
        return "Research & Models"

    # Keyword-based categorization
    if any(word in title for word in ["lawsuit", "court", "legal", "copyright", "safety", "regulation", "ban"]):
        return "Policy & Ethics"
    if any(word in title for word in ["paper", "research", "model", "benchmark", "beats", "arxiv", "study"]):
        return "Research & Models"
    if any(word in title for word in ["launch", "release", "tool", "api", "feature", "app", "plugin"]):
        return "Tools & Applications"
    if any(word in title for word in ["raise", "funding", "$", "acquire", "valuation", "ipo", "billion", "million"]):
        return "Industry & Business"
    if any(word in title for word in ["how", "guide", "tutorial", "should", "opinion", "why", "lesson"]):
        return "Tutorials & Insights"
    if any(word in title for word in ["announce", "unveil", "reveal", "breaking", "just"]):
        return "Breaking News"

    return str(DEFAULT_CATEGORY)


def node_categorize(state: DigestState) -> DigestState:
    """Use LLM to categorize items and identify duplicates."""
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()

    # If no API key, use fallback categorization
    if not api_key:
        logger.warning("No OPENAI_API_KEY found, using fallback categorization")
        for item in state.get("items", []):
            item["category"] = _fallback_categorize(item)
        return state

    if not state.get("items"):
        logger.warning("No items to categorize")
        return state

    try:
        client = _get_openai_client(api_key)

        # Create item list with shortened titles
        items_text = "\n".join([
            f"{i + 1}. {item['title']} — {item['source']}"
            for i, item in enumerate(state["items"])
        ])

        categories_str = "\n".join([f"- {cat}" for cat in CATEGORIES])

        prompt = f"""Analyze these AI news headlines for duplicates and categorization.

CRITICAL DUPLICATE DETECTION:
Look for stories about the SAME EVENT even if worded differently:
- "OpenAI launches X" = "X released by OpenAI" = "New X from OpenAI"
- "Google announces Y" = "Y unveiled by Google" = "Google's new Y"
- "Model Z beats benchmark" = "Z achieves state-of-art" = "New record by Z"
- "Company raises $X" = "X funding for Company" = "Company valued at Y"
- Same paper/research from different sources

Mark ALL BUT ONE as SKIP for each duplicate group. Keep the most informative version.

CATEGORIES:
{categories_str}

Items:
{items_text}

For each item, respond with ONLY:
- The category name (if keeping)
- SKIP (if duplicate)

One per line, {len(state['items'])} lines total. Be VERY aggressive marking duplicates."""

        # Parse categorization response
        response_text = _chat_completion_text(client, prompt)
        logger.debug("LLM categorization response received")

        lines = [_strip_line_number(line) for line in response_text.split("\n") if line.strip()]

        # Validate response line count
        expected_count = len(state["items"])
        actual_count = len(lines)

        if actual_count != expected_count:
            logger.warning(
                f"LLM response line mismatch: expected {expected_count}, got {actual_count}. "
                "Using fallback for unmatched items."
            )

        # First pass: LLM categorization
        for i, item in enumerate(state["items"]):
            if i < len(lines):
                line = lines[i]

                # Check for SKIP
                if "SKIP" in line.upper():
                    item["skip"] = True
                    item["skip_reason"] = "duplicate"
                    continue

                # Check for exact category match
                category_found = False
                for valid_cat in CATEGORIES:
                    if valid_cat.lower() in line.lower():
                        item["category"] = valid_cat
                        category_found = True
                        break

                # If no valid category found in LLM response, use fallback
                if not category_found:
                    item["category"] = _fallback_categorize(item)
                    logger.debug(f"Fallback categorization for: {item['title'][:50]}")
            else:
                # LLM didn't provide enough lines, use fallback
                item["category"] = _fallback_categorize(item)
                logger.debug(f"Missing LLM response, fallback for: {item['title'][:50]}")

        # Second pass: High-confidence duplicate detection only
        kept_items: list[dict[str, Any]] = []
        for item in state["items"]:
            if item.get("skip"):
                continue

            duplicate = any(
                _is_high_confidence_duplicate(existing, item) for existing in kept_items
            )
            if duplicate:
                item["skip"] = True
                item["skip_reason"] = "high-overlap duplicate"
                logger.debug("High-overlap duplicate found: %s", item["title"][:80])
                continue

            kept_items.append(item)

        # Third pass: Handle any remaining "All" category items
        for item in state["items"]:
            if item.get("skip"):
                continue
            if item.get("category") == "All" or item.get("category") not in CATEGORIES:
                item["category"] = _fallback_categorize(item)
                logger.debug(f"Reassigned 'All' category for: {item['title'][:50]}")

        # Remove skipped items
        original_count = len(state["items"])
        state["items"] = [item for item in state["items"] if not item.get("skip")]

        logger.info(
            f"After categorization: {len(state['items'])} items "
            f"(skipped {original_count - len(state['items'])} duplicates)"
        )

        # Debug: show categories assigned
        cats: dict[str, int] = defaultdict(int)
        for item in state["items"]:
            cats[item.get("category", "Unknown")] += 1
        logger.info(f"Category distribution: {dict(cats)}")

    except Exception as exc:
        logger.error(
            "Categorization error: %s. Falling back to keyword categorization.",
            exc,
        )

        # Set fallback categories on error
        for item in state.get("items", []):
            item["category"] = _fallback_categorize(item)

    return state


def node_render(state: DigestState) -> DigestState:
    items = state.get("items", [])
    logger.info(f"Rendering {len(items)} items")
    markdown = to_markdown(items)
    _NEWS_FILE.write_text(markdown, encoding="utf-8")
    state["markdown"] = markdown
    return state


# ──────────────────────────────────────────────────────────────
# 3. Build LangGraph
def build_graph():
    g = StateGraph(DigestState)

    g.add_node("collect", node_collect)
    g.add_node("filter", node_filter)
    g.add_node("shortify", node_shortify)
    g.add_node("categorize", node_categorize)
    g.add_node("render", node_render)

    g.set_entry_point("collect")
    g.add_edge("collect", "filter")
    g.add_edge("filter", "shortify")
    g.add_edge("shortify", "categorize")
    g.add_edge("categorize", "render")

    return g.compile()
