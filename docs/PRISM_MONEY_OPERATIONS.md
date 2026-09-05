# PRISM on the Money Operations narrative boundary

5 September 2026. This document covers Money Operations only. The existing
payments investigator adapter in `mandate/integrations.py` is unchanged.

## What is traced

PRISM observes **compose() / model phrasing** — the narrative boundary. The
hook is `observe_narrative(...)` in `mandate/money_operations_prism.py`.
Builder 1 may call it after `compose()`. Allowed metadata:

- analysis_id, run_id
- prior / current periods
- calculation_digest
- structured claim IDs and retrieved context IDs
- prompt / template version
- model or provider identity, or `deterministic-template`
- reconciliation status and unexplained-item count
- numeric-validation and citation-validation results
- fallback / error state
- latency and token usage when available

The validated headline/body may be sent as the observed output. That is
phrasing of already-computed claims, not a new calculation.

## What is not traced

- Deterministic engine arithmetic (`analyze`, drivers, shares, reconciliation)
- Raw transaction descriptions or full source rows
- Credentials, API keys, or customer lists beyond claim IDs
- Payment-case investigations (those stay on the existing adapter)

A successful handshake, setup-doctor `live_connected` flag, or a payments
trace does **not** make Money Operations live.

## States (explicit)

| State | Meaning |
|---|---|
| `not_configured` | `PRISMTRACE_API_KEY` or `PRISMTRACE_PROJECT_ID` missing |
| `credential_configured` | Credentials present; no successful handshake yet |
| `credential_ok` | Handshake succeeded. Not live. |
| `live_trace_pending` | A Money Operations narrative was submitted (SDK has no ingest receipt) |
| `live_connected` | This worker received a Money Operations **application** trace ID |
| `error` | Handshake or observe failed |

Default after credentials + handshake: `credential_ok` or, after a send
without a receipt, `live_trace_pending`. A handshake is **never**
`live_connected`.

Environment: `PRISMTRACE_API_KEY`, `PRISMTRACE_PROJECT_ID`, optional
`PRISMTRACE_HOST` (HTTPS origin, default `https://prism.blockconvey.com`).
Network send also requires `MANDATE_ALLOW_SYNTHETIC_EGRESS=1`.
`MANDATE_PRISM_TRANSPORT` defaults to `sdk` (same pin: prismtrace-sdk 0.4.2).
HTTP transport can record `live_connected` only when the trace response
includes an id.

This environment has not received a real Money Operations application
trace unless an operator ran a live send and the HTTP path returned an id.

## Demo (Observe → Improve)

From `mvp/`:

```text
python3.12 scripts/run_prism_money_ops_demo.py
```

1. Weak narrative invents an unsupported Other Opex cause (`$12,400`
   warehouse insurance / vendor onboarding). Claim validation **REJECTS**.
2. Corrected narrative uses the deterministic template and keeps Other
   Opex unexplained. Claim validation **PASSES**.

Without credentials the script exits 0 and prints setup steps. It never
prints credential values. With credentials and synthetic egress it sends
both runs and prints `run_id` / `application_trace_id` only.

## UI contracts (Lead-wired)

`register_money_operations_extensions(app, store, auth)` adds:

- `GET /api/money-operations/analyses/{id}/overview`
- `GET /api/money-operations/analyses/{id}/graph`
- `GET /api/money-operations/analyses/{id}/account-variances`
- `GET /api/money-operations/analyses/{id}/account-variances/{account}`
- `POST /api/money-operations/analyses/{id}/chat` (read-only; auditor allowed)
- `GET /api/money-operations/analyses/{id}/memo`
- `POST /api/money-operations/analyses/{id}/briefing`
- `GET /api/money-operations/analyses/{id}/briefing/audio`

Overview uses `reconciliation_conflicts` and `causally_unexplained`.
Other Opex is not a reconciliation conflict.

List + detail variance routes avoid colliding with the existing service
`GET .../variances/{account_code}` engine payload.

## ElevenLabs (optional)

Disabled unless `MONEY_OPS_AUDIO_ENABLED=true` and
`ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` are set. Audio is produced
only from a controller-approved memo whose `narrative_digest` and
analysis revision still match. Voice cannot approve, edit, submit, or
distribute. If synthesis is unavailable the approved transcript is
returned with `audio_unavailable`.
