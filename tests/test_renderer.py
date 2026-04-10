"""Tests for renderer module."""
from datetime import datetime, timezone

from renderer import to_markdown


def test_to_markdown_empty():
    """Test to_markdown with empty list."""
    result = to_markdown([])
    assert result == "_No fresh AI headlines in the last 24 h._"


def test_to_markdown_single_item():
    """Test to_markdown with a single item."""
    items = [
        {
            "title": "Test Headline",
            "link": "https://example.com/article",
            "source": "Test Source",
            "category": "Breaking News",
            "published": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        }
    ]
    result = to_markdown(items)
    assert "## Daily AI / LLM Headlines" in result
    assert "### Breaking News" in result
    assert "[Test Headline](https://example.com/article)" in result
    assert "Test Source" in result


def test_to_markdown_multiple_categories():
    """Test to_markdown groups items by category correctly."""
    items = [
        {
            "title": "Breaking Item",
            "link": "https://example.com/1",
            "source": "Source A",
            "category": "Breaking News",
            "published": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        },
        {
            "title": "Research Item",
            "link": "https://example.com/2",
            "source": "Source B",
            "category": "Research & Models",
            "published": datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc),
        },
    ]
    result = to_markdown(items)
    assert "### Breaking News" in result
    assert "### Research & Models" in result
    # Breaking News should appear before Research & Models
    assert result.index("Breaking News") < result.index("Research & Models")


def test_to_markdown_sorted_by_recency():
    """Test that items within a category are sorted by recency."""
    items = [
        {
            "title": "Older Item",
            "link": "https://example.com/1",
            "source": "Source A",
            "category": "Breaking News",
            "published": datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
        },
        {
            "title": "Newer Item",
            "link": "https://example.com/2",
            "source": "Source A",
            "category": "Breaking News",
            "published": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        },
    ]
    result = to_markdown(items)
    # Newer item should appear before older item
    assert result.index("Newer Item") < result.index("Older Item")


def test_to_markdown_prefers_primary_source_over_newer_commentary_when_tier_matches():
    items = [
        {
            "title": "Commentary take",
            "link": "https://example.com/1",
            "source": "Newsletter",
            "source_role": "commentary",
            "category": "Breaking News",
            "published": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        },
        {
            "title": "Official announcement",
            "link": "https://example.com/2",
            "source": "OpenAI News",
            "source_role": "primary",
            "category": "Breaking News",
            "published": datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc),
        },
    ]

    result = to_markdown(items)
    assert result.index("Official announcement") < result.index("Commentary take")


def test_to_markdown_unknown_category_goes_to_other():
    """Test that items with unknown category go to Other section."""
    items = [
        {
            "title": "Unknown Category Item",
            "link": "https://example.com/1",
            "source": "Source A",
            "category": "Unknown Category",
            "published": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        },
    ]
    result = to_markdown(items)
    # Should not crash, item goes to "Other" or its own category
    assert "Unknown Category Item" in result


def test_to_markdown_strips_title_whitespace():
    """Test that titles with whitespace are stripped."""
    items = [
        {
            "title": "  Whitespace Title  ",
            "link": "https://example.com/1",
            "source": "Source",
            "category": "Breaking News",
            "published": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        },
    ]
    result = to_markdown(items)
    assert "[Whitespace Title]" in result
    assert "[  Whitespace Title  ]" not in result


def test_to_markdown_uses_compact_lines_without_summary_text():
    items = [
        {
            "title": "Compact Item",
            "link": "https://example.com/1",
            "source": "Source A",
            "category": "Breaking News",
            "summary_line": "This should not be rendered.",
            "coverage_sources": ["Source B", "Source C"],
            "published": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        },
    ]

    result = to_markdown(items, executive_summary="Long summary that should stay hidden.")
    assert "This should not be rendered." not in result
    assert "Long summary that should stay hidden." not in result
    assert "- [Compact Item](https://example.com/1) — Source A (3 sources)" in result


def test_to_markdown_does_not_repeat_top_story_in_category_sections():
    items = [
        {
            "title": "Top Story",
            "link": "https://example.com/top",
            "source": "Source A",
            "category": "Breaking News",
            "_prompt_id": "item-1",
            "published": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
        },
        {
            "title": "Second Story",
            "link": "https://example.com/second",
            "source": "Source B",
            "category": "Breaking News",
            "_prompt_id": "item-2",
            "published": datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc),
        },
    ]

    result = to_markdown(items, top_stories=["item-1"])
    assert result.count("Top Story") == 1
    assert "Second Story" in result
