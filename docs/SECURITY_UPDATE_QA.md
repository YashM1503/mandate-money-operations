# Security workflow update — QA and release boundary

5 September 2026. Primary scope: synthetic enterprise security questionnaire analyst. Earlier AP implementation remains a separate secondary scenario; its historical payment amounts are not merged with the newer reference deck amounts.

This note records checks actually run after the Cursor builder/evaluator pass. Independent findings are in `docs/CURSOR_EVALUATION.md`. UI walkthrough notes are in `docs/SECURITY_UI_QA.md`.

## Verified in this session

- Security tests: `python3.13 -m pytest tests/test_security.py -q` → **22 passed**, 1 Starlette/httpx deprecation warning, 2.50s. Interpreter: `/opt/anaconda3/bin/python3.13` (system `python3` is 3.9 and cannot import `datetime.UTC`).
- Full suite: `python3.13 -m pytest -q` → **84 passed**, **1 failed**, 1 warning, 9 subtests passed, 21.83s.
  - Failure: `tests/test_integrations.py::test_sdk_public_trace_and_flush` — `ModuleNotFoundError: prismtrace`. Pre-existing environment gap. PRISM was not configured in this pass.
- Security tests now also cover: source-first retrieval before response; MFA contradiction only resolved by the IAM fixture; targeted backup follow-ups; correction memory remaining `user_confirmed`; evidence-backed vs user-confirmed export including unknowns; prompt-injection non-resolution; stale revision 409; duplicate/cycle/rehashed known-ID integrity failure; auditor GET allowed and POST forbidden; pending backup not stolen by “admin”; export/resolution isolation; restore mapped to backups not storage; ordinary “do not ignore” backup sentence; scans question matching configuration-only source; auditor GET does not write/seal; gitignore patterns for runtime secrets.
- Evaluator majors applied and re-tested:
  - E1: `GET /api/security/profile` is read-only (`store.connect` + `security_read`). Persist only from analyst/controller POST.
  - E2: chat user bubbles use `userBubbleLabel`; investigation prompts are not labeled “employee assertion”.
  - E3: offline `localReply` aligned with server intent/vague/no-backup patterns (including `restore` before `stor`, and `do not.*backups` no longer matching “do not ignore … backups”).
  - E4: scans question is now “Is vulnerability scanning configured in CI?” so `evidence_backed` matches configuration evidence, not “conduct.”
  - E6: `.gitignore` now includes `*.sqlite`, `*.db`, `*credentials*`, `.DS_Store`; `data/.gitkeep` restored.
- Browser QA: `CHROME_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" node tests/security_browser_qa.cjs` → **PASS browser: chat, correction, reload, source hash, resolution, export, mobile, WebGL**. Script now clears `localStorage` first. Observed path: login honesty copy, coverage counts, MFA prompt not labeled employee assertion, restore not mapped to AWS RDS, ordinary ignore sentence keeps weekly memory, backup correction, reload persistence, source digest match + integrity≠truth, IAM fixture, JSON export retains unknowns, 390×844 no document overflow.
- Screenshots/export written to `qa-evidence/security-overview.png`, `security-chat.png`, `security-mobile.png`, `security-export.json`.
- Tracked-file secret scan (`git ls-files` against private-key / `sk-` / `AKIA` / `ghp_` patterns): no live-looking secrets.
- Ignore verification (`git check-ignore -v`): `.env`, `data/config.json`, `data/demo-credentials.txt`, `data/mandate.sqlite3`, `credentials.json`, `*.db`, `*.sqlite` are ignored. `data/.gitkeep` is the only intended addable path under `data/` (`git add -n data/` would stage `.gitkeep` only). `.env.example` remains the empty placeholder. Local `data/config.json`, `data/demo-credentials.txt`, and `data/mandate.sqlite3` exist on disk at mode `0600` and must not be copied into a GIDE handoff.

## Not verified or not implemented

Live model-based security conversation, security trace ingestion in PRISM, completed GIDE session, ElevenLabs, Docker engine build, cloud deployment, production tenancy, external audit anchoring and real company controls. Existing AP sponsor adapter does not automatically make the new security workflow sponsor-complete. Connected-mode `/api/login` was not re-walked in Chrome in this session (file:// script only). WebGL-unavailable fallback and `prefers-reduced-motion` freeze were not captured in the Chrome/SwiftShader run. Print/PDF of the memo was not visually re-checked. Demo auditor inspect-only is not in the Playwright default path.

The WebGL animation is a labeled workflow illustration, not live telemetry. Evidence-backed means supported within synthetic source scope; it is not an assertion that an entire company meets a control. Hashes establish consistency, not truth. Support categories are not confidence percentages. Unknowns and conflicts remain in exports.

## Event completion gates

Confirm pre-build rules, exact deadline and contradictory team-size posts with organizers. Implement the bounded security model/trace segment, demonstrate an actual PRISM run and improvement, use GIDE for a substantive code/test change, and save evidence. Do not claim “verified company information” beyond the scoped records or erase uncertainty to produce a completed questionnaire.

Final regression: a question asking whether backups are daily is not stored as an employee assertion. Both standalone and server engines include this safeguard. Both DOCX documents were rendered to three pages each and visually inspected in an earlier pass; they were not re-rendered in this session. The eight-slide reference adaptation was visually reviewed in an earlier pass.
