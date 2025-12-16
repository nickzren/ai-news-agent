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
from pathlib import Path
from typing import TypedDict, List, Dict, Any

from langgraph.graph import StateGraph
from openai import OpenAI

from collector import collect_items
from config import (
    CATEGORIES,
    COMPANY_NAMES,
    DEFAULT_CATEGORY,
    OPENAI_MODEL,
    PAPER_LIMIT,
)
from filterer import deduplicate
from renderer import to_markdown

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# 1. Shared state definition
class DigestState(TypedDict, total=False):
    items: List[Dict]  # list of headline dicts
    markdown: str  # final rendered MD


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
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("No OPENAI_API_KEY found, skipping shortify")
        return state

    if not state.get("items"):
        logger.warning("No items to shortify")
        return state

    client = OpenAI(api_key=api_key)
    items = state["items"]

    # Batch shortify: process up to 20 items per API call
    BATCH_SIZE = 20
    shortified_count = 0

    for batch_start in range(0, len(items), BATCH_SIZE):
        batch = items[batch_start:batch_start + BATCH_SIZE]

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
            resp = client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
            )
            content = resp.choices[0].message.content
            response_text = content.strip() if content else ""
            lines = [line.strip() for line in response_text.split('\n') if line.strip()]

            # Remove any numbering from response lines (e.g., "1. Title" -> "Title")
            cleaned_lines = []
            for line in lines:
                # Remove leading numbers like "1." or "1:"
                cleaned = re.sub(r'^\d+[\.\):\-]\s*', '', line)
                cleaned_lines.append(cleaned)

            # Apply shortened titles
            for i, item in enumerate(batch):
                if i < len(cleaned_lines) and cleaned_lines[i]:
                    item["title"] = cleaned_lines[i]
                    shortified_count += 1
                else:
                    logger.debug(f"No shortened title for: {item['title'][:50]}")

        except Exception as exc:
            logger.warning(f"LLM batch error: {exc}")

    logger.info(f"Shortified {shortified_count}/{len(items)} items")
    return state


def _fallback_categorize(item: Dict[str, Any]) -> str:
    """Keyword-based fallback categorization."""
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
    api_key = os.getenv("OPENAI_API_KEY")

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
        client = OpenAI(api_key=api_key)

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

        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
        )

        # Parse categorization response
        content = resp.choices[0].message.content
        response_text = content.strip() if content else ""
        logger.debug("LLM categorization response received")

        lines = [line.strip() for line in response_text.split('\n') if line.strip()]

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

        # Second pass: Additional duplicate detection based on key terms
        seen_topics: dict[str, int] = {}
        seen_keywords: dict[str, int] = {}

        for i, item in enumerate(state["items"]):
            if item.get("skip"):
                continue

            title_lower = item["title"].lower()

            # Check for keyword-based duplicates (e.g., "word of the year", "slop")
            # Extract significant words for matching
            words = set(
                w for w in re.findall(r'\b\w+\b', title_lower)
                if len(w) > 3 and w not in [
                    "with", "from", "that", "this", "what", "about", "into",
                    "have", "been", "will", "would", "could", "should", "their",
                    "announces", "launches", "says", "year", "word", "named"
                ]
            )

            # Create a fingerprint from the most distinctive words
            if len(words) >= 3:
                # Sort to make fingerprint consistent
                fingerprint = "_".join(sorted(list(words)[:5]))
                if fingerprint in seen_keywords:
                    item["skip"] = True
                    item["skip_reason"] = "keyword duplicate"
                    logger.debug(f"Keyword duplicate found: {item['title'][:50]}")
                    continue
                seen_keywords[fingerprint] = i

            # Extract company/product names for duplicate detection
            for company in COMPANY_NAMES:
                if company in title_lower:
                    # Create a topic key without common words
                    key_words = [
                        w for w in title_lower.split()
                        if len(w) > 3 and w not in ["with", "from", "announces", "launches", "the", "and"]
                    ]
                    topic_key = f"{company}_{'_'.join(sorted(key_words[:3]))}"

                    if topic_key in seen_topics:
                        item["skip"] = True
                        item["skip_reason"] = "duplicate topic"
                        logger.debug(f"Additional duplicate found: {item['title'][:50]}")
                    else:
                        seen_topics[topic_key] = i
                    break

        # Third pass: Handle any remaining "All" category items
        for item in state["items"]:
            if item.get("category") == "All" and not item.get("skip"):
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
        logger.error(f"Categorization error: {exc}", exc_info=True)

        # Set fallback categories on error
        for item in state.get("items", []):
            item["category"] = _fallback_categorize(item)

    return state


def node_render(state: DigestState) -> DigestState:
    items = state.get("items", [])
    logger.info(f"Rendering {len(items)} items")
    markdown = to_markdown(items)
    Path("news.md").write_text(markdown, encoding="utf-8")
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
