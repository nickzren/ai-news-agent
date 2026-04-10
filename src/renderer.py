"""
Markdown renderer for ai-news-agent
"""
import logging
from collections import defaultdict
from typing import Any

try:
    from config import CATEGORIES
except ModuleNotFoundError:  # pragma: no cover - module execution fallback
    from .config import CATEGORIES

logger = logging.getLogger(__name__)
_CATEGORY_ORDER = [*CATEGORIES, "Other"]


def _render_item_line(item: dict[str, Any], *, bold: bool = False) -> list[str]:
    title = item["title"].strip()
    link_text = f"**[{title}]({item['link']})**" if bold else f"[{title}]({item['link']})"
    lines = [f"- {link_text} — {item['source']}"]

    summary_line = item.get("summary_line", "")
    if summary_line:
        lines.append(f"  _{summary_line}_")

    coverage_sources: list[str] = item.get("coverage_sources", [])
    if coverage_sources:
        total = len(coverage_sources) + 1
        named = ", ".join(coverage_sources[:2])
        lines.append(f"  Coverage: {total} sources ({named})")

    return lines


def to_markdown(
    items: list[dict[str, Any]],
    *,
    executive_summary: str = "",
    top_stories: list[str] | None = None,
) -> str:
    """Convert items to markdown, sorted by tier then recency within each category."""
    if not items:
        return "_No fresh AI headlines in the last 24 h._"

    if top_stories is None:
        top_stories = []

    lines = ["## Daily AI / LLM Headlines\n"]

    if executive_summary:
        for paragraph in executive_summary.split("\n"):
            paragraph = paragraph.strip()
            if paragraph:
                lines.append(f"> {paragraph}")
        lines.append("")

    if top_stories:
        prompt_id_lookup = {item.get("_prompt_id", ""): item for item in items}
        resolved = [prompt_id_lookup[sid] for sid in top_stories if sid in prompt_id_lookup]
        if resolved:
            lines.append("### Top Stories")
            for item in resolved:
                lines.extend(_render_item_line(item, bold=True))
            lines.append("")

    sections: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for it in items:
        cat = it.get("category", "Other")
        if cat not in CATEGORIES:
            cat = "Other"
        sections[cat].append(it)

    for cat in _CATEGORY_ORDER:
        if cat not in sections:
            continue
        lines.append(f"### {cat}")

        sorted_items = sorted(
            sections[cat],
            key=lambda x: (
                -(1 if x.get("tier") == "high" else 0),
                -x["published"].timestamp(),
                x["source"],
            ),
        )

        for i in sorted_items:
            lines.extend(_render_item_line(i))
        lines.append("")

    return "\n".join(lines)
