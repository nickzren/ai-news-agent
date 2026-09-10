# Deferred digest integrity follow-ups

## Bio decision references and top-story validation

Recorded 2026-09-10 from the paired digest design review. Bio was reported to
expose both `item_id` and article `id`, and to accept invalid `top_stories`
references that ranking can silently replace through automatic selection.
Re-verify against Bio's current head before implementing a separate change.

This AI-only patch does not fix or authorize changes to Bio. A future Bio review
should cover missing/empty selection compatibility, requested keeps before
promotion, rejection before rendering, and its distinct API fallback policy.

## Other separate policy decisions

- AI API enrichment top-story validation remains unchanged in this patch.
- Invalid cluster categories still use the existing categorization fallback;
  snapshot guidance now tells the author to use the canonical categories list.
- Removing the exported article `id`, changing live automation wording, and
  cleaning up CLI error presentation remain separate from this compatibility-
  preserving patch. None is authorized by this follow-up list.
