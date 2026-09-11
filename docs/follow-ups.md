# Deferred digest integrity follow-ups

## Bio decision references and top-story validation — RESOLVED 2026-09-11

Recorded 2026-09-10 from the paired digest design review. Bio was reported to
expose both `item_id` and article `id`, and to accept invalid `top_stories`
references that ranking can silently replace through automatic selection.

Re-verified against Bio's head on 2026-09-11 and confirmed: a URL, an unknown
id, `null`, a bare string, and a duplicate-item reference were all accepted,
after which ranking silently auto-selected a different lead story.

Closed by the Bio-side port, ActioBio/bio-news-agent#399, merged as
`e28a91e4301adf4c0c209bd36dd0c02beee96661`. It carries hash-bound snapshot
guidance, `top_stories` validation after exhaustive dispositions and before
promotion, preserved absent/empty automatic selection, and rejection of
non-lists, non-strings, repeats, and any reference other than a requested
`keep_id`. Bio's API fallback, discovery-only promotion with alias mapping, the
exported article `id`, and its category fallback are unchanged. Two independent
reviewers from different model families approved the exact merged head.

Verified in CI and locally, not by a live digest run. The first live Bio agent
run is the first runtime evidence and will fail closed on decisions previously
tolerated, such as whitespace-padded ids.

## Schema-v5 compatibility regression test

Recorded 2026-09-11 from the Bio implementation review, and it applies to both
repos. Neither test suite pins the compatibility clause that an existing
schema-v5 snapshot without `decision_guidance` still validates and renders. The
`_candidate_v5` helper rebuilds through `build_candidate_envelope`, so every
test snapshot now carries guidance. Reviewers confirmed the clause by execution
against the pre-guidance fixtures, so the behavior is correct but unpinned. A
test that validates and applies a guidance-less v5 snapshot would close it.

## Other separate policy decisions

- AI API enrichment top-story validation remains unchanged in this patch. The
  Bio port did not change its API-enrichment path either, so this gap is open
  in both repos.
- Invalid cluster categories still use the existing categorization fallback;
  snapshot guidance now tells the author to use the canonical categories list.
- Removing the exported article `id`, changing live automation wording, and
  cleaning up CLI error presentation remain separate from this compatibility-
  preserving patch. None is authorized by this follow-up list.
