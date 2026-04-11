"""Finalization helpers for ai-news-agent."""

from collections import defaultdict
from logging import Logger
from typing import Any

try:
    from config import PAPER_LIMIT
    from item_types import ResolvedItem
    from ranking import normalize_feed_mode, select_top_story_ids
except ModuleNotFoundError:  # pragma: no cover - module execution fallback
    from .config import PAPER_LIMIT
    from .item_types import ResolvedItem
    from .ranking import normalize_feed_mode, select_top_story_ids


def _sort_items_by_recency(items: list[ResolvedItem]) -> list[ResolvedItem]:
    return sorted(items, key=lambda item: item["published"], reverse=True)


def _limit_papers(items: list[ResolvedItem], *, limit: int) -> tuple[list[ResolvedItem], int]:
    paper_count = 0
    filtered_items: list[ResolvedItem] = []
    skipped_papers = 0

    for item in items:
        source_type = str(item.get("source_type", "")).lower()
        is_paper = source_type == "paper" or "papers" in str(item.get("source", "")).lower()
        if is_paper:
            if paper_count >= limit:
                skipped_papers += 1
                continue
            paper_count += 1
        filtered_items.append(item)

    return filtered_items, skipped_papers


def _filter_discovery_only_items(items: list[ResolvedItem]) -> tuple[list[ResolvedItem], int]:
    filtered_items = [
        item for item in items if normalize_feed_mode(item.get("feed_mode")) != "discovery_only"
    ]
    return filtered_items, len(items) - len(filtered_items)


def finalize_items(
    state: dict[str, Any],
    items: list[ResolvedItem],
    skipped_items: int,
    *,
    log_label: str,
    logger: Logger,
    paper_limit: int = PAPER_LIMIT,
) -> dict[str, Any]:
    sorted_items = _sort_items_by_recency(items)
    final_items, skipped_discovery = _filter_discovery_only_items(sorted_items)
    final_items, skipped_papers = _limit_papers(final_items, limit=paper_limit)

    if skipped_discovery:
        logger.info("Skipped %d discovery-only items before rendering", skipped_discovery)

    if skipped_papers:
        logger.info("Skipped %d additional papers (kept top %d)", skipped_papers, paper_limit)

    logger.info(
        "%s: %d items (skipped %d items)",
        log_label,
        len(final_items),
        skipped_items + skipped_discovery + skipped_papers,
    )

    categories: dict[str, int] = defaultdict(int)
    for item in final_items:
        categories[item.get("category", "Unknown")] += 1
    logger.info("Category distribution: %s", dict(categories))

    requested_top_stories = state.get("top_stories", [])
    if not isinstance(requested_top_stories, list):
        requested_top_stories = []
    state["top_stories"] = select_top_story_ids(final_items, requested_top_stories)
    state["items"] = final_items
    return state
