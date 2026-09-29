# Known limitations

Accepted for now. None of these is scheduled work.

- **Repeated stories after a late digest.** Candidates come from a rolling 24-hour window, so a late digest's window can overlap the next one. Four digest pairs between Aug 27 and Sep 11 repeated 17 URL occurrences in total, all around irregular publication times; no later repeats through Sep 29, 2026. Revisit if late publications recur.
- **Discovery-only candidates can mask a failed news feed.** If the core news feeds have no fresh stories and at least one of them fails, discovery-only candidates keep the snapshot non-empty. The run then counts as healthy and can publish a "no fresh headlines" digest instead of retrying and reporting the failure. Reproduced locally; production occurrence unverified.
- **Fallback top stories are not validated.** On the API fallback path, unknown `top_stories` references are dropped silently; if none remain, top stories are selected automatically. Agent decisions are validated.
- **Unknown cluster categories fall back to keyword categorization** instead of failing.
- **Schema-v5 snapshots without `decision_guidance` remain supported** but no test pins that compatibility.
