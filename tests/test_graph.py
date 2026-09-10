"""Tests for graph module."""
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
import graph
from decision_contract import build_candidate_envelope, validate_candidate_envelope
from graph import (
    _build_candidate_groups,
    _fallback_categorize,
    _is_high_confidence_duplicate,
    _should_retry_openai_error,
    apply_decisions_file,
    build_graph,
    build_candidate_snapshot,
    export_candidate_snapshot,
    node_categorize,
    node_filter,
    node_render,
)
from openai import APIConnectionError
from openai import APITimeoutError


_FIXTURES_DIR = Path(__file__).with_name("fixtures")


def _load_fixture(name: str) -> dict[str, object]:
    return json.loads((_FIXTURES_DIR / name).read_text(encoding="utf-8"))


def _load_text_fixture(name: str) -> str:
    return (_FIXTURES_DIR / name).read_text(encoding="utf-8")


def _item(
    item_id: str,
    title: str,
    hour: int,
    *,
    source: str = "Example",
    summary: str = "",
    category: str = "All",
    source_type: str = "news",
    source_role: str = "independent_reporting",
    feed_mode: str = "core",
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
        "source_role": source_role,
        "feed_mode": feed_mode,
    }


def _candidate_v5(items):
    legacy = build_candidate_snapshot(items)
    return build_candidate_envelope(
        kind="ai-news-agent.candidates",
        categories=legacy["categories"],
        groups=legacy["groups"],
    )


