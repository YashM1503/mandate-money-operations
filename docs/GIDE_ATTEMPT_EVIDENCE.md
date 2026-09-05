# Native GIDE attempt — rate limited

5 September 2026. This is **not** a completed GIDE evaluation. Cursor did
not perform the evaluation. Native GIDE was opened, given the runbook
prompt, began thinking, and was refused by the product rate limiter.

API/UI status remains `gide: usage_pending`. Do not treat this file as
`docs/GIDE_EVALUATION.md`. That artifact was never created by GIDE.

## What ran

| Item | Value |
|---|---|
| Product | `/Applications/GIDE.app` (native desktop, not Cursor) |
| Workspace | Repository `mvp/` root |
| Prompt | Exact “One exact prompt” from `docs/GIDE_EVALUATION_RUNBOOK.md` |
| Session | `ee1b0b86-a11d-4121-ac06-39295c6344ef` |
| Operator time | 13:20–13:23 EDT |

GIDE invoked its V5 agentic loop on the Money Operations prompt. The UI
showed Thinking, then:

> Rate Limited. Too many requests. The system is waiting and will retry automatically. Attempted 3 retries.

The GIDE renderer logged the same text three times, then again on a second
invoke. The server never executed the pytest suite for this session and
never wrote `docs/GIDE_EVALUATION.md`.

An earlier session (`10f17954-5a0d-4895-8c05-cb55378860a4`) planned the
eight evaluation todos, then hung on `posix_spawnp failed` while spawning
its persistent shell. That run also produced no evaluation artifact.

## Screenshots

- Thinking on the native prompt: `qa-evidence/gide-attempt/gide-thinking.png`
- Product refusal: `qa-evidence/gide-attempt/gide-rate-limited.png`

No credentials, `.env`, `data/`, or demo passwords are in these images.

## Honesty for demo / submission

This package already treats a live model call as optional; the organizer
accepted a synthetic / proof-of-concept agent path. The same honesty
applies here:

- Native GIDE **was used**. The prompt was submitted to GIDE’s own agent.
- Native GIDE **did not complete** the eight evaluation steps.
- The blocker is GIDE’s own rate limit (and an earlier shell-spawn fault),
  not a Cursor substitute evaluation.
- Canonical Jan→Feb figures and Other Opex unexplained were not changed.
- PRISM dashboard traces remain a separate artifact
  (`docs/PRISM_LIVE_EVIDENCE.md`).

If organizers require a finished GIDE JSONL plus `docs/GIDE_EVALUATION.md`,
this attempt is not that. If they accept documented native-product use
plus a product-side refusal, this is the evidence.
