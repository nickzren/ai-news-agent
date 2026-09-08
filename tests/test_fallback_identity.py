"""Local deletion requires headline identity, not candidate-group similarity."""

from copy import deepcopy
from datetime import datetime, timezone

import graph
import pytest


def _item(item_id, title, **overrides):
    return {
        "id": item_id,
        "title": title,
        "original_title": title,
        "link": f"https://example.com/{item_id}",
        "source": f"Wire {item_id}",
        "published": datetime(2026, 9, 8, 12, tzinfo=timezone.utc),
        "summary": "",
        "source_type": "news",
        "source_role": "independent_reporting",
        "feed_mode": "core",
        **overrides,
    }


@pytest.mark.parametrize(
    ("left", "right"),
    [
        (
            "OpenAI launches GPT-5.1 coding assistant for developers",
            "OpenAI launches GPT-5.2 coding assistant for developers",
        ),
        (
            "OpenAI releases model for oncology treatment planning",
            "OpenAI releases model for arthritis treatment planning",
        ),
        (
            "OpenAI coding assistant supports private enterprise deployment",
            "OpenAI coding assistant does not support private enterprise deployment",
        ),
        (
            "OpenAI releases GPT-51 coding assistant for developers",
            "OpenAI releases GPT-5.1 coding assistant for developers",
        ),
        (
            "OpenAI coding assistant beats rival in benchmark",
            "Rival beats OpenAI coding assistant in benchmark",
        ),
        (
            "OpenAI launches realtime coding assistant for developers",
            "OpenAI launches realtime coding assistant for enterprise developers",
        ),
    ],
    ids=["version", "indication", "negation", "punctuation", "word-order", "near-duplicate"],
)
def test_distinct_headlines_survive_local_resolution(left, right, monkeypatch):
    items = [_item("a", left), _item("b", right)]
    groups = graph._build_candidate_groups(deepcopy(items))
    assert [{item["id"] for item in group} for group in groups] == [{"a", "b"}]

    resolved, skipped = graph._fallback_resolve_groups(deepcopy(groups))
    assert {item["id"] for item in resolved} == {"a", "b"}
    assert skipped == 0
    assert [item["coverage_sources"] for item in resolved] == [[], []]

    monkeypatch.setattr(graph, "_get_openai_api_key", lambda: "")
    result = graph.node_categorize({"items": deepcopy(items)})
    assert {item["id"] for item in result["items"]} == {"a", "b"}


def test_summary_similarity_does_not_authorize_deletion(monkeypatch):
    summary = "Shared benchmark performance development platform research findings."
    items = [
        _item("a", "OpenAI publishes oncology report", summary=summary),
        _item("b", "OpenAI publishes arthritis report", summary=summary),
    ]
    monkeypatch.setattr(graph, "_get_openai_api_key", lambda: "")
    result = graph.node_categorize({"items": items})
    assert {item["id"] for item in result["items"]} == {"a", "b"}


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("OpenAI launches coding assistant for developers", "OpenAI launches coding assistant for developers"),
        ("  OpenAI launches coding assistant for developers  ", "OPENAI\tlaunches  coding assistant\nfor developers"),
        ("GPT-5.1", "gpt-5.1"),
        ("Straße", "STRASSE"),
    ],
    ids=["identical", "case-whitespace", "short-version", "unicode-casefold"],
)
def test_matching_headlines_keep_one_item_and_distinct_source_coverage(left, right):
    items = [
        _item("a", left),
        _item("b", right, summary="Report explains the release. Further context."),
        _item("c", right, source="  wire a  "),
    ]
    resolved, skipped = graph._fallback_resolve_groups([items])
    assert [item["id"] for item in resolved] == ["a"]
    assert skipped == 2
    assert resolved[0]["coverage_sources"] == ["Wire b"]
    assert resolved[0]["summary_line"] == "Report explains the release."
    assert resolved[0]["_prompt_id"] == "g1i1"


@pytest.mark.parametrize("title", ["", " \t\n", None, 123, {"headline": "missing"}])
def test_unusable_titles_never_become_duplicate_keys(title):
    resolved, skipped = graph._fallback_resolve_groups([[_item("a", title), _item("b", title)]])
    assert [item["id"] for item in resolved] == ["a", "b"]
    assert skipped == 0


def test_original_headlines_take_priority_over_equal_display_titles():
    items = [
        _item("a", "Coding assistant", original_title="OpenAI launches GPT-5.1 coding assistant for developers"),
        _item("b", "Coding assistant", original_title="OpenAI launches GPT-5.2 coding assistant for developers"),
    ]
    resolved, skipped = graph._fallback_resolve_groups([items])
    assert [item["id"] for item in resolved] == ["a", "b"]
    assert skipped == 0


@pytest.mark.parametrize("original", [None, "", "  ", 123])
def test_usable_title_is_used_when_original_is_unavailable(original):
    items = [
        _item("a", "OpenAI launches coding assistant for developers", original_title=original),
        _item("b", "OPENAI launches coding assistant for developers", original_title=original),
    ]
    resolved, skipped = graph._fallback_resolve_groups([items])
    assert [item["id"] for item in resolved] == ["a"]
    assert skipped == 1


def test_matching_short_titles_in_separate_groups_are_not_merged_across_groups():
    groups = graph._build_candidate_groups([_item("a", "GPT-5.1"), _item("b", "GPT-5.1")])
    assert [{item["id"] for item in group} for group in groups] == [{"a"}, {"b"}]
    resolved, skipped = graph._fallback_resolve_groups(groups)
    assert {item["id"] for item in resolved} == {"a", "b"}
    assert skipped == 0
