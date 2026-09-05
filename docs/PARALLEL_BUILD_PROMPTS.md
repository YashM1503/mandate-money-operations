# Parallel build prompts: one contract, four workstreams

Use these prompts with ChatGPT, Claude, Cursor, or GIDE. They assign ownership and completion criteria rather than assume a particular assistant can run tools. Provide the actual repo files, current spec and API definition to each assistant. If working in a chat without filesystem access, ask for a unified diff and tests; a human applies and verifies it. Never send credentials, private customer data, or unrelated project files. Use separate branches/checkouts when assistants do not share a controlled filesystem.

This is a four-hour integration plan for the provided scaffold. It does not promise that a new team can rebuild every verified component from zero in four hours. Confirm prebuilt-code/reuse rules before the event and disclose upstream attribution.

## Shared master prompt — prepend to every assignment

```text
You are implementing a bounded part of MANDATE, a synthetic financial Trust & Risk demo.
Read README.md, the implementation spec, current API models/routes, this assignment,
and relevant tests before editing. The repository is authoritative for symbols and schemas.
The persona is Yari, an owner of a synthetic retailer, with a finance team. Do not claim
proven staffing reduction, fraud prevention, regulatory certification or real-bank execution.
The differentiator is detecting when an agent's own derived vendor-master update is used
as evidence to authorize its payment: source independence, exact action authority,
revocation, one-use execution and post-execution verification.

The LLM is advisory. Only deterministic server controls and authenticated human actions
can authorize the simulated ledger effect. Unknown evidence cannot increase autonomy.
Keep provenance, lineage, fingerprints, roles, expiry and transaction boundaries intact.
Keep upstream Resolve notices and pinned-source attribution; adapt user-facing language
to Mandate. Do not invent unavailable ADMIT metrics. Record unmapped sources as gaps.
PRISM and GIDE are mandatory but success must be backed by actual use. Never relabel
mock tests, deterministic replay, an environment flag or a badge as sponsor verification.

Work only within the files assigned below. Do not edit another owner's files or change
shared API/data contracts unilaterally. Propose a contract change to the integrator first.
Do not commit secrets or runtime databases. Do not publish, call real payment rails,
use private financial data, add blanket authorization bypasses or remove failing tests.
Implement useful behavior, test failure paths, and report exact commands/results,
modified files, any contract delta, remaining blockers and assumptions. If you cannot run
checks, label them unrun. Your final handoff must fit the integration checklist below.
```

## Freeze contract before parallel edits: first 15 minutes

The integrator publishes the actual backend OpenAPI schema and one sanitized case, decision, error, ledger and audit response. Attach them to all workstreams. The supplied `mandate/integrations.py` exposes the stable Python contract:

```python
investigate(case: dict, decision: dict) -> dict
# mode, summary, steps, cited_evidence_ids, trace_id, prism_status; optional error
integration_status() -> dict
# model, prism, gide, synthetic_egress_enabled, status_scope
verify_prism() -> dict
# operator diagnostic only
```

No endpoint names are invented here. Use the actual routes in the repository and generated OpenAPI document. A shared contract change requires a reviewed schema/example update, then each affected owner acknowledges it. The integration owner alone edits dependency manifests, launch configuration and shared schemas.

## Workstream A — control and data integrity (Claude or ChatGPT)

```text
Assignment: inspect and improve the deterministic control engine, approval validation,
lineage and simulated ledger consistency. The integrator assigns the exact engine,
store and engine-test paths from this repo before you begin. You own those paths only.
Do not edit UI, integrations.py, integration tests or deployment files.

Verify: independent roots deduplicate copied evidence; missing ancestry and cycles do not
pass; invoice validity cannot authorize changed bank details; case/candidate/evidence/
state changes invalidate an existing grant; verifier and approver separation is enforced;
expiry and revocation fail closed; duplicate requests cannot produce duplicate effects;
concurrent different idempotency keys cannot consume the same authority twice; rollback
leaves no half-written approval/ledger/audit state. Inspect before adding duplicate tests.
Preserve any independently anchored journal limitation in the docs rather than inventing
immutability. Currency values use integer minor units. No real funds move.

Return a reviewed diff, meaningful test results and a short invariants table connecting
trigger → expected refusal/effect → test. If a production control is not implemented,
state it as a deployment limitation, not a completed feature. Budget: 90 minutes coding,
20 minutes testing, 10 minutes handoff. Leave API routes and shared schema unchanged.
```

## Workstream B — premium finance UI (Cursor)

```text
Assignment: wire and polish only static/ HTML, CSS and browser JavaScript plus UI-specific
tests/screenshots paths explicitly approved by the integrator. Read the actual OpenAPI
contract and sample responses; do not invent endpoints, fields, sessions or permissions.
Maintain the premium forest/ivory finance interface and accessible keyboard navigation.

Show the owner a clear exception queue: invoice, amount, proposed destination suffix,
control outcome, source-lineage reason, current authority and precise next action.
Northstar Packaging $8,240 is the routine fixture; Atlas $47,850 is the changed-destination
exception. Use actual seeded values. Distinguish independent human verification from
approval, and approval from simulated execution. Explain why 3 copies count as 1 origin.
Every button must call the real API, disable while pending, show bounded readable errors
and refresh from server state. Never store authority in localStorage, trust a browser gate,
or insert model/evidence text with innerHTML. Make loading, empty, denied, expired,
stale, revoked, integration error and replay states visible. Show no fake metrics.

QA at desktop and narrow widths; test keyboard/focus, long text, malicious HTML text,
failed requests and repeated actions. Preserve clean screenshots and a reproducible
smoke checklist. Report cosmetic vs behavior changes, exact verified workflows and any
browser checks you could not run. Budget: 100 minutes build, 20 minutes browser QA.
```

