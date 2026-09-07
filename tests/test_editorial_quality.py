"""Editorial regressions across daily decisions, API enrichment and local fallback."""

import json
from datetime import datetime, timezone

import pytest

import graph
import publisher
from ranking import render_sort_key, select_top_story_ids, story_rank_key


_ORIGINAL_TITLE = "OpenAI releases coding assistant"


def _item(index, source="Wire A", *, feed_mode="core"):
    return {
        "id": f"article-{index}",
        "title": _ORIGINAL_TITLE,
        "original_title": _ORIGINAL_TITLE,
        "link": f"https://example.com/article-{index}",
        "source": source,
        "published": datetime(2026, 9, 7, 12 - index, tzinfo=timezone.utc),
        "category": "Tools & Applications",
        "summary": "",
        "source_type": "news",
        "source_role": "independent_reporting",
        "feed_mode": feed_mode,
    }


@pytest.fixture(autouse=True)
def _isolate_external_state(monkeypatch, tmp_path):
    monkeypatch.setattr(graph, "_get_openai_api_key", lambda: "")
    monkeypatch.setattr(graph, "_get_dotenv_openai_api_key", lambda: "")
    monkeypatch.setattr(graph, "_NEWS_FILE", tmp_path / "news.md")
    monkeypatch.delenv("DIGEST_ISSUE_TITLE_OVERRIDE", raising=False)
    monkeypatch.setattr(
        publisher, "_utcnow", lambda: datetime(2026, 9, 7, 15, tzinfo=timezone.utc)
    )


def _response(duplicate_ids, **editorial_fields):
    return {"groups": [{
        "group_id": "g1",
        "clusters": [{
            "keep_id": "g1i1",
            "duplicate_ids": duplicate_ids,
            **editorial_fields,
        }],
    }]}


def _apply_daily(tmp_path, items, response):
    snapshot = graph.build_candidate_snapshot(items)
    decisions = {
        "schema_version": 2,
        "kind": "ai-news-agent.decisions",
        "snapshot_id": snapshot["snapshot_id"],
        **response,
    }
    candidates_file = tmp_path / "candidates.json"
    decisions_file = tmp_path / "decisions.json"
    candidates_file.write_text(json.dumps(snapshot), encoding="utf-8")
    decisions_file.write_text(json.dumps(decisions), encoding="utf-8")
    return graph.apply_decisions_file(decisions_file, candidates_file)


@pytest.mark.parametrize("route", ["daily", "api"])
@pytest.mark.parametrize(("fields", "expected"), [
    pytest.param({}, _ORIGINAL_TITLE, id="omitted"),
    pytest.param({"short_title": None}, _ORIGINAL_TITLE, id="null"),
    pytest.param({"short_title": ""}, _ORIGINAL_TITLE, id="empty"),
    pytest.param({"short_title": " \n\t "}, _ORIGINAL_TITLE, id="whitespace"),
    pytest.param({"short_title": 42}, _ORIGINAL_TITLE, id="number"),
    pytest.param({"short_title": {"text": "Wrong type"}}, _ORIGINAL_TITLE, id="object"),
    pytest.param({"short_title": []}, _ORIGINAL_TITLE, id="list"),
    pytest.param({"short_title": False}, _ORIGINAL_TITLE, id="boolean"),
    pytest.param({"short_title": "  A useful\tnew headline  "}, "A useful new headline", id="valid"),
    pytest.param(
        {"short_title": "One two three four five six seven eight nine ten eleven"},
        "One two three four five six seven eight nine ten", id="word-limit",
    ),
])
def test_short_titles_reach_render_and_issue_title_safely(tmp_path, route, fields, expected):
    if route == "daily":
        result = _apply_daily(tmp_path, [_item(0)], _response([], **fields))
    else:
        seeded = graph._seed_resolved_item(_item(0), "g1i1")
        result = graph._apply_enrichment_response(
            {}, [seeded], {"items": [{"item_id": "g1i1", **fields}]},
            skipped_items=0, log_label="test",
        )
        result = graph.node_render(result)

    assert result["items"][0]["title"] == expected
    assert f"**[{expected}](https://example.com/article-0)**" in result["markdown"]
    assert (tmp_path / "news.md").read_text(encoding="utf-8") == result["markdown"]
    assert publisher._issue_title_for_body(result["markdown"]) == f"AI Headlines - Sep 7: {expected}"


