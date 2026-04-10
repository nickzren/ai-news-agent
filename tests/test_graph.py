"""Tests for graph module."""
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import graph
from graph import (
    _build_candidate_groups,
    _fallback_categorize,
    _is_high_confidence_duplicate,
    _should_retry_openai_error,
    apply_decisions_file,
    build_graph,
    build_candidate_snapshot,
    node_categorize,
    node_filter,
    node_render,
)
from openai import APIConnectionError
from openai import APITimeoutError


_FIXTURES_DIR = Path(__file__).with_name("fixtures")


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))


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


def test_build_candidate_snapshot_preserves_group_ids():
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
    ]

    snapshot = build_candidate_snapshot(items)

    assert snapshot["kind"] == "ai-news-agent.candidates"
    assert snapshot["groups"][0]["group_id"] == "g1"
    assert [item["item_id"] for item in snapshot["groups"][0]["items"]] == ["g1i1", "g1i2"]
    assert snapshot["groups"][0]["items"][0]["link"] == "https://example.com/a"


def test_build_candidate_snapshot_matches_contract_fixture():
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
            9,
            source="The Guardian",
        ),
    ]

    snapshot = build_candidate_snapshot(items)

    assert snapshot == _load_fixture("candidate_snapshot.json")


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
        "executive_summary": "OpenAI launched a coding assistant. Anthropic faces scrutiny.",
        "top_stories": ["g1i1"],
        "groups": [
            {
                "group_id": "g1",
                "clusters": [
                    {
                        "keep_id": "g1i1",
                        "duplicate_ids": ["g1i2"],
                        "category": "Tools & Applications",
                        "short_title": "OpenAI launches coding assistant",
                        "summary_line": "A new AI coding tool could reshape development.",
                        "tier": "high",
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
                        "summary_line": "Government oversight is intensifying.",
                        "tier": "normal",
                    }
                ],
            },
        ],
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
    assert result["items"][0]["summary_line"] == "A new AI coding tool could reshape development."
    assert result["items"][0]["tier"] == "high"
    assert result["items"][0]["coverage_sources"] == ["TechCrunch"]
    assert result["items"][1]["tier"] == "normal"
    assert result["items"][1]["coverage_sources"] == []
    assert result["executive_summary"] == "OpenAI launched a coding assistant. Anthropic faces scrutiny."
    assert result["top_stories"] == ["g1i1"]


def test_node_categorize_without_api_key_uses_local_resolution(monkeypatch):
    """Local fallback should keep originals and drop obvious duplicates."""
    items = [
        _item("a", "OpenAI launches realtime coding assistant for developers", 12, source="OpenAI"),
        _item("b", "OpenAI launches realtime coding assistant for enterprise developers", 11, source="TechCrunch"),
    ]

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(graph, "CONFIG_OPENAI_API_KEY", "")
    monkeypatch.setattr(graph, "_get_dotenv_openai_api_key", lambda: "")

    result = node_categorize({"items": items})

    assert len(result["items"]) == 1
    assert result["items"][0]["title"] == "OpenAI launches realtime coding assistant for developers"
    assert result["items"][0]["summary_line"] == ""
    assert result["items"][0]["tier"] == "normal"
    assert result["items"][0]["coverage_sources"] == ["TechCrunch"]
    assert result.get("executive_summary") == ""
    assert result.get("top_stories") == ["g1i1"]


def test_node_categorize_without_api_key_uses_duplicate_summary_when_primary_is_blank(monkeypatch):
    items = [
        _item("a", "OpenAI launches realtime coding assistant for developers", 12, source="OpenAI"),
        _item(
            "b",
            "OpenAI launches realtime coding assistant for enterprise developers",
            11,
            source="TechCrunch",
            summary="Independent reporting explains why the new coding assistant matters. Extra detail follows.",
        ),
    ]

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(graph, "CONFIG_OPENAI_API_KEY", "")
    monkeypatch.setattr(graph, "_get_dotenv_openai_api_key", lambda: "")

    result = node_categorize({"items": items})

    assert result["items"][0]["summary_line"] == "Independent reporting explains why the new coding assistant matters."
    assert result["items"][0]["coverage_sources"] == ["TechCrunch"]


def test_node_categorize_uses_dotenv_api_key_when_env_is_placeholder(monkeypatch):
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
            9,
            source="The Guardian",
        ),
    ]
    response = _load_fixture("decisions.json")
    captured: dict[str, str] = {}

    monkeypatch.setenv("OPENAI_API_KEY", "your_api_key_here")
    monkeypatch.setattr(graph, "CONFIG_OPENAI_API_KEY", "")
    monkeypatch.setattr(graph, "_get_dotenv_openai_api_key", lambda: "test-key")

    def fake_get_openai_client(api_key: str) -> object:
        captured["api_key"] = api_key
        return object()

    monkeypatch.setattr(graph, "_get_openai_client", fake_get_openai_client)
    monkeypatch.setattr(graph, "_chat_completion_text", lambda _client, _prompt: json.dumps(response))

    result = node_categorize({"items": items})

    assert captured["api_key"] == "test-key"
    assert len(result["items"]) == 2
    assert result["items"][0]["category"] == "Tools & Applications"


def test_node_categorize_timeout_uses_local_resolution(monkeypatch):
    items = [
        _item("a", "OpenAI launches realtime coding assistant for developers", 12, source="OpenAI"),
        _item("b", "OpenAI launches realtime coding assistant for enterprise developers", 11, source="TechCrunch"),
    ]

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(graph, "_get_openai_client", lambda _api_key: object())

    def raise_timeout(_client, _prompt):
        raise APITimeoutError(
            request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        )

    monkeypatch.setattr(graph, "_chat_completion_text", raise_timeout)

    result = node_categorize({"items": items})

    assert len(result["items"]) == 1
    assert result["items"][0]["title"] == "OpenAI launches realtime coding assistant for developers"


