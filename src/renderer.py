"""
Markdown renderer for ai-news-agent
"""
import logging
from collections import defaultdict

from config import CATEGORIES

logger = logging.getLogger(__name__)


def to_markdown(items):
    """Convert items to markdown, sorted by recency within each category."""
    if not items:
        return "_No fresh AI headlines in the last 24 h._"

    sections = defaultdict(list)
    for it in items:
        cat = it.get("category", "Other")
        # Map unknown categories to "Other"
        if cat not in CATEGORIES:
            cat = "Other"
        sections[cat].append(it)

    lines = ["## Daily AI / LLM Headlines\n"]

    # Use categories from config, plus "Other" as fallback
    category_order = CATEGORIES + ["Other"]

    for cat in category_order:
        if cat not in sections:
            continue
        lines.append(f"### {cat}")

        # Sort items by date (newest first), then by source alphabetically as tiebreaker
        sorted_items = sorted(
            sections[cat],
            key=lambda x: (-x['published'].timestamp(), x['source'])
        )

        for i in sorted_items:
            title = i["title"].strip()
            lines.append(f"- [{title}]({i['link']}) — {i['source']}")
        lines.append("")  # blank line

    return "\n".join(lines)
