# Cursor prompt — integrate the Money Operations UI and prove the reference case

Paste the text below into Cursor at the `mvp/` repository root.

```text
Act as the integration lead for the MANDATE Money Operations MVP. Work in the existing repository; do not redesign the UI, replace the deterministic engine, remove existing security/payment routes, push, deploy, or claim sponsor completion. The working tree is intentionally uncommitted, so inspect before editing and preserve unrelated changes.

Primary outcome
Create one real, locally runnable, API-backed demo that starts from the packaged synthetic dataset and proves this chain:

January 2026 → February 2026 gross revenue increased $675,000, or 18.0%; enterprise contributed $576,000, or 32.0%; C001/C002/C003 contributed $432,000, exactly 64.0% of total revenue growth. Prior-close context may support the Software explanation only after current-run confirmation. Other Opex increased $57,000, reconciles numerically, and remains causally unexplained until human review.

The existing visual replay in static/money-operations.html is the approved design. Preserve its layout, typography, responsive behavior, WebGL graph, synthetic replay mode, and honesty labels. Connect its existing BackendAdapter boundary to the implemented API contracts. Do not hard-code live-mode figures or turn API failures into demo data.

If Cursor supports parallel agents, use them only for independent inspection: one reads API response contracts, one maps UI state/actions, and one designs connected browser tests. The lead agent owns all edits and integration to prevent conflicting writes.

Read first
- static/money-operations.html
- docs/MONEY_OPERATIONS_UI_HANDOFF.md
- docs/openapi.json
- mandate/money_operations_service.py
- mandate/money_operations_contracts.py
- mandate/money_operations_audio.py
- mandate/money_operations_prism.py
- docs/PRISM_MONEY_OPERATIONS.md
- docs/GIDE_EVALUATION_RUNBOOK.md
- tests/test_money_operations_extensions.py

Phase 1 — serve and connect the UI
1. Add GET /money-operations in mandate/api.py to serve static/money-operations.html with the same security treatment used by the other unified pages. Keep / and /security unchanged.
2. Keep Synthetic replay working without a server. In Connected API mode:
   - POST /api/login with entered credentials and keep the bearer token in memory only.
   - POST /api/money-operations/datasets with {"fixture":"reference"}.
   - POST /api/money-operations/analyses using the returned dataset ID, entity_id "yari-retail-us", prior_period "2026-01", current_period "2026-02", and the returned dataset revision when available.
   - Fetch in parallel after analysis creation: overview, graph, account-variances, context, memo, escalations, lineage, and integration-status.
   - Normalize those payloads into the UI state inside BackendAdapter/normalizeLiveAnalysis. Convert integer minor units only at the display boundary. Never parse formatted currency back into calculations.
3. Bind every visible connected-mode function:
   - Overview cards and agent graph use overview/graph responses.
   - Variance Explorer uses account-variances and account detail. Evidence links call the claim evidence route.
   - Ask Mandate posts {"question":...} to /chat, renders returned claim IDs/citations/limitations, and remains read-only.
   - Context confirmation posts {"expected_revision": currentContextRevision} to /context/{id}/confirm, then refetches the analysis, overview, context, memo, and revision-sensitive state. A 409 must show a stale-state message and refetch rather than retrying blindly.
   - Review posts the current analysis ID, analysis revision, calculation digest, narrative digest, and decision to /review. Do not let the browser create an approval locally.
   - Memo uses /memo for structured display and /memo.html for print/download when appropriate.
   - Export buttons use the server export.json/export.csv routes in connected mode.
4. Make roles explicit. Analysis/context actions require an analyst or controller session; approval requires a controller session. Provide a small re-authenticate/switch-role modal for the approval step. Never persist passwords or bearer tokens to localStorage, source, logs, screenshots, or test artifacts.
5. Add loading, empty, 401/403/409, and network-error states without losing the existing visual structure. Display “Connected API” only after analysis creation and successful contract loading. Keep “Synthetic replay” obvious in offline mode.

Phase 2 — prove Goal State 1 with packaged synthetic data
6. Add a connected Playwright browser test that boots the actual FastAPI app in an isolated temporary MANDATE_DATA_DIR, uses freshly generated demo credentials, opens /money-operations, and exercises the API-backed path. The test must prove from rendered UI and API responses:
   - +$675,000 and +18.0% gross revenue
   - +$576,000 and +32.0% enterprise
   - +$432,000 and 64.0% for C001/C002/C003
   - calculation digest remains stable
   - source/claim lineage is inspectable
   - NovaERP is suggested before confirmation and user_confirmed afterward
   - confirming context does not change any calculated amount/share/claim ID and invalidates stale approval state
   - Other Opex is +$57,000, reconciled, causally unexplained, and routed to human review
   - chat cannot approve, edit, submit, or distribute
7. Keep the existing offline UI test. Add desktop and mobile screenshots for the connected reference run, with no secrets in the artifacts.

Phase 3 — PRISM integration proof
8. Do not rewrite the existing PRISM adapter. Run its mocked tests and inspect the allowlist boundary. The deterministic arithmetic and raw rows must not be sent to PRISM.
9. If PRISMTRACE_API_KEY and PRISMTRACE_PROJECT_ID are already present in the process environment, and only then, run scripts/run_prism_money_ops_demo.py with MANDATE_ALLOW_SYNTHETIC_EGRESS=1. Capture only safe run IDs/application trace IDs and status; never print or store credentials. Demonstrate Observe → Improve → Prove: the weak invented Other Opex narrative rejects, the corrected cited narrative passes.
10. A handshake is not live usage. Set/show live_connected only if this Money Operations run receives an application trace ID. Otherwise retain credential_ok or live_trace_pending and document the exact remaining operator step.

Phase 4 — ElevenLabs optional briefing
11. Wire “Listen to briefing” to POST /api/money-operations/analyses/{id}/briefing. Before controller approval, show approval_required and the safe transcript. After approval, if audio is enabled and synthesis succeeds, fetch /briefing/audio and play it with native controls.
12. If MONEY_OPS_AUDIO_ENABLED is false or ElevenLabs credentials are absent, keep the approved transcript usable and show audio_unavailable/provider=none. Do not block Goal State 1 on voice. Voice must never approve, edit, submit, or distribute and must never synthesize a stale revision/digest.
13. Do not add credentials to files. Use only MONEY_OPS_AUDIO_ENABLED, ELEVENLABS_API_KEY, and ELEVENLABS_VOICE_ID from the runtime environment. Mock provider calls in automated tests; make one live call only when the operator has configured credentials and explicitly runs the app in that environment.

Phase 5 — GIDE boundary
14. Cursor is not GIDE. Do not mark gide complete and do not manufacture JSONL evidence. Keep usage_pending in the UI/API unless a real native GIDE session has produced reviewed evidence.
15. Ensure docs/GIDE_EVALUATION_RUNBOOK.md remains runnable after your changes. Add the UI integration tests to its inspection/test list if needed. The actual GIDE run will happen separately in the GIDE desktop app and must create docs/GIDE_EVALUATION.md with the real session evidence path.

Required validation
- Run the six Money Operations Python suites from the existing closeout; all must remain green.
- Run the full pytest suite.
- Run scripts/run_evaluation.py and retain 12/12.
- Run the offline UI QA and the new connected UI QA.
- Confirm static/index.html and static/security.html hashes remain 478b6e122783ba6d33af999c56000c448b301d98f43ae281533e6d9dd8395333 and ae03afb0b864b4052ccf0d0221fe0ed83e13a640aa79e3b561fb557130ca09ad.
- Scan tracked changes for live-looking secrets. Do not add data/, .env, demo-credentials.txt, sqlite files, or credential files.

Stop conditions and reporting
- Do not push, deploy, merge, or commit.
- Do not claim PRISM live without a Money Operations application trace ID.
- Do not claim GIDE used from this Cursor run.
- Do not claim ElevenLabs live when only mocks or transcript fallback ran.
- Do not invent a cause for Other Opex.
- Do not alter the canonical reference figures.

At completion report: files changed; the exact connected demo path; browser and API assertions; test counts; oracle values; calculation digest; context state before/after; review binding behavior; PRISM state plus trace ID if real; ElevenLabs state; GIDE still pending/completed based only on real evidence; secret scan; and remaining operator steps. Separate implemented, mocked, live-verified, and pending states.
```