## Workstream C — PRISM and GIDE (GIDE for at least one real change)

```text
Assignment: own mandate/integrations.py, tests/test_integrations.py and sponsor setup
notes only. Use the real GIDE product for a useful development task and record its
contribution with a redacted screenshot/session reference, actual diff and test outcome.
Do not claim usage from being assigned this prompt. If access is absent, report it.

Preserve investigate(case, decision) as an advisory-only interface. Explicit synthetic
egress opt-in plus complete provider config are required for network calls. Validate
model JSON and citations. Never mutate a decision or create authority. Send only
allowlisted context; never forward raw invoices, names, accounts or human notes.

Verify PRISM's current official HTTP docs. Trace actual model exchanges with stable
opaque session, agent mandate-investigator and unique trace ID. Use X-PRISMtrace-Key.
Distinguish replay / configured-unverified / accepted / error. Test provider timeout,
HTTP failure, malformed JSON, unknown references, attempted permission fields, redirects,
trace ingest failure, redaction and no-network default. Do not silently bypass HTTPS.
If credentials are available, run a real synthetic case and correlate exact trace in
PRISM. Record accepted ingest separately from later scoring. Otherwise return the
mock-tested adapter and the precise live-validation blocker. Budget: 90 minutes adapter
and tests, 30 minutes authentic sponsor evidence. Never place secrets in the handoff.
```

## Workstream D — integration, hosting and demonstration (human lead + ChatGPT)

```text
Assignment: you are the integrator. Own launch/dependency/container/CI/configuration
files, top-level documentation and the demo script; resolve shared contract changes.
Read all owner handoffs, run the whole suite and inspect the actual UI/API together.
Keep a local launch route and scope a cloud deployment from the same package. Use
synthetic data and simulated payments only. Do not select an ephemeral filesystem
for durable SQLite state or claim multiple replicas are supported without verification.

Inventory Python version, dependencies, secrets, identity/session configuration,
persistent storage, HTTPS/proxy headers, health checks, restart behavior and restore
procedure. Validate the container if Docker is available. Mark unavailable checks unrun.
Do not loosen authentication to make hosting easy. Freeze features by minute 180.

Build a 3-minute demo: routine case → agent-derived self-confirmation blocked → lineage
explanation → independent verification under a different identity → owner approval →
one simulated effect → audit/ledger verification. Add one stale-approval or retry attack.
Show integration statuses honestly, correlate a real PRISM trace if available, and
record the GIDE development evidence. Keep a local fallback and reset instructions.

Release only with a completed test report, known limitations, source attribution,
setup instructions and no unresolved critical control failures. Report actual deployment
as unrun if no target is chosen. Budget: first 15 minutes freeze; integrate continuously;
minutes 180–225 regression and deployment smoke; 225–240 demo rehearsal and submission.
```

## Handoff form — every owner returns this

```text
Owner and branch/commit:
Assigned files changed:
Behavior implemented:
Shared contract changed? (no, or approved change reference):
Commands executed and pass/fail counts:
Observed failure scenarios:
Checks not executed:
Remaining blocker and minimum fix:
New dependencies and licenses:
Secrets/data exposure check:
Screenshots/logs/evidence paths (redacted):
```

## Critical path and stop rules

| Minutes | Parallel activity | Integrator decision |
|---|---|---|
| 0–15 | Read scaffold, clarify organizer tools and prebuilt rules | Freeze schemas, fixtures and owner paths |
| 15–105 | Engine, UI and integrations work independently | Review diffs continuously; resolve only necessary schema changes |
| 105–135 | Connect real API; run focused tests; GIDE evidence | Get one complete case through all server controls |
| 135–180 | Failure cases, sponsor live evidence, local/cloud smoke | Stop adding features; preserve working local route |
| 180–225 | End-to-end regression, redacted screenshots, runbook | Critical control failure blocks a release claim |
| 225–240 | Demo rehearsal, repo/demo submission package | Record live-tool and hosting gaps honestly |

If a tool owner is blocked on credentials, they finish mocked tests and setup evidence requirements while the other workstreams continue. If cloud is not ready by minute 180, use the tested local API and demo recording. If a mandatory sponsor cannot be used, disclose that gap and ask organizers for access/eligibility guidance; hosting success cannot cure it. Optional sponsor integrations and extra LLM agents are cut before source integrity, authorization, traceability or the main demo path.

## Frozen approval request update

POST /api/cases/{id}/approve requires version AND decision_fingerprint from the displayed decision.fingerprints.decision_fingerprint. Never approve a newly recomputed cash context without confirming it matches the screen. PRISM defaults to the pinned SDK; submitted_unverified is not live proof. Full exact API is docs/openapi.json. The unified server UI is static/index.html; parent-folder mandate.html is a historical browser-only prototype.
