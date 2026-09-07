# Development

## Prerequisites

- Python 3.12+ with pip

## Quick start

### 1. Install UV

```bash
pip install uv
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
# Placeholder values such as sk-... or your_api_key_here are treated as missing
```

The default API fallback model is `gpt-5.6-luna`. Set `OPENAI_MODEL` to override it.

### 3. Run

```bash
uv run python src/main.py
```

## CI and scheduled runs

Scheduled GitHub Actions fallback runs target 12:30 PM `America/New_York` and use that timezone when matching today's digest issue and generating its title. This keeps DST changes and delayed runs from shifting the digest to the wrong calendar day. The fallback checks for the issue before calling the LLM, so it skips duplicate builds. Manual workflow dispatch intentionally bypasses that scheduled preflight. Push and pull request CI runs `pytest` and `mypy`. Scheduled agent runs generate locally and dispatch the final publish through GitHub Actions. Direct `--publish-issue` remains a manual fallback.

## Agent-driven mode

This path keeps feed collection and filtering in Python, but lets Codex or Claude Code handle dedupe/categorization without `OPENAI_API_KEY`.

**The canonical operational runbook is [AGENTS.md](../AGENTS.md).** This section is for developers who need the CLI command reference and the agent-decision JSON contract.

CLI commands used by the agent flow:

```bash
uv run python src/main.py --check-issue --issue-status-file digest-issue-status.json
uv run python src/main.py --candidates-only
# agent reads digest-candidates.json and writes digest-decisions.json
uv run python src/main.py --apply-decisions digest-decisions.json
uv run python src/main.py --dispatch-publish
```

`--check-issue` writes `digest-issue-status.json` by default. `--candidates-only` writes `digest-candidates.json` and `digest-run-status.json` by default. Use `--candidates-file <path>`, `--status-file <path>`, and `--issue-status-file <path>` to override these artifacts.

### Decision schema

Agent decisions should use this JSON shape:

```json
{
  "schema_version": 2,
  "kind": "ai-news-agent.decisions",
  "snapshot_id": "sha256:<copy exactly from digest-candidates.json>",
  "executive_summary": "2-3 sentence overview of today's AI news.",
  "top_stories": ["g1i1"],
  "groups": []
}
```

The empty `groups` skeleton above is valid only for a candidate snapshot with no groups; it is invalid for every nonempty snapshot. Every candidate group must appear exactly once, and every candidate item must be dispositioned exactly once as a keep, duplicate, or off-topic item. For example, given `g1i1` as a kept singleton, `g2i1` and `g2i2` as duplicate coverage of one story, and `g3i1` as off-topic, the exhaustive decisions are:

```json
{
  "schema_version": 2,
  "kind": "ai-news-agent.decisions",
  "snapshot_id": "sha256:<copy exactly from digest-candidates.json>",
  "executive_summary": "2-3 sentence overview of today's AI news.",
  "top_stories": ["g1i1"],
  "groups": [
    {
      "group_id": "g1",
      "off_topic_ids": [],
      "clusters": [
        {
          "keep_id": "g1i1",
          "duplicate_ids": [],
          "category": "Tools & Applications",
          "short_title": "OpenAI launches coding assistant",
          "summary_line": "Why this matters in one sentence.",
          "tier": "high"
        }
      ]
    },
    {
      "group_id": "g2",
      "off_topic_ids": [],
      "clusters": [
        {
          "keep_id": "g2i1",
          "duplicate_ids": ["g2i2"],
          "category": "Models & Research",
          "short_title": "Researchers release a new reasoning model",
          "summary_line": "Why this matters in one sentence.",
          "tier": "medium"
        }
      ]
    },
    {
      "group_id": "g3",
      "off_topic_ids": ["g3i1"],
      "clusters": []
    }
  ]
}
```

Every cluster must contain a list-valued `duplicate_ids`; use `[]` for a kept singleton. A standalone `discovery_only` item is valid decision input and must still be represented as an explicit singleton keep, but it is removed later during rendering. Decisions are fully validated, including snapshot binding and exhaustive dispositions, before any keep is promoted. Stale or partial decisions invalidate and remove any prior generated `news.md`, then stop before rendering or dispatch.

`--dispatch-publish` sends the rendered digest to the publish-only GitHub Actions workflow so the final issue author is `app/github-actions`, which is friendlier to watch-email notifications than publishing through your own local GitHub identity.

The default digest output is compact and title-first. `summary_line` and `executive_summary` are kept as decision metadata and are not rendered in the issue body. The published issue title appends the leading top story, e.g. `AI Headlines - Jun 12: Bezos' Prometheus raises $12B`, while same-day deduplication matches on the `ai-digest` label and creation date rather than the title.

## Feed configuration

The collector reads RSS feed URLs from [`feeds.json`](../feeds.json) in the project root. The file should contain a JSON object where each key is a feed URL and each value specifies the `category` and human-readable `source` name.

Optional fields:

- `type`: source-specific handling such as paper limits
- `source_role`: source authority for duplicate tie-breaks and ranking. Supported values: `primary`, `independent_reporting`, `commentary`, `community`.
- `feed_mode`: whether a feed is part of the main digest or supporting discovery only. Supported values: `core`, `discovery_only`.

```json
{
  "https://example.com/feed.xml": {
    "source": "Example Feed",
    "category": "All",
    "type": "news",
    "source_role": "independent_reporting",
    "feed_mode": "core"
  }
}
```
