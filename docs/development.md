# Development

## Prerequisites

- Python 3.12+ with pip
- Node.js for the executable workflow contract tests (available on GitHub-hosted runners).

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

### Publication safety

`--dispatch-publish` freezes one `America/New_York` date and sends it as the required `digest_date` workflow input alongside the title and compressed body. The receiver passes it unchanged as `DIGEST_DATE`. Actions publishing rejects missing, malformed, noncanonical, past or future dates before contacting GitHub, and checks the date again after issue lookup before starting a write. An observed Eastern date change stops publication; a UTC date change alone does not invalidate the payload. The guard cannot undo a request already accepted by GitHub.

The API-build workflow freezes `DIGEST_DATE` before preflight and build. Title generation and issue selection use that same date. Both publishing workflows share the repository-wide `digest-publish-${{ github.repository }}` concurrency group with `cancel-in-progress: false` and `queue: max`. This serializes Actions publishers, retains up to 100 pending runs, and leaves the existing final issue lookup inside the lock. Same-day retries update the existing issue rather than create another. Queue order is not a promise of dispatch order. See [GitHub concurrency documentation](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).

Direct local `--publish-issue` without `DIGEST_DATE` remains a manual fallback using the date when the command starts; an explicitly supplied date is still validated. It does not participate in the Actions lock and must not run concurrently with Actions publishers. Standalone `--check-issue` still checks today's issue. The date binds dispatch/build to publication, not the age of an arbitrary local `news.md`; regenerate stale local output instead of redispatching it as new news.

For rollout, merge the producer, receiver and workflow lock together in each repo, then update the local checkout before the next agent run. Older callers missing `digest_date` fail closed against the new receiver. Already-running workflows using older code are not retroactively protected; let those finish or handle them explicitly before relying on the new gate. No schedule or fallback-policy change is part of this batch.


## API response contract

The API graph uses separate dedupe and enrichment responses:

- Dedupe must return every requested group exactly once and account for every requested item exactly once as a keep or duplicate within its own group. Distinct keeps require explicit singleton clusters with `duplicate_ids: []`, including discovery-only items. Off-topic filtering belongs to enrichment; dedupe may omit `off_topic_ids` or leave it empty.
- Enrichment must account for every requested item ID exactly once in `items` or `off_topic_ids`, with no overlap, repeats, or unknown IDs. An omitted `off_topic_ids` defaults to an empty list.
- The complete set of response dispositions is validated before applying response contents or promoting a requested keep. Omitted candidates are not silently seeded or retained. Valid singleton/promotion behavior and optional title/summary defaults remain unchanged. Duplicate counts include each discarded item once; distinct-source coverage remains a separate measure.

Invalid API responses raise and stop the graph before rendering, as do other attempted API failures. The existing no-key local path remains available.

Local duplicate removal requires a nonempty full original headline matching another
headline in the same candidate group after case and whitespace normalization. If
the original headline is unavailable, it uses the source title. Numbers,
punctuation and word order are preserved; shared words or summaries alone do not
authorize removal. Candidate grouping remains deliberately broader, and API/agent
editorial duplicate decisions are unchanged. This conservative fallback may retain
multiple reports of one event. Conversely, identical generic headlines can still
describe different events; headline equality is not semantic verification.

These API responses do not use the candidate snapshot/agent-decision envelope. The daily agent path and live automation prompts are unchanged.

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
          "category": "Research & Models",
          "short_title": "Researchers release a new reasoning model",
          "summary_line": "Why this matters in one sentence.",
          "tier": "normal"
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

Use a canonical category from the candidate snapshot and a `tier` of `high` or `normal`. Optional `short_title` values that are missing, null, non-string, or blank retain the original source title. Valid strings have whitespace normalized and are limited to 10 words. This applies to agent decisions and API enrichment.

The resolved `coverage_sources` list contains additional distinct sources, excluding the kept source. Source labels have leading, trailing, and repeated whitespace normalized and are compared case-insensitively; empty labels are ignored and the first normalized display spelling is preserved. Coverage counts used in rendering, ranking, and API enrichment represent distinct source/newsroom labels, not the number of URLs. Publisher aliases are not merged.

`--dispatch-publish` sends the rendered digest to the publish-only GitHub Actions workflow so the final issue author is `app/github-actions`, which is friendlier to watch-email notifications than publishing through your own local GitHub identity.

The default digest output is compact and title-first. `summary_line` and `executive_summary` are kept as decision metadata and are not rendered in the issue body. The published issue title appends the leading top story, e.g. `AI Headlines - Jun 12: Bezos' Prometheus raises $12B`, while same-day deduplication matches on the `ai-digest` label and creation date rather than the title.

## Feed configuration

The collector reads RSS feed URLs from [`feeds.json`](../feeds.json) in the project root. The file should contain a JSON object where each key is a feed URL and each value specifies the `category` and human-readable `source` name.

RSS and Atom relative links are resolved before URL normalization and deduplication.
The final response URL (after redirects) supplies the default base; an absolute or
relative `Content-Location` header overrides it, and nested `xml:base` attributes
are handled by feedparser. See [feedparser's resolution rules](https://feedparser.readthedocs.io/en/stable/resolving-relative-links.html).

Collection captures one UTC timestamp before fetching any feeds. Dated items are
accepted from exactly 24 hours before that timestamp through exactly one hour after
it, inclusive. The one-hour allowance tolerates publisher clock skew; later dates
and missing dates are excluded. Fetch duration does not move either boundary.
Filtering dates does not turn a successfully fetched and parsed feed into a failure;
feed-health and empty-day policies are unchanged.

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