def test_apply_decisions_file_renders_from_candidate_snapshot(tmp_path, monkeypatch):
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
            9,
            source="The Guardian",
        ),
    ]
    candidates_file = tmp_path / "digest-candidates.json"
    decisions_file = tmp_path / "digest-decisions.json"
    output_file = tmp_path / "news.md"

    candidates_file.write_text(
        json.dumps(build_candidate_snapshot(items)),
        encoding="utf-8",
    )
    decisions_file.write_text(
        json.dumps(
            {
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
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(graph, "_NEWS_FILE", output_file)

    result = apply_decisions_file(decisions_file, candidates_file)

    assert [item["title"] for item in result["items"]] == [
        "OpenAI launches coding assistant",
        "Anthropic faces Pentagon scrutiny",
    ]
    assert output_file.read_text(encoding="utf-8") == result["markdown"]


def test_apply_decisions_file_matches_contract_fixtures(tmp_path, monkeypatch):
    candidates_file = tmp_path / "digest-candidates.json"
    decisions_file = tmp_path / "digest-decisions.json"
    output_file = tmp_path / "news.md"

    candidates_file.write_text(
        json.dumps(_load_fixture("candidate_snapshot.json")),
        encoding="utf-8",
    )
    decisions_file.write_text(
        json.dumps(_load_fixture("decisions.json")),
        encoding="utf-8",
    )
    monkeypatch.setattr(graph, "_NEWS_FILE", output_file)

    result = apply_decisions_file(decisions_file, candidates_file)

    assert [item["title"] for item in result["items"]] == [
        "OpenAI launches coding assistant",
        "Anthropic faces Pentagon scrutiny",
    ]
    assert [item["category"] for item in result["items"]] == [
        "Tools & Applications",
        "Policy & Ethics",
    ]
    assert result["items"][0]["summary_line"] == "A new AI coding tool could reshape how developers write software."
    assert result["items"][0]["tier"] == "high"
    assert result["items"][0]["coverage_sources"] == ["TechCrunch"]
    assert result["executive_summary"] == "OpenAI launched a new coding assistant while Anthropic faces scrutiny over its defense work."
    assert result["top_stories"] == ["g1i1", "g2i1"]
    assert output_file.read_text(encoding="utf-8") == result["markdown"]


def test_apply_decisions_backward_compat_old_format(tmp_path, monkeypatch):
    """Old-format decisions without new fields should still work with defaults."""
    candidates_file = tmp_path / "digest-candidates.json"
    decisions_file = tmp_path / "digest-decisions.json"
    output_file = tmp_path / "news.md"

    candidates_file.write_text(
        json.dumps(_load_fixture("candidate_snapshot.json")),
        encoding="utf-8",
    )
    decisions_file.write_text(
        json.dumps(
            {
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
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(graph, "_NEWS_FILE", output_file)

    result = apply_decisions_file(decisions_file, candidates_file)

    assert result["items"][0]["summary_line"] == "Official launch post for the coding assistant"
    assert result["items"][0]["tier"] == "normal"
    assert result["items"][0]["coverage_sources"] == ["TechCrunch"]
    assert result.get("executive_summary") == ""
    assert result.get("top_stories") == ["g1i1", "g2i1"]


def test_apply_structured_response_uses_duplicate_summary_when_keep_summary_is_blank():
    state = {"items": [], "executive_summary": "", "top_stories": []}
    groups = [[
        _item("a", "OpenAI launches realtime coding assistant for developers", 12, source="OpenAI"),
        _item(
            "b",
            "OpenAI launches realtime coding assistant for enterprise developers",
            11,
            source="TechCrunch",
            summary="Independent reporting explains why the new coding assistant matters. Extra detail follows.",
        ),
    ]]
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
            }
        ]
    }

    result = graph._apply_structured_response(state, groups, response, log_label="test")

    assert result["items"][0]["summary_line"] == "Independent reporting explains why the new coding assistant matters."
    assert result["items"][0]["coverage_sources"] == ["TechCrunch"]


def test_should_retry_openai_error_retries_timeout():
    request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")

    assert _should_retry_openai_error(APITimeoutError(request=request))
    assert _should_retry_openai_error(APIConnectionError(request=request))


def test_clean_summary_line_preserves_abbreviations_and_versions():
    assert (
        graph._clean_summary_line("U.S. regulators approved the therapy after review.")
        == "U.S. regulators approved the therapy after review."
    )
    assert (
        graph._clean_summary_line("Version 2.1 ships today with better coding support.")
        == "Version 2.1 ships today with better coding support."
    )
    assert (
        graph._clean_summary_line("OpenAI Inc. Launches a new coding assistant for teams.")
        == "OpenAI Inc. Launches a new coding assistant for teams."
    )
    assert (
        graph._clean_summary_line("The board met at Acme Co. Headquarters before the vote.")
        == "The board met at Acme Co. Headquarters before the vote."
    )


def test_clean_summary_line_keeps_only_first_sentence():
    assert (
        graph._clean_summary_line("No major policy change yet. Markets are watching.")
        == "No major policy change yet."
    )
    assert (
        graph._clean_summary_line("This matters. here is a lowercase second sentence.")
        == "This matters."
    )


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
