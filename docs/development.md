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

### 3. Run

```bash
uv run python src/main.py
```

## CI and scheduled runs

Scheduled GitHub Actions runs check for today's digest issue before calling the LLM, so fallback CI skips duplicate builds. Push and pull request CI runs `pytest` and `mypy`. Scheduled agent runs generate locally and dispatch the final publish through GitHub Actions. Direct `--publish-issue` remains a manual fallback.

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
  "executive_summary": "2-3 sentence overview of today's AI news.",
  "top_stories": ["g1i1"],
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
          "summary_line": "Why this matters in one sentence.",
          "tier": "high"
        }
      ]
    }
  ]
}
```

Use `off_topic_ids` to drop low-signal or off-topic items from a group. For singleton groups, set `clusters` to `[]` and list the item id in `off_topic_ids`.

`--dispatch-publish` sends the rendered digest to the publish-only GitHub Actions workflow so the final issue author is `app/github-actions`, which is friendlier to watch-email notifications than publishing through your own local GitHub identity.

The default digest output is compact and title-first. `summary_line` renders as one indented line under each Top Story; category sections stay title-only, and `executive_summary` is not rendered. The published issue title appends the leading top story, e.g. `AI Headlines - Jun 12: Bezos' Prometheus raises $12B`, while same-day deduplication matches on the `ai-digest` label and creation date rather than the title.

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
