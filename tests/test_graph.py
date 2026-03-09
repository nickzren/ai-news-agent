"""Tests for graph module."""
import json
from datetime import datetime, timezone

import graph
from graph import (
    _build_candidate_groups,
    _fallback_categorize,
    _is_high_confidence_duplicate,
    build_graph,
    node_categorize,
    node_filter,
    node_render,
)


def _item(
    item_id: str,
    title: str,
    hour: int,
    *,
    source: str = "Example",
    summary: str = "",
    category: str = "All",
    source_type: str = "news",
) -> dict[str, object]:
    return {
        "id": item_id,
        "title": title,
        "original_title": title,
        "link": f"https://example.com/{item_id}",
        "source": source,
        "published": datetime(2026, 1, 1, hour, 0, tzinfo=timezone.utc),
        "category": category,
        "summary": summary,
        "source_type": source_type,
    }


def test_fallback_categorize_papers_source():
    """Test that items from Papers source get Research & Models."""
    item = {"title": "Some headline", "source": "Hugging Face Papers"}
    assert _fallback_categorize(item) == "Research & Models"


def test_fallback_categorize_paper_source_type():
    """Paper source types should map to Research & Models."""
    item = {"title": "Anything", "source": "Example", "source_type": "paper"}
    assert _fallback_categorize(item) == "Research & Models"


def test_fallback_categorize_policy_keywords():
    """Test policy/ethics keyword detection."""
    items = [
        {"title": "New AI lawsuit filed against company", "source": "TechCrunch"},
        {"title": "AI copyright issues in court", "source": "Wired"},
        {"title": "AI safety concerns raised", "source": "MIT"},
        {"title": "New AI regulation proposed", "source": "Guardian"},
    ]
    for item in items:
        assert _fallback_categorize(item) == "Policy & Ethics"


def test_fallback_categorize_research_keywords():
    """Test research keyword detection."""
    items = [
        {"title": "New paper on transformers", "source": "ArXiv"},
        {"title": "Research shows AI improvement", "source": "MIT"},
        {"title": "New model beats benchmark", "source": "Google"},
        {"title": "Arxiv paper released", "source": "Unknown"},
    ]
    for item in items:
        assert _fallback_categorize(item) == "Research & Models"


def test_fallback_categorize_tools_keywords():
    """Test tools/applications keyword detection."""
    items = [
        {"title": "Company launches new AI tool", "source": "TechCrunch"},
        {"title": "New API release from OpenAI", "source": "OpenAI"},
        {"title": "Feature update for ChatGPT", "source": "The Verge"},
    ]
    for item in items:
        assert _fallback_categorize(item) == "Tools & Applications"


def test_fallback_categorize_business_keywords():
    """Test business/industry keyword detection."""
    items = [
        {"title": "AI startup raises $50M", "source": "TechCrunch"},
        {"title": "Company funding round announced", "source": "VentureBeat"},
        {"title": "$100 billion valuation", "source": "WSJ"},
    ]
    for item in items:
        assert _fallback_categorize(item) == "Industry & Business"


def test_fallback_categorize_tutorials_keywords():
    """Test tutorials/insights keyword detection."""
    items = [
        {"title": "How to use ChatGPT effectively", "source": "Medium"},
        {"title": "Complete guide to LLMs", "source": "Blog"},
        {"title": "Tutorial on fine-tuning", "source": "HuggingFace"},
        {"title": "Why AI matters for developers", "source": "Dev.to"},
    ]
    for item in items:
        assert _fallback_categorize(item) == "Tutorials & Insights"


def test_fallback_categorize_breaking_keywords():
    """Test breaking news keyword detection."""
    items = [
        {"title": "OpenAI announces GPT-5", "source": "OpenAI"},
        {"title": "Google unveils new Gemini", "source": "Google"},
    ]
    for item in items:
        assert _fallback_categorize(item) == "Breaking News"


def test_fallback_categorize_default():
    """Test that unmatched items get default category."""
    item = {"title": "Some random AI headline", "source": "Unknown"}
    # Should return the default category (Industry & Business)
    result = _fallback_categorize(item)
    assert result == "Industry & Business"


def test_fallback_categorize_case_insensitive():
    """Test that keyword matching is case insensitive."""
    item = {"title": "NEW LAWSUIT FILED", "source": "News"}
    assert _fallback_categorize(item) == "Policy & Ethics"

    item = {"title": "COMPANY RAISES FUNDING", "source": "News"}
    assert _fallback_categorize(item) == "Industry & Business"


def test_fallback_categorize_respects_valid_category_hint():
    """Valid category hints should be preserved."""
    item = {
        "title": "Anything",
        "source": "Unknown",
        "category": "Tools & Applications",
    }
    assert _fallback_categorize(item) == "Tools & Applications"


def test_high_confidence_duplicate_requires_strong_overlap():
    """Very similar headlines should be marked duplicates."""
    existing = {"title": "OpenAI launches realtime coding assistant for developers"}
    candidate = {"title": "OpenAI launches realtime coding assistant for enterprise developers"}
    assert _is_high_confidence_duplicate(existing, candidate)


