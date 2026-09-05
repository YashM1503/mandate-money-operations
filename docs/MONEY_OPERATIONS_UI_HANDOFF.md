# Money Operations UI handoff

`static/money-operations.html` is a standalone interactive prototype for the Maximor Money Operations reference case. It does not change the existing payment or security pages.

## Implemented in the browser prototype

- synthetic login and explicit connected-mode placeholder
- February close overview and deterministic reference metrics
- animated WebGL agent-flow visualization
- material-variance table and account drilldown
- driver contribution visualization
- evidence and claim references
- evidence-backed analyst chat replay
- prior-close context suggestion and confirmation interaction
- controller review queue and demo approval state
- finance-style executive memo, print action, and JSON export
- PRISM, GIDE, and ElevenLabs status boundaries
- responsive and reduced-motion behavior

## Backend connection boundary

Only the `BackendAdapter` object and state normalization in `static/money-operations.html` should need replacement. `API_ROUTES` lists the current backend routes. Connected mode is now wired through `BackendAdapter`: login, reference fixture ingest, Jan→Feb analysis, parallel contract fetch, and normalizeLiveAnalysis. Synthetic replay remains fully offline.

The UI expects these concepts from the backend:

- analysis ID, revision, calculation digest, periods, and currency
- material variances with raw minor units and display values
- selected drivers, offsets, shares, and reconciliation status
- source and row lineage for every claim
- `context_suggested` and `user_confirmed` context states
- separate numeric reconciliation and causal-support states
- controller review bound to the current analysis and narrative revision
- honest integration states for PRISM, GIDE, and ElevenLabs

## Required route addition during integration

Serve `static/money-operations.html` from `/money-operations` with the same security headers as the other unified pages. Update the content-security-policy path handling if the current middleware applies it only to `/`.

## Honesty boundary

All current values and interactions are a synthetic browser replay. PRISM is shown as awaiting a live trace, GIDE as pending evaluation, and ElevenLabs as optional and disabled. The UI must not change those labels until the backend provides verified status.