def _bound_decisions(snapshot, groups):
    return {
        "schema_version": 2,
        "kind": "ai-news-agent.decisions",
        "snapshot_id": snapshot["snapshot_id"],
        "groups": groups,
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


def test_build_candidate_groups_prefers_primary_source_within_group():
    items = [
        _item(
            "a",
            "OpenAI launches realtime coding assistant for developers",
            11,
            source="OpenAI",
            source_role="primary",
        ),
        _item(
            "b",
            "OpenAI releases realtime coding assistant for enterprise developers",
            12,
            source="TechCrunch",
            source_role="independent_reporting",
        ),
    ]

    groups = _build_candidate_groups(items)

    assert [item["id"] for item in groups[0]] == ["a", "b"]


def test_build_candidate_snapshot_preserves_group_ids():
    items = [
        _item(
            "a",
            "OpenAI launches realtime coding assistant for developers",
            12,
            source="OpenAI",
            summary="Official launch post for the coding assistant",
            source_role="primary",
        ),
        _item(
            "b",
            "OpenAI releases realtime coding assistant for enterprise developers",
            11,
            source="TechCrunch",
            summary="Coverage of the same OpenAI coding assistant launch",
            source_role="independent_reporting",
        ),
    ]

    snapshot = build_candidate_snapshot(items)

    assert snapshot["kind"] == "ai-news-agent.candidates"
    assert snapshot["groups"][0]["group_id"] == "g1"
    assert [item["item_id"] for item in snapshot["groups"][0]["items"]] == ["g1i1", "g1i2"]
    assert snapshot["groups"][0]["items"][0]["link"] == "https://example.com/a"


def test_build_candidate_snapshot_emits_bound_v5_envelope():
    snapshot = build_candidate_snapshot([_item("a", "A distinct AI story", 12)])

    assert snapshot["schema_version"] == 5
    validate_candidate_envelope(
        snapshot,
        expected_kind="ai-news-agent.candidates",
    )


def test_candidate_guidance_is_exported_and_bound_to_snapshot(tmp_path, monkeypatch):
    item = _item("https://example.com/story", "A distinct AI story", 12)
    monkeypatch.setattr(graph, "collect_items_with_stats", lambda: ([item], {
        "feeds_total": 1, "feeds_succeeded": 1, "feeds_failed": 0, "feed_errors": [],
        "items_collected": 1,
    }))
    monkeypatch.setattr(graph, "_filter_items", lambda items: items)
    output = tmp_path / "candidates.json"

    snapshot, status = export_candidate_snapshot(output)

    assert status["ok"] is True
    assert json.loads(output.read_text()) == snapshot
    assert snapshot["decision_guidance"]
    assert list(snapshot).index("decision_guidance") < list(snapshot).index("groups")
    assert snapshot["groups"][0]["items"][0]["id"] == "https://example.com/story"
    assert snapshot["groups"][0]["items"][0]["item_id"] == "g1i1"
    validate_candidate_envelope(snapshot, expected_kind="ai-news-agent.candidates")
    snapshot["decision_guidance"] = "Use article URLs instead"
    with pytest.raises(ValueError, match="snapshot_id"):
        validate_candidate_envelope(snapshot, expected_kind="ai-news-agent.candidates")


def test_build_candidate_snapshot_matches_contract_fixture():
    items = [
        _item(
            "a",
            "OpenAI launches realtime coding assistant for developers",
            12,
            source="OpenAI",
            summary="Official launch post for the coding assistant",
            source_role="primary",
        ),
        _item(
            "b",
            "OpenAI releases realtime coding assistant for enterprise developers",
            11,
            source="TechCrunch",
            summary="Coverage of the same OpenAI coding assistant launch",
            source_role="independent_reporting",
        ),
        _item(
            "c",
            "Anthropic faces Pentagon scrutiny over defense work",
            9,
            source="The Guardian",
            source_role="independent_reporting",
            feed_mode="discovery_only",
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


def test_export_candidate_snapshot_writes_status_for_healthy_run(tmp_path, monkeypatch):
    items = [
        _item("a", "OpenAI launches new coding agent", 12, source="OpenAI"),
        _item("b", "Anthropic signs enterprise deal", 11, source="TechCrunch"),
    ]
    monkeypatch.setattr(
        graph,
        "collect_items_with_stats",
        lambda: (
            items,
            {
                "feeds_total": 2,
                "feeds_succeeded": 2,
                "feeds_failed": 0,
                "items_collected": 2,
            },
        ),
    )

    snapshot_file = tmp_path / "digest-candidates.json"
    snapshot_payload, status = export_candidate_snapshot(snapshot_file)

    assert snapshot_file.exists()
    assert len(snapshot_payload["groups"]) == 2
    assert status == {
        "ok": True,
        "reason": "ok",
        "groups": 2,
        "items_collected": 2,
        "items_filtered": 2,
        "feeds_total": 2,
        "feeds_succeeded": 2,
        "feeds_failed": 0,
        "feed_errors": [],
    }


def test_export_candidate_snapshot_marks_empty_snapshot_as_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        graph,
        "collect_items_with_stats",
        lambda: (
            [],
            {
                "feeds_total": 3,
                "feeds_succeeded": 0,
                "feeds_failed": 3,
                "items_collected": 0,
            },
        ),
    )

    snapshot_file = tmp_path / "digest-candidates.json"
    snapshot_payload, status = export_candidate_snapshot(snapshot_file)

    assert snapshot_payload["groups"] == []
    assert status["ok"] is False
    assert status["reason"] == "feed_fetch_failed"
    assert status["feed_errors"] == []


def test_export_candidate_snapshot_allows_healthy_empty_day(tmp_path, monkeypatch):
    monkeypatch.setattr(
        graph,
        "collect_items_with_stats",
        lambda: (
            [],
            {
                "feeds_total": 5,
                "feeds_succeeded": 5,
                "feeds_failed": 0,
                "items_collected": 0,
            },
        ),
    )

    snapshot_file = tmp_path / "digest-candidates.json"
    snapshot_payload, status = export_candidate_snapshot(snapshot_file)

    assert snapshot_payload["groups"] == []
    assert status["ok"] is True
    assert status["reason"] == "no_fresh_items"
    assert status["feed_errors"] == []


def test_export_candidate_snapshot_fails_when_no_feeds_are_configured(tmp_path, monkeypatch):
    monkeypatch.setattr(
        graph,
        "collect_items_with_stats",
        lambda: (
            [],
            {
                "feeds_total": 0,
                "feeds_succeeded": 0,
                "feeds_failed": 0,
                "items_collected": 0,
            },
        ),
    )

    snapshot_file = tmp_path / "digest-candidates.json"
    snapshot_payload, status = export_candidate_snapshot(snapshot_file)

    assert snapshot_payload["groups"] == []
    assert status["ok"] is False
    assert status["reason"] == "no_feeds_configured"
    assert status["feed_errors"] == []


def test_node_categorize_drops_discovery_only_singletons(monkeypatch):
    items = [
        _item(
            "a",
            "OpenAI launches realtime coding assistant for developers",
            12,
            source="OpenAI",
            source_role="primary",
        ),
        _item(
            "b",
            "NotebookLM workflow tips for teams",
            11,
            source="Import AI",
            source_role="commentary",
            feed_mode="discovery_only",
        ),
    ]

    monkeypatch.setattr(graph, "_get_openai_api_key", lambda: "")
    result = node_categorize({"items": items})

    assert [item["id"] for item in result["items"]] == ["a"]


def test_node_categorize_keeps_core_item_when_discovery_duplicate_exists(monkeypatch):
    items = [
        _item(
            "a",
            "OpenAI launches realtime coding assistant for developers",
            12,
            source="OpenAI",
            summary="Official launch post for the coding assistant",
            source_role="primary",
        ),
        _item(
            "b",
            "OpenAI launches realtime coding assistant for developers",
            11,
            source="Simon Willison",
            summary="Commentary on the same coding assistant launch",
            source_role="commentary",
            feed_mode="discovery_only",
        ),
    ]

    monkeypatch.setattr(graph, "_get_openai_api_key", lambda: "")
    result = node_categorize({"items": items})

    assert len(result["items"]) == 1
    assert result["items"][0]["source"] == "OpenAI"
    assert result["items"][0]["coverage_sources"] == ["Simon Willison"]


def test_apply_dedupe_response_promotes_core_item_over_discovery_keep():
    indexed_groups = [(
        1,
        [
            _item(
                "a",
                "OpenAI launches realtime coding assistant for developers",
                12,
                source="OpenAI",
                source_role="primary",
            ),
            _item(
                "b",
                "OpenAI launches realtime coding assistant for developers",
                11,
                source="Simon Willison",
                source_role="commentary",
                feed_mode="discovery_only",
            ),
        ],
    )]
    response = {
        "groups": [
            {
                "group_id": "g1",
                "clusters": [
                    {
                        "keep_id": "g1i2",
                        "duplicate_ids": ["g1i1"],
                    }
                ],
            }
        ]
    }

    items, skipped = graph._apply_dedupe_response(indexed_groups, response)

    assert skipped == 1
    assert len(items) == 1
    assert items[0]["source"] == "OpenAI"
    assert items[0]["feed_mode"] == "core"
    assert items[0]["_prompt_id"] == "g1i1"
    assert items[0]["coverage_sources"] == ["Simon Willison"]


def test_node_categorize_uses_structured_llm_response(monkeypatch):
    """Ambiguous groups should use a dedupe pass followed by enrichment."""
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
    dedupe_response = {
        "groups": [
            {
                "group_id": "g1",
                "clusters": [
                    {
                        "keep_id": "g1i1",
                        "duplicate_ids": ["g1i2"],
                    }
                ],
            }
        ],
    }
    enrichment_response = {
        "executive_summary": "OpenAI launched a coding assistant. Anthropic faces scrutiny.",
        "top_stories": ["g1i1"],
        "items": [
            {
                "item_id": "g1i1",
                "category": "Tools & Applications",
                "short_title": "OpenAI launches coding assistant",
                "summary_line": "A new AI coding tool could reshape development.",
                "tier": "high",
            },
            {
                "item_id": "g2i1",
                "category": "Policy & Ethics",
                "short_title": "Anthropic faces Pentagon scrutiny",
                "summary_line": "Government oversight is intensifying.",
                "tier": "normal",
            },
        ],
    }
    prompts: list[str] = []
    responses = iter([
        json.dumps(dedupe_response),
        json.dumps(enrichment_response),
    ])

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(graph, "_get_openai_client", lambda _api_key: object())

    def fake_chat_completion(_client, prompt: str) -> str:
        prompts.append(prompt)
        return next(responses)

    monkeypatch.setattr(graph, "_chat_completion_text", fake_chat_completion)

    result = node_categorize({"items": items})

    assert len(prompts) == 2
    assert "Deduplicate these AI news groups." in prompts[0]
    assert "Enrich these deduplicated AI news items" in prompts[1]
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


def test_node_categorize_skips_dedupe_call_when_no_ambiguous_groups(monkeypatch):
    items = [
        _item("a", "OpenAI launches study mode for ChatGPT", 12, source="OpenAI"),
        _item("b", "Anthropic releases new enterprise controls", 11, source="Anthropic"),
    ]
    enrichment_response = {
        "executive_summary": "OpenAI and Anthropic shipped product updates.",
        "top_stories": ["g1i1"],
        "items": [
            {
                "item_id": "g1i1",
                "category": "Tools & Applications",
                "short_title": "OpenAI launches study mode",
                "summary_line": "ChatGPT gained a new product feature.",
                "tier": "high",
            },
            {
                "item_id": "g2i1",
                "category": "Tools & Applications",
                "short_title": "Anthropic releases controls",
                "summary_line": "Claude added enterprise admin features.",
                "tier": "normal",
            },
        ],
    }
    prompts: list[str] = []

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(graph, "_get_openai_client", lambda _api_key: object())

    def fake_chat_completion(_client, prompt: str) -> str:
        prompts.append(prompt)
        return json.dumps(enrichment_response)

    monkeypatch.setattr(graph, "_chat_completion_text", fake_chat_completion)

    result = node_categorize({"items": items})

    assert len(prompts) == 1
    assert "Enrich these deduplicated AI news items" in prompts[0]
    assert len(result["items"]) == 2


def test_node_categorize_drops_off_topic_items_in_enrichment_response(monkeypatch):
    items = [
        _item("a", "OpenAI launches study mode for ChatGPT", 12, source="OpenAI"),
        _item("b", "Conference discount code ends tonight", 11, source="Newsletter"),
    ]
    enrichment_response = {
        "executive_summary": "OpenAI shipped one notable product update.",
        "top_stories": ["g1i1"],
        "off_topic_ids": ["g2i1"],
        "items": [
            {
                "item_id": "g1i1",
                "category": "Tools & Applications",
                "short_title": "OpenAI launches study mode",
                "summary_line": "ChatGPT gained a new product feature.",
                "tier": "high",
            }
        ],
    }

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(graph, "_get_openai_client", lambda _api_key: object())
    monkeypatch.setattr(graph, "_chat_completion_text", lambda _client, _prompt: json.dumps(enrichment_response))

    result = node_categorize({"items": items})

    assert len(result["items"]) == 1
    assert result["items"][0]["title"] == "OpenAI launches study mode"
    assert result["top_stories"] == ["g1i1"]


def test_node_categorize_raises_when_openai_request_fails(monkeypatch):
    """An attempted API call that fails must never degrade to heuristic output."""
    items = [
        _item("a", "OpenAI launches study mode for ChatGPT", 12, source="OpenAI"),
        _item("b", "Anthropic releases new enterprise controls", 11, source="Anthropic"),
    ]

    def fail(_client, _prompt: str) -> str:
        raise RuntimeError("credit_balance_exhausted")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(graph, "_get_openai_client", lambda _api_key: object())
    monkeypatch.setattr(graph, "_chat_completion_text", fail)

    with pytest.raises(RuntimeError, match="credit_balance_exhausted"):
        node_categorize({"items": items})


def test_node_categorize_raises_when_response_omits_candidates(monkeypatch):
    """A well-formed response that silently drops candidates must fail closed."""
    items = [
        _item("a", "OpenAI launches study mode for ChatGPT", 12, source="OpenAI"),
        _item("b", "Anthropic releases new enterprise controls", 11, source="Anthropic"),
    ]
    enrichment_response = {
        "executive_summary": "",
        "top_stories": [],
        "items": [],
    }

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(graph, "_get_openai_client", lambda _api_key: object())
    monkeypatch.setattr(
        graph,
        "_chat_completion_text",
        lambda _client, _prompt: json.dumps(enrichment_response),
    )

    with pytest.raises(ValueError, match="did not account for"):
        node_categorize({"items": items})


def test_full_graph_does_not_reach_render_when_openai_request_fails(monkeypatch):
    """Render and its downstream publish path must be unreachable after an API failure."""
    items = [
        _item("a", "OpenAI launches study mode for ChatGPT", 12, source="OpenAI"),
        _item("b", "Anthropic releases new enterprise controls", 11, source="Anthropic"),
    ]
    rendered: list[str] = []

    def fail(_client, _prompt: str) -> str:
        raise RuntimeError("boom")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(graph, "_get_openai_client", lambda _api_key: object())
    monkeypatch.setattr(graph, "_chat_completion_text", fail)
    monkeypatch.setattr(graph, "node_collect", lambda _state: {"items": items})
    monkeypatch.setattr(graph, "node_filter", lambda state: state)
    monkeypatch.setattr(
        graph,
        "node_render",
        lambda state: rendered.append("rendered") or state,
    )

    with pytest.raises(RuntimeError, match="boom"):
        build_graph().invoke({"items": []})

    assert rendered == []


def test_node_categorize_without_api_key_keeps_near_duplicate_headlines(monkeypatch):
    """Similar but different headlines need an editorial duplicate decision."""
    items = [
        _item("a", "OpenAI launches realtime coding assistant for developers", 12, source="OpenAI"),
        _item("b", "OpenAI launches realtime coding assistant for enterprise developers", 11, source="TechCrunch"),
    ]

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(graph, "CONFIG_OPENAI_API_KEY", "")
    monkeypatch.setattr(graph, "_get_dotenv_openai_api_key", lambda: "")

    result = node_categorize({"items": items})

    assert [item["id"] for item in result["items"]] == ["a", "b"]
    assert [item["coverage_sources"] for item in result["items"]] == [[], []]
    assert result.get("executive_summary") == ""
    assert result.get("top_stories") == ["g1i1", "g1i2"]


def test_node_categorize_without_api_key_uses_duplicate_summary_when_primary_is_blank(monkeypatch):
    items = [
        _item("a", "OpenAI launches realtime coding assistant for developers", 12, source="OpenAI"),
        _item(
            "b",
            "OpenAI launches realtime coding assistant for developers",
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


def test_no_key_full_pipeline_matches_golden_fixture(tmp_path, monkeypatch):
    output_file = tmp_path / "news.md"
    items = [
        _item(
            "a",
            "OpenAI launches realtime coding assistant for developers",
            12,
            source="OpenAI",
            source_role="primary",
            summary="Official launch post for the coding assistant.",
        ),
        _item(
            "b",
            "OpenAI launches realtime coding assistant for enterprise developers",
            11,
            source="TechCrunch",
            source_role="independent_reporting",
            summary="Independent reporting on the same coding assistant launch.",
        ),
        _item(
            "c",
            "Anthropic faces lawsuit over defense work",
            10,
            source="Ars Technica",
            source_role="independent_reporting",
        ),
        _item(
            "d",
            "Microsoft releases Copilot vision API for Windows developers",
            9,
            source="Microsoft AI",
            source_role="primary",
        ),
        _item(
            "e",
            "Databricks raises $200 million for AI infrastructure",
            8,
            source="VentureBeat",
            source_role="independent_reporting",
        ),
        _item(
            "f",
            "ChatGPT voice mode is a weaker model",
            7,
            source="Simon Willison",
            source_role="commentary",
            feed_mode="discovery_only",
        ),
    ]

    monkeypatch.setattr(
        graph,
        "collect_items_with_stats",
        lambda: (
            items,
            {
                "feeds_total": 6,
                "feeds_succeeded": 6,
                "feeds_failed": 0,
                "items_collected": 6,
            },
        ),
    )
    monkeypatch.setattr(graph, "_get_openai_api_key", lambda: "")
    monkeypatch.setattr(graph, "_NEWS_FILE", output_file)

    result = build_graph().invoke({})

    expected_markdown = _load_text_fixture("no_key_digest.md")
    assert result["markdown"] == expected_markdown
    assert output_file.read_text(encoding="utf-8") == expected_markdown


def test_select_top_story_ids_prefers_category_diversity_without_requested_ids():
    items = [
        {
            "_prompt_id": "g1i1",
            "title": "Policy story",
            "category": "Policy & Ethics",
            "tier": "normal",
            "source_role": "independent_reporting",
            "feed_mode": "core",
            "coverage_sources": [],
            "published": datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        },
        {
            "_prompt_id": "g1i2",
            "title": "Industry story A",
            "category": "Industry & Business",
            "tier": "normal",
            "source_role": "independent_reporting",
            "feed_mode": "core",
            "coverage_sources": [],
            "published": datetime(2026, 1, 1, 11, 0, tzinfo=timezone.utc),
        },
        {
            "_prompt_id": "g1i3",
            "title": "Industry story B",
            "category": "Industry & Business",
            "tier": "normal",
            "source_role": "independent_reporting",
            "feed_mode": "core",
            "coverage_sources": [],
            "published": datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc),
        },
        {
            "_prompt_id": "g1i4",
            "title": "Tool story",
            "category": "Tools & Applications",
            "tier": "normal",
            "source_role": "independent_reporting",
            "feed_mode": "core",
            "coverage_sources": [],
            "published": datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc),
        },
    ]

    assert graph._select_top_story_ids(items, []) == ["g1i1", "g1i2", "g1i4"]


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
    responses = iter([
        json.dumps(
            {
                "groups": [
                    {
                        "group_id": "g1",
                        "clusters": [
                            {
                                "keep_id": "g1i1",
                                "duplicate_ids": ["g1i2"],
                            }
                        ],
                    }
                ]
            }
        ),
        json.dumps(
            {
                "executive_summary": "",
                "top_stories": [],
                "items": [
                    {
                        "item_id": "g2i1",
                        "category": "Policy & Ethics",
                        "short_title": "Anthropic faces Pentagon scrutiny",
                    },
                    {
                        "item_id": "g1i1",
                        "category": "Tools & Applications",
                        "short_title": "OpenAI launches coding assistant",
                    }
                ],
            }
        ),
    ])
    captured: dict[str, str] = {}

    monkeypatch.setenv("OPENAI_API_KEY", "your_api_key_here")
    monkeypatch.setattr(graph, "CONFIG_OPENAI_API_KEY", "")
    monkeypatch.setattr(graph, "_get_dotenv_openai_api_key", lambda: "test-key")

    def fake_get_openai_client(api_key: str) -> object:
        captured["api_key"] = api_key
        return object()

    monkeypatch.setattr(graph, "_get_openai_client", fake_get_openai_client)
    monkeypatch.setattr(graph, "_chat_completion_text", lambda _client, _prompt: next(responses))

    result = node_categorize({"items": items})

    assert captured["api_key"] == "test-key"
    assert len(result["items"]) == 2
    assert result["items"][0]["category"] == "Tools & Applications"


def test_node_categorize_timeout_raises_instead_of_local_resolution(monkeypatch):
    """A timeout is an attempted call, so it fails closed rather than degrading."""
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

    with pytest.raises(APITimeoutError):
        node_categorize({"items": items})


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
    snapshot = build_candidate_snapshot(items)

    candidates_file.write_text(
        json.dumps(snapshot),
        encoding="utf-8",
    )
    decisions_file.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "kind": "ai-news-agent.decisions",
                "snapshot_id": snapshot["snapshot_id"],
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


@pytest.fixture
def identity_decision_files(tmp_path, monkeypatch):
    groups = [[
        _item("https://example.com/core", "OpenAI releases coding assistant", 12,
              source="OpenAI", source_role="primary"),
        _item("https://example.com/discovery", "OpenAI releases coding assistant", 11,
              source="Commentary", feed_mode="discovery_only"),
        _item("https://example.com/off-topic", "Unrelated product promotion", 10),
    ], [
        _item("https://example.com/other", "Court rules on AI copyright case", 9),
    ]]
    snapshot = build_candidate_envelope(
        kind="ai-news-agent.candidates", categories=list(graph.CATEGORIES),
        groups=graph._build_candidate_snapshot_groups(groups),
    )
    decisions = _bound_decisions(snapshot, [
        {"group_id": "g1", "off_topic_ids": ["g1i3"], "clusters": [
            {"keep_id": "g1i2", "duplicate_ids": ["g1i1"],
             "category": "Tools & Applications"},
        ]},
        {"group_id": "g2", "off_topic_ids": [], "clusters": [
            {"keep_id": "g2i1", "duplicate_ids": [], "category": "Policy & Ethics"},
        ]},
    ])
    candidates_path = tmp_path / "candidates.json"
    decisions_path = tmp_path / "decisions.json"
    output = tmp_path / "news.md"
    candidates_path.write_text(json.dumps(snapshot))
    output.write_text("stale digest")
    monkeypatch.setattr(graph, "_NEWS_FILE", output)
    return decisions, candidates_path, decisions_path, output


@pytest.mark.parametrize("top_stories", [
    None, "g1i2", {}, 7, [None], [7], [True], [{}],
    ["g1i2", "g1i2"], ["https://example.com/discovery"],
    ["g9i9"], ["g1i1"], ["g1i3"], ["g1i2", "g1i3"], [" g1i2 "],
])
def test_apply_decisions_rejects_invalid_top_stories_before_render(
    identity_decision_files, top_stories,
):
    decisions, candidates, decisions_path, output = identity_decision_files
    decisions["top_stories"] = top_stories
    decisions_path.write_text(json.dumps(decisions))

    with pytest.raises(ValueError, match="top_stories"):
        apply_decisions_file(decisions_path, candidates)

    assert not output.exists()


@pytest.mark.parametrize("field", ["keep_id", "duplicate_ids", "off_topic_ids"])
def test_apply_decisions_url_dispositions_explain_item_id_without_rendering(
    identity_decision_files, field,
):
    decisions, candidates, decisions_path, output = identity_decision_files
    group = decisions["groups"][0]
    cluster = group["clusters"][0]
    if field == "keep_id":
        cluster[field] = "https://example.com/discovery"
    elif field == "duplicate_ids":
        cluster[field] = ["https://example.com/core"]
    else:
        group[field] = ["https://example.com/off-topic"]
    decisions_path.write_text(json.dumps(decisions))

    with pytest.raises(ValueError) as error:
        apply_decisions_file(decisions_path, candidates)

    message = str(error.value)
    assert "item_id" in message
    assert "g1i1, g1i2, g1i3" in message
    assert "id" in message and "link" in message
    assert not output.exists()


@pytest.mark.parametrize("selection", ["absent", "empty", "requested"])
def test_apply_decisions_preserves_auto_selection_and_requested_keep_promotion(
    identity_decision_files, selection,
):
    decisions, candidates, decisions_path, output = identity_decision_files
    if selection == "empty":
        decisions["top_stories"] = []
    elif selection == "requested":
        decisions["top_stories"] = ["g2i1", "g1i2"]
    decisions_path.write_text(json.dumps(decisions))

    result = apply_decisions_file(decisions_path, candidates)

    expected = ["g2i1", "g1i1"] if selection == "requested" else ["g1i1", "g2i1"]
    assert result["top_stories"] == expected
    assert output.read_text() == result["markdown"]


def test_apply_decisions_file_rejects_unbound_legacy_decisions(tmp_path, monkeypatch):
    snapshot = _candidate_v5([_item("a", "A distinct AI story", 12)])
    candidates_file = tmp_path / "digest-candidates.json"
    decisions_file = tmp_path / "digest-decisions.json"
    output_file = tmp_path / "news.md"
    candidates_file.write_text(json.dumps(snapshot), encoding="utf-8")
    decisions_file.write_text(json.dumps({"groups": []}), encoding="utf-8")
    output_file.write_text("stale digest", encoding="utf-8")
    monkeypatch.setattr(graph, "_NEWS_FILE", output_file)

    with pytest.raises(ValueError, match="schema version"):
        apply_decisions_file(decisions_file, candidates_file)

    assert not output_file.exists()


def test_apply_decisions_file_rejects_missing_groups_without_rendering(tmp_path, monkeypatch):
    snapshot = _candidate_v5([_item("a", "A distinct AI story", 12)])
    candidates_file = tmp_path / "digest-candidates.json"
    decisions_file = tmp_path / "digest-decisions.json"
    output_file = tmp_path / "news.md"
    candidates_file.write_text(json.dumps(snapshot), encoding="utf-8")
    decisions_file.write_text(json.dumps(_bound_decisions(snapshot, [])), encoding="utf-8")
    monkeypatch.setattr(graph, "_NEWS_FILE", output_file)

    with pytest.raises(ValueError, match="Missing decision groups"):
        apply_decisions_file(decisions_file, candidates_file)

    assert not output_file.exists()


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

    assert [item["title"] for item in result["items"]] == ["OpenAI launches coding assistant"]
    assert [item["category"] for item in result["items"]] == [
        "Tools & Applications",
    ]
    assert result["items"][0]["summary_line"] == "A new AI coding tool could reshape how developers write software."
    assert result["items"][0]["tier"] == "high"
    assert result["items"][0]["coverage_sources"] == ["TechCrunch"]
    assert result["executive_summary"] == "OpenAI launched a new coding assistant for developers."
    assert result["top_stories"] == ["g1i1"]
    assert output_file.read_text(encoding="utf-8") == result["markdown"]


def test_apply_decisions_file_respects_off_topic_ids(tmp_path, monkeypatch):
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
            "Conference pass discount ends tonight",
            9,
            source="Newsletter",
        ),
    ]
    candidates_file = tmp_path / "digest-candidates.json"
    decisions_file = tmp_path / "digest-decisions.json"
    output_file = tmp_path / "news.md"
    snapshot = build_candidate_snapshot(items)

    candidates_file.write_text(
        json.dumps(snapshot),
        encoding="utf-8",
    )
    decisions_file.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "kind": "ai-news-agent.decisions",
                "snapshot_id": snapshot["snapshot_id"],
                "groups": [
                    {
                        "group_id": "g1",
                        "off_topic_ids": [],
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
                        "off_topic_ids": ["g2i1"],
                        "clusters": [],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(graph, "_NEWS_FILE", output_file)

    result = apply_decisions_file(decisions_file, candidates_file)

    assert len(result["items"]) == 1
    assert result["items"][0]["title"] == "OpenAI launches coding assistant"
    assert output_file.read_text(encoding="utf-8") == result["markdown"]


def test_apply_decisions_rejects_unbound_old_format(tmp_path, monkeypatch):
    candidates_file = tmp_path / "digest-candidates.json"
    decisions_file = tmp_path / "digest-decisions.json"
    output_file = tmp_path / "news.md"

    candidates_file.write_text(
        json.dumps(_load_fixture("candidate_snapshot.json")),
        encoding="utf-8",
    )
    decisions_file.write_text(json.dumps({"groups": []}), encoding="utf-8")
    monkeypatch.setattr(graph, "_NEWS_FILE", output_file)

    with pytest.raises(ValueError, match="schema version"):
        apply_decisions_file(decisions_file, candidates_file)

    assert not output_file.exists()


def test_apply_decisions_v2_preserves_optional_field_fallbacks(tmp_path, monkeypatch):
    snapshot = _load_fixture("candidate_snapshot.json")
    candidates_file = tmp_path / "digest-candidates.json"
    decisions_file = tmp_path / "digest-decisions.json"
    output_file = tmp_path / "news.md"
    candidates_file.write_text(json.dumps(snapshot), encoding="utf-8")
    decisions_file.write_text(
        json.dumps({
            "schema_version": 2,
            "kind": "ai-news-agent.decisions",
            "snapshot_id": snapshot["snapshot_id"],
            "groups": [
                {
                    "group_id": "g1",
                    "off_topic_ids": [],
                    "clusters": [{
                        "keep_id": "g1i1",
                        "duplicate_ids": ["g1i2"],
                        "category": "Tools & Applications",
                        "short_title": "OpenAI launches coding assistant",
                    }],
                },
                {"group_id": "g2", "off_topic_ids": ["g2i1"], "clusters": []},
            ],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(graph, "_NEWS_FILE", output_file)

    result = apply_decisions_file(decisions_file, candidates_file)

    assert result["items"][0]["summary_line"] == "Official launch post for the coding assistant"
    assert result["items"][0]["tier"] == "normal"
    assert result["items"][0]["coverage_sources"] == ["TechCrunch"]
    assert result.get("executive_summary") == ""
    assert result.get("top_stories") == ["g1i1"]


def test_apply_structured_response_accepts_discovery_singleton_then_filters_it():
    groups = [[_item(
        "a",
        "Discovery-only AI story",
        12,
        feed_mode="discovery_only",
    )]]
    response = {
        "groups": [{
            "group_id": "g1",
            "off_topic_ids": [],
            "clusters": [{
                "keep_id": "g1i1",
                "duplicate_ids": [],
                "category": "Industry & Business",
                "short_title": "Discovery-only AI story",
            }],
        }],
    }

    result = graph._apply_structured_response({}, groups, response, log_label="test")

    assert result["items"] == []


def test_invalid_raw_dispositions_fail_before_keep_promotion(monkeypatch):
    groups = [[
        _item("a", "Core AI report", 12, feed_mode="core"),
        _item("b", "Discovery AI report", 11, feed_mode="discovery_only"),
        _item("c", "Separate AI policy report", 10, feed_mode="core"),
    ]]
    response = {
        "groups": [{
            "group_id": "g1",
            "off_topic_ids": [],
            "clusters": [{"keep_id": "g1i2", "duplicate_ids": ["g1i1"]}],
        }],
    }
    promoted = False

    def record_promotion(*args, **kwargs):
        nonlocal promoted
        promoted = True
        return "g1i1"

    monkeypatch.setattr(graph, "_promote_renderable_keep_id", record_promotion)

    with pytest.raises(ValueError, match="Missing item dispositions"):
        graph._apply_structured_response({}, groups, response, log_label="test")

    assert not promoted


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


def test_apply_structured_response_orders_duplicate_fallbacks_by_source_role():
    state = {"items": [], "executive_summary": "", "top_stories": []}
    groups = [[
        _item(
            "a",
            "OpenAI launches realtime coding assistant for developers",
            12,
            source="OpenAI News",
            source_role="primary",
        ),
        _item(
            "b",
            "OpenAI launches realtime coding assistant for enterprise developers",
            11,
            source="TechCrunch",
            summary="Independent summary second.",
            source_role="independent_reporting",
        ),
        _item(
            "c",
            "OpenAI coding assistant analysis",
            10,
            source="Newsletter",
            summary="Commentary summary first.",
            source_role="commentary",
        ),
    ]]
    response = {
        "groups": [
            {
                "group_id": "g1",
                "clusters": [
                    {
                        "keep_id": "g1i1",
                        "duplicate_ids": ["g1i3", "g1i2"],
                        "category": "Tools & Applications",
                        "short_title": "OpenAI launches coding assistant",
                    }
                ],
            }
        ]
    }

    result = graph._apply_structured_response(state, groups, response, log_label="test")

    assert result["items"][0]["summary_line"] == "Independent summary second."
    assert result["items"][0]["coverage_sources"] == ["TechCrunch", "Newsletter"]


def test_apply_structured_response_promotes_core_item_over_discovery_keep():
    state = {"items": [], "executive_summary": "", "top_stories": []}
    groups = [[
        _item(
            "a",
            "OpenAI launches realtime coding assistant for developers",
            12,
            source="OpenAI",
            source_role="primary",
        ),
        _item(
            "b",
            "OpenAI launches realtime coding assistant for developers",
            11,
            source="Simon Willison",
            source_role="commentary",
            feed_mode="discovery_only",
        ),
    ]]
    response = {
        "top_stories": ["g1i2"],
        "groups": [
            {
                "group_id": "g1",
                "clusters": [
                    {
                        "keep_id": "g1i2",
                        "duplicate_ids": ["g1i1"],
                        "category": "Tools & Applications",
                        "short_title": "OpenAI launches coding assistant",
                    }
                ],
            }
        ],
    }

    result = graph._apply_structured_response(state, groups, response, log_label="test")

    assert len(result["items"]) == 1
    assert result["items"][0]["source"] == "OpenAI"
    assert result["items"][0]["feed_mode"] == "core"
    assert result["items"][0]["_prompt_id"] == "g1i1"
    assert result["items"][0]["coverage_sources"] == ["Simon Willison"]
    assert result["top_stories"] == ["g1i1"]


def test_apply_enrichment_response_preserves_seeded_summary_line_when_model_omits_it():
    item = {
        "title": "Primary keep",
        "original_title": "Primary keep",
        "summary": "",
        "summary_line": "Independent reporting summary.",
        "source": "OpenAI News",
        "source_role": "primary",
        "_prompt_id": "g1i1",
        "category": "Industry & Business",
        "tier": "normal",
        "coverage_sources": ["TechCrunch"],
        "published": datetime(2026, 4, 10, tzinfo=timezone.utc),
        "link": "https://example.com/1",
    }
    response = {
        "executive_summary": "",
        "top_stories": [],
        "items": [
            {
                "item_id": "g1i1",
                "category": "Tools & Applications",
                "short_title": "Primary keep",
            }
        ],
    }

    result = graph._apply_enrichment_response(
        {"items": [], "executive_summary": "", "top_stories": []},
        [item],
        response,
        skipped_items=1,
        log_label="test",
    )

    assert result["items"][0]["summary_line"] == "Independent reporting summary."


def test_apply_enrichment_response_skips_off_topic_ids():
    items = [
        {
            "title": "Primary keep",
            "original_title": "Primary keep",
            "summary": "",
            "summary_line": "",
            "source": "OpenAI News",
            "source_role": "primary",
            "_prompt_id": "g1i1",
            "category": "Industry & Business",
            "tier": "normal",
            "coverage_sources": [],
            "published": datetime(2026, 4, 10, tzinfo=timezone.utc),
            "link": "https://example.com/1",
        },
        {
            "title": "Low-signal item",
            "original_title": "Low-signal item",
            "summary": "",
            "summary_line": "",
            "source": "Newsletter",
            "source_role": "commentary",
            "_prompt_id": "g2i1",
            "category": "Tutorials & Insights",
            "tier": "normal",
            "coverage_sources": [],
            "published": datetime(2026, 4, 10, tzinfo=timezone.utc),
            "link": "https://example.com/2",
        },
    ]
    response = {
        "executive_summary": "",
        "top_stories": ["g1i1"],
        "off_topic_ids": ["g2i1"],
        "items": [
            {
                "item_id": "g1i1",
                "category": "Tools & Applications",
                "short_title": "Primary keep",
            }
        ],
    }

    result = graph._apply_enrichment_response(
        {"items": [], "executive_summary": "", "top_stories": []},
        items,
        response,
        skipped_items=0,
        log_label="test",
    )

    assert [item["title"] for item in result["items"]] == ["Primary keep"]


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
    monkeypatch.setattr(
        graph,
        "collect_items_with_stats",
        lambda: (
            [],
            {
                "feeds_total": 5,
                "feeds_succeeded": 5,
                "feeds_failed": 0,
                "items_collected": 0,
            },
        ),
    )

    result = build_graph().invoke({})

    assert result["items"] == []
    assert result["markdown"] == "_No fresh AI headlines in the last 24 h._"
    assert output_file.read_text(encoding="utf-8") == result["markdown"]


def test_build_graph_fails_when_collection_health_is_bad(tmp_path, monkeypatch):
    output_file = tmp_path / "news.md"

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(graph, "_NEWS_FILE", output_file)
    monkeypatch.setattr(
        graph,
        "collect_items_with_stats",
        lambda: (
            [],
            {
                "feeds_total": 5,
                "feeds_succeeded": 0,
                "feeds_failed": 5,
                "items_collected": 0,
            },
        ),
    )

    with pytest.raises(RuntimeError, match="Candidate export failed health checks: feed_fetch_failed"):
        build_graph().invoke({})


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