@pytest.mark.parametrize("route", ["daily", "api", "heuristic"])
@pytest.mark.parametrize(("duplicate_sources", "expected_sources", "expected_count"), [
    pytest.param([], [], 1, id="singleton"),
    pytest.param(["Wire A", "Wire A"], [], 1, id="same-source"),
    pytest.param(["Wire B", "Wire C"], ["Wire B", "Wire C"], 3, id="distinct"),
    pytest.param(["Wire B", "Wire B"], ["Wire B"], 2, id="repeated"),
    pytest.param([" wire\tA ", " Wire  B ", "wire b", "WIRE C"], ["Wire B", "WIRE C"], 3, id="normalized"),
    pytest.param(["", " \t ", "Wire B"], ["Wire B"], 2, id="blank"),
])
def test_distinct_source_coverage_is_consistent_across_consumers(
    tmp_path, route, duplicate_sources, expected_sources, expected_count,
):
    items = [_item(0), *[_item(i, source) for i, source in enumerate(duplicate_sources, 1)]]
    response = _response(
        [f"g1i{i}" for i in range(2, len(items) + 1)], short_title=_ORIGINAL_TITLE,
    )
    if route == "daily":
        result = _apply_daily(tmp_path, items, response)
    elif route == "api":
        kept, skipped = graph._apply_dedupe_response([(1, items)], response)
        result = graph._apply_enrichment_response(
            {}, kept, {"items": [{"item_id": "g1i1", "short_title": _ORIGINAL_TITLE}]},
            skipped_items=skipped, log_label="test",
        )
        result = graph.node_render(result)
    else:
        result = graph.node_render(graph.node_categorize({"items": items}))

    assert len(result["items"]) == 1
    kept = result["items"][0]
    assert kept["coverage_sources"] == expected_sources
    assert graph._serialize_enrichment_item(kept)["coverage_count"] == expected_count
    assert story_rank_key(kept)[3] == -(expected_count - 1)
    assert render_sort_key(kept)[2] == -(expected_count - 1)
    if expected_count == 1:
        assert " sources)" not in result["markdown"]
    else:
        assert f"— Wire A ({expected_count} sources)" in result["markdown"]


@pytest.mark.parametrize("route", ["daily", "api"])
def test_coverage_excludes_promoted_keep_source(tmp_path, route):
    items = [
        _item(0, "Wire A", feed_mode="discovery_only"),
        _item(1, "Wire B"),
        _item(2, " wire  b "),
    ]
    response = _response(["g1i2", "g1i3"], short_title=_ORIGINAL_TITLE)
    if route == "daily":
        # Candidate export orders the two core items before the discovery item.
        response["groups"][0]["clusters"][0].update(
            keep_id="g1i3", duplicate_ids=["g1i1", "g1i2"],
        )
        result = _apply_daily(tmp_path, items, response)
        kept = result["items"][0]
        assert kept["_prompt_id"] == "g1i1"
    else:
        result, _ = graph._apply_dedupe_response([(1, items)], response)
        kept = result[0]
        assert kept["_prompt_id"] == "g1i2"

    assert kept["source"] == "Wire B"
    assert kept["coverage_sources"] == ["Wire A"]
    assert graph._serialize_enrichment_item(kept)["coverage_count"] == 2
    assert "— Wire B (2 sources)" in graph.to_markdown([kept])


def test_repeated_api_ids_do_not_inflate_visible_source_coverage():
    kept, skipped = graph._apply_dedupe_response(
        [(1, [_item(0), _item(1, "Wire B")])],
        _response(["g1i2", "g1i2"]),
    )

    # Identity validation/accounting is deliberately deferred; coverage has a separate invariant.
    assert skipped == 2
    assert kept[0]["coverage_sources"] == ["Wire B"]
    assert graph._serialize_enrichment_item(kept[0])["coverage_count"] == 2
    assert "— Wire A (2 sources)" in graph.to_markdown(kept)


def test_same_source_repetition_does_not_outrank_a_newer_story():
    repeated = graph._seed_resolved_item(
        _item(1), "g1i1", duplicate_items=[_item(2)],
    )
    newer = graph._seed_resolved_item(_item(0), "g2i1")

    assert select_top_story_ids([repeated, newer], []) == ["g2i1", "g1i1"]
    assert [item["_prompt_id"] for item in sorted([repeated, newer], key=render_sort_key)] == ["g2i1", "g1i1"]
