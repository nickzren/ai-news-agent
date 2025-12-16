"""Tests for filterer module."""
from datetime import datetime, timezone

from filterer import deduplicate


def test_deduplicate_empty():
    """Test deduplicate with empty list."""
    assert deduplicate([]) == []


def test_deduplicate_no_duplicates():
    """Test deduplicate when there are no duplicates."""
    items = [
        {"id": "a", "published": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)},
        {"id": "b", "published": datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)},
        {"id": "c", "published": datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)},
    ]
    result = deduplicate(items)
    assert len(result) == 3
    assert [item["id"] for item in result] == ["a", "b", "c"]


def test_deduplicate_keeps_newest():
    """Test that deduplicate keeps the newest item when duplicates exist."""
    items = [
        {"id": "a", "published": datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc), "source": "old"},
        {"id": "a", "published": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc), "source": "new"},
        {"id": "b", "published": datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)},
    ]
    result = deduplicate(items)
    assert len(result) == 2

    # Find the item with id "a" and verify it's the newer one
    item_a = next(item for item in result if item["id"] == "a")
    assert item_a["source"] == "new"


def test_deduplicate_preserves_order_by_date():
    """Test that results are sorted by published date (newest first)."""
    items = [
        {"id": "c", "published": datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)},
        {"id": "a", "published": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)},
        {"id": "b", "published": datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)},
    ]
    result = deduplicate(items)
    assert [item["id"] for item in result] == ["a", "b", "c"]


def test_deduplicate_multiple_duplicates():
    """Test with multiple duplicate groups."""
    items = [
        {"id": "a", "published": datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)},
        {"id": "a", "published": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)},
        {"id": "a", "published": datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)},
        {"id": "b", "published": datetime(2024, 1, 1, 9, 0, tzinfo=timezone.utc)},
        {"id": "b", "published": datetime(2024, 1, 1, 13, 0, tzinfo=timezone.utc)},
    ]
    result = deduplicate(items)
    assert len(result) == 2
    assert [item["id"] for item in result] == ["b", "a"]