def test_high_confidence_duplicate_avoids_unrelated_company_stories():
    """Different events for one company should not be merged."""
    existing = {"title": "Google unveils Gemini 3 model for enterprises"}
    candidate = {"title": "Google faces antitrust lawsuit in European court"}
    assert not _is_high_confidence_duplicate(existing, candidate)


def test_build_candidate_groups_clusters_possible_duplicates():
    """Potential duplicates should be grouped before LLM analysis."""
    items = [
        _item(
            "a",
            "OpenAI launches realtime coding assistant for developers",
            12,
            source="OpenAI",
            summary="Official launch post for the coding assistant",
        ),
        _item(
            "b",
            "OpenAI releases realtime coding assistant for enterprise developers",
            11,
            source="TechCrunch",
            summary="Coverage of the same OpenAI coding assistant launch",
        ),
        _item(
            "c",
            "Anthropic faces Pentagon scrutiny over defense work",
            10,
            source="The Guardian",
        ),
    ]

    groups = _build_candidate_groups(items)

    assert [len(group) for group in groups] == [2, 1]
    assert {item["id"] for item in groups[0]} == {"a", "b"}


def test_node_filter_removes_noise_titles_and_applies_source_cap(monkeypatch):
    items = [
        _item("a", "OpenAI launches new coding agent", 12, source="OpenAI"),
        _item("b", "Sponsored webinar: build agents faster", 11, source="Vendor"),
        _item("c", "OpenAI ships upgraded eval tooling", 10, source="OpenAI"),
        _item("d", "OpenAI adds enterprise controls", 9, source="OpenAI"),
    ]

    monkeypatch.setattr(graph, "MAX_ITEMS_PER_SOURCE", 2)
    result = node_filter({"items": items})

    assert [item["id"] for item in result["items"]] == ["a", "c"]


def test_node_categorize_uses_structured_llm_response(monkeypatch):
    """Structured group output should remove duplicates and shorten kept titles."""
    items = [
        _item(
            "a",
            "OpenAI launches realtime coding assistant for developers",
            12,
            source="OpenAI",
            summary="Official post announcing the new coding assistant",
        ),
        _item(
            "b",
            "OpenAI releases realtime coding assistant for enterprise developers",
            11,
            source="TechCrunch",
            summary="A report on the same OpenAI coding assistant launch",
        ),
        _item(
            "c",
            "Anthropic faces Pentagon scrutiny over defense work",
            9,
            source="The Guardian",
        ),
    ]
    response = {
        "groups": [
            {
                "group_id": "g1",
                "clusters": [
                    {
                        "keep_id": "g1i1",
                        "duplicate_ids": ["g1i2"],
                        "category": "Tools & Applications",
                        "short_title": "OpenAI launches coding assistant",
                    }
                ],
            },
            {
                "group_id": "g2",
                "clusters": [
                    {
                        "keep_id": "g2i1",
                        "duplicate_ids": [],
                        "category": "Policy & Ethics",
                        "short_title": "Anthropic faces Pentagon scrutiny",
                    }
                ],
            },
        ]
    }

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(graph, "_get_openai_client", lambda _api_key: object())
    monkeypatch.setattr(graph, "_chat_completion_text", lambda _client, _prompt: json.dumps(response))

    result = node_categorize({"items": items})

    assert len(result["items"]) == 2
    assert [item["title"] for item in result["items"]] == [
        "OpenAI launches coding assistant",
        "Anthropic faces Pentagon scrutiny",
    ]
    assert [item["category"] for item in result["items"]] == [
        "Tools & Applications",
        "Policy & Ethics",
    ]
    assert result["items"][0]["original_title"] == "OpenAI launches realtime coding assistant for developers"


def test_node_categorize_without_api_key_uses_local_resolution(monkeypatch):
    """Local fallback should keep originals and drop obvious duplicates."""
    items = [
        _item("a", "OpenAI launches realtime coding assistant for developers", 12, source="OpenAI"),
        _item("b", "OpenAI launches realtime coding assistant for enterprise developers", 11, source="TechCrunch"),
    ]

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = node_categorize({"items": items})

    assert len(result["items"]) == 1
    assert result["items"][0]["title"] == "OpenAI launches realtime coding assistant for developers"


def test_build_graph_renders_empty_digest_when_collection_is_empty(tmp_path, monkeypatch):
    """The full graph should complete even when collection yields no items."""
    output_file = tmp_path / "news.md"

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(graph, "_NEWS_FILE", output_file)
    monkeypatch.setattr(graph, "collect_items", lambda: [])

    result = build_graph().invoke({})

    assert result["items"] == []
    assert result["markdown"] == "_No fresh AI headlines in the last 24 h._"
    assert output_file.read_text(encoding="utf-8") == result["markdown"]


def test_node_render_writes_to_configured_output(tmp_path, monkeypatch):
    """Rendered markdown should be written to the configured output path."""
    output_file = tmp_path / "news.md"
    monkeypatch.setattr(graph, "_NEWS_FILE", output_file)
    state = {
        "items": [
            {
                "title": "Title",
                "link": "https://example.com",
                "source": "Example",
                "category": "Breaking News",
                "published": datetime(2026, 1, 1, tzinfo=timezone.utc),
            }
        ]
    }

    result = node_render(state)
    assert output_file.exists()
    assert result["markdown"]
