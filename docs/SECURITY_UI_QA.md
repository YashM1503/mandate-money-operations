# Security UI QA

5 September 2026. Scope: visible security workspace only (`static/security.html`). Engine, API, and Python tests were not changed.

## Surfaces reviewed

- Login / persona entry (demo label vs connected credentials)
- Overview coverage counts and MFA / unknown priorities
- Evidence-flow illustration (WebGL + static six-stage fallback)
- Analyst chat chips (MFA conflict, backups, correction)
- Source inspector digest + “integrity ≠ truth”
- Questionnaire JSON/CSV export
- Executive decision memo
- Assurance / support-status copy
- Layout at 1440×1000 and 390×844

## What changed

- Wired the unused premium entry/shell styles so the live page matches that layout instead of the simpler overlay stylesheet.
- Demo entry now presents **Yari (investigator)** vs **Auditor (inspect-only)** as labels only. Demo is stated as not authentication. Connected mode still requires a provisioned username and password; no password is stored in the HTML; the browser does not invent a server session.
- Overview counts are labeled as coverage of eight items, not a score. MFA conflict and unknowns stay on the page until evidence changes.
- WebGL remains a labeled workflow illustration. If WebGL is missing, a static six-stage list replaces the blank canvas. If WebGL is present and `prefers-reduced-motion` is set, the existing freeze is kept.
- Chat, export, memo, and footer copy still deny live AI, certification, live PRISM, and measured business outcomes.
- Browser QA script writes screenshots and the JSON export under `qa-evidence/`.

## Browser QA

Command (from `mvp/`):

```bash
CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" node tests/security_browser_qa.cjs
```

**Observed result: PASS**

```
PASS browser: chat, correction, reload, source hash, resolution, export, mobile, WebGL
```

Playwright 1.62.1 launched system Chrome (SwiftShader). The script is a `file://` walkthrough. Connected-mode `/api/login` was not exercised.

Artifacts:

- `qa-evidence/security-overview.png`
- `qa-evidence/security-chat.png`
- `qa-evidence/security-mobile.png`
- `qa-evidence/security-export.json` (unknowns retained; after the scripted IAM fixture, `background_checks` remains `unknown`)

## Labeling / honesty checks

- Demo chip / footer: synthetic local replay, not authentication; no certification; no live model; PRISM / GIDE / ElevenLabs not complete.
- Support categories remain Evidence-backed / User-confirmed / Unknown / Conflict.
- Source inspector still reports digest match/mismatch and that integrity is not truth. Dynamic strings go through `esc()`.
- Memo still requires human review and states no external submission, time, revenue, or compliance claim.

## Remaining UI limitations

- Connected username/password and auditor write-denial were not browser-tested against a running API.
- The WebGL-unavailable fallback was not seen in this Chrome run (WebGL initialized). Reduced-motion freeze was not separately captured.
- Print/PDF of the memo was not visually checked.
- Demo auditor inspect-only disables local write controls; that path is not in the Playwright script (default remains Yari).
- Toast after export can sit over the overview scene until it times out.
- Local replay is still editable `localStorage`, not an audit log.
