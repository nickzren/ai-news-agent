# AI News Agent

## Purpose
- Build the daily AI digest locally with an agent.
- Publish the final issue through GitHub Actions so the issue author is `app/github-actions`.

## Where To Look
- `README.md` is for newsletter readers only; keep it free of developer detail.
- [docs/development.md](docs/development.md): setup, CI and scheduled runs, API response contract, agent-driven mode and decision schema, feed configuration.
- [docs/architecture.md](docs/architecture.md): pipeline diagrams and design notes.
- [docs/follow-ups.md](docs/follow-ups.md): known limitations.
- [feeds.json](feeds.json): news sources.

## Verify Changes
1. `UV_CACHE_DIR=.uv-cache uv sync --locked --extra dev`
2. `UV_CACHE_DIR=.uv-cache uv run pytest -q`
3. `UV_CACHE_DIR=.uv-cache uv run mypy src`

## Preferred Agent Flow
1. `UV_CACHE_DIR=.uv-cache uv sync --locked`
2. `uv run python src/main.py --check-issue --issue-status-file digest-issue-status.json`
3. Stop if `digest-issue-status.json` says `ok: true` and `exists: true`.
4. Stop if it says `ok: false` and `retryable: false`.
5. If it says `ok: false` and `retryable: true`, continue.
6. `RSS_MAX_WORKERS=2 RSS_TIMEOUT=15 uv run python src/main.py --candidates-only --status-file digest-run-status.json`
7. If `digest-run-status.json` says `feed_fetch_failed` or `empty_snapshot_with_feed_errors`, retry once with `RSS_MAX_WORKERS=1 RSS_TIMEOUT=20`.
8. If the retry still fails, stop and report the failure reason.
9. If status is healthy, write `digest-decisions.json` using the repo decision schema.
10. `uv run python src/main.py --apply-decisions digest-decisions.json`
11. `uv run python src/main.py --dispatch-publish`
12. Wait briefly, then re-run `--check-issue` to confirm the issue exists.

## Defaults
- Prefer the agent path above for daily runs.
- Do not use `uv run python src/main.py` for the daily automation path unless explicitly asked. That is the repo's default graph path and may use the repo LLM API path.
- `--publish-issue` is a manual fallback only.
- `--dispatch-publish` is the normal final publish path.
- `--dispatch-publish` needs workflow-dispatch-capable GitHub auth through authenticated local `gh`, or through `DIGEST_GITHUB_TOKEN`, `GITHUB_TOKEN` / `GH_TOKEN` in CI-style environments.
- For local Codex automation, use authenticated local `gh`; if it fails with 401, re-authenticate `gh` instead of switching the runbook to direct publish.

## Status Artifacts
- `digest-run-status.json`: feed health and candidate export status.
- `digest-issue-status.json`: issue existence or GitHub preflight status.
- `digest-candidates.json`: grouped candidate snapshot.
- `digest-decisions.json`: agent editorial decisions.
- `news.md`: rendered digest body.

## Editorial Bar
- Mark tutorials, Academy lessons, prompt guides, event promos, conference marketing, discount posts, and lightweight culture or reaction pieces as off-topic unless they reflect a material industry change. This is the same bar the API fallback applies.
- Keep quiet days short; do not pad the digest to reach a length.

## Decision Shape
- For the full input contract, inspect the current `digest-candidates.json`, including `decision_guidance`, and the decision-schema section in [docs/development.md](docs/development.md). `keep_id`, `duplicate_ids`, `off_topic_ids`, and `top_stories` refer to candidate `item_id` values such as `g1i1`, never the article's `id` or `link`.
- Choose cluster categories from the snapshot's top-level `categories` list, not the candidate item's category (which may be `All`).
- Copy candidate `snapshot_id` exactly into decisions schema v2 with kind `ai-news-agent.decisions`.
- Include every candidate group exactly once and disposition every item exactly once as keep, duplicate, or off-topic.
- Represent every distinct kept item, including `discovery_only`, as an explicit singleton cluster with `duplicate_ids: []`.
- `--apply-decisions` invalidates any existing `news.md` before validation. If it exits nonzero, stop and do not run `--dispatch-publish`.
- If binding or exhaustive validation fails, stop before dispatch; never repair the decisions with local passthrough.
- `clusters`: duplicate groups with `keep_id` and `duplicate_ids`
- `top_stories`: omit or use `[]` for automatic selection; otherwise supply unique strings naming your requested `keep_id` values, before internal promotion. Duplicate/off-topic IDs, URLs, and malformed values are rejected.
- `executive_summary`
- `off_topic_ids`

## Generated Files
- Treat `digest-candidates.json`, `digest-decisions.json`, `digest-run-status.json`, `digest-issue-status.json`, and `news.md` as generated local artifacts.
- Do not commit them unless explicitly asked.

## Troubleshooting
- If candidate export fails, inspect `digest-run-status.json` first.
- Check `digest-run-status.json.feed_errors` first for sample feed failures before looking elsewhere.
