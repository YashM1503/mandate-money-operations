# Judging metrics — Money Operations

Synthetic January 2026 → February 2026 close. Dollar movements are engine
oracles. Labor dollars are estimates. Do not say the product recovered cash.

| Bucket | Number | What it means / so what |
|---|---|---|
| Hackathon tools · 20% | PRISM 25 → 45 (+80%) | Thin 18% story failed numeric and citation checks. The 18 / 32 / 64 story passed. That is the required PRISM 10%. Native GIDE was opened and rate-limited. ElevenLabs stays behind approval. Prelint and Tavily unused. |
| Financial workflow · 20% | 392 rows · 99 / 107 claims | Eight accounts compared, tied, ranked, and written into a memo. $57,000 Other Opex still needs a person. |
| AI intelligence · 20% | 18.0% / 32.0% / 64.0% | The required sentence is cited, not invented. An invented Other Opex cause was rejected. |
| Business value · 20% | $675,000 explained · ~$270 / close | $432,000 of growth sits in three customers. About 3 hours of analyst work at a $90 blended rate becomes a 45-second signable memo (~$3,200 / year on this step). $57,000 stays open. |
| Product / UX · 20% | 45 s demo · 196 tests | Observe → Improve → Prove is clickable. Suite is green. No public cloud URL. About 70% of this story is on camera. |

Honest target: 80 / 100.

## Measured compute

| Check | Result |
|---|---|
| `analyze` first run | 8.1 ms |
| `analyze` p50 / p95 (n=25) | 4.8 ms / 5.8 ms |
| `compose` | 1.6 ms |
| Pytest | 196 passed + 9 subtests in 62 s |
| Image smoke | `/healthz` ok, `/money-operations` 200 |

## PRISM Observe → Improve

| Run | Trace | Quality | Validation |
|---|---|---|---|
| Weak 18% only | `d285c684-66bf-4e52-bb48-c3e0e4c14cd9` | 25 / 100 | numeric reject, citation reject |
| Corrected 18 / 32 / 64 | `18e10623-749f-48c7-905b-bf703d32beb4` | 45 / 100 | pass / pass |

Project `cb615645-2204-4ce6-a6cb-013562d3cc59`. Runtime remains `live_trace_pending` (no SDK ingest receipt). See `docs/PRISM_LIVE_EVIDENCE.md`.

## GIDE

Native desktop GIDE received the runbook prompt (session `ee1b0b86-a11d-4121-ac06-39295c6344ef`) and was rate-limited after three retries. Status stays `usage_pending`. See `docs/GIDE_ATTEMPT_EVIDENCE.md`.
