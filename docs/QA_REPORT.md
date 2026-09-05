# QA and release evidence

Verified 5 September 2026 on macOS with Python 3.12.14. This report is a bounded engineering assessment of a synthetic local MVP, not an independent penetration test, financial certification or claim that a cloud deployment has already passed.

## Completed checks

- 63 automated tests passed, plus 9 unittest subtests. JUnit evidence: qa-evidence/tests.xml. Tests cover persona values, held dependent evidence, separate roles, login/logout/throttling, exact effects, retry idempotency, concurrent same-key execution, conflicting keys, one-time compensation, stale approval context, expiration, revocation, destination mutation, cash constraints, stale cash, missing/cyclic ancestry, duplicate evidence IDs, content tampering, deleted event tails/anchors, persisted-ledger changes/deletion, cash tampering, idempotency receipt redirection and restart persistence.
- PRISM/model adapter tests use intercepted HTTP clients and SDK mocks. They cover explicit egress opt-in, safe context, schema validation, invented citations, provider failures, trace receipt validation and SDK submission status. These tests do not establish live provider compatibility or sponsor account connectivity.
- The constructed deterministic evaluation passed 12/12 expected outcomes: 0/9 unsafe admissions and 0/3 false holds. The deliberately weak comparison baseline admitted 9/9 unsafe cases. Evidence: qa-evidence/control-evaluation.json. This is an authored adversarial fixture set, not a production dataset or actual model before/after experiment.
- pip-audit against requirements.lock reported no known vulnerabilities. Evidence: qa-evidence/dependency-audit.json. This is a time-bounded advisory database check, not proof that dependencies are vulnerability-free.
- Real headless Chrome against the local running API passed login, held Atlas inspection, replay investigation, trusted-contact attestation, separate controller login, fingerprint-bound approval, exact ledger release, activity, metrics, desktop/mobile display and absence of document-level mobile overflow or JavaScript errors in that path. Both finance flows also pass backend tests. Original frontend-only intercepted-response tests are documented in UI_QA_NOTES.md.
- A separate static control review identified three issues which were fixed and regression-tested: stale displayed cash context at approval; missing persisted-ledger/cash integrity coverage; and missing journal anchors passing validation. An additional idempotency receipt-to-ledger reconciliation check was added and tested.
- UI inspection found an inaccurate “renew approval” label after successful use; it now says consumed for this release. The backend still treats the grant as used and prevents a second effect.

## Release disposition

Local/private synthetic demonstration: verified for the paths above. Live advisory model: adapter implemented, mocked tests passed, actual endpoint not configured. PRISM: SDK installed and wired, mocked tests passed, real ingest/dashboard proof pending. GIDE: substantive use not performed in this environment, evidence pending. Container: Dockerfile/Compose/CI prepared, local Docker engine unavailable, build not executed. Cloud: host undecided, no deployment or host-specific validation performed. Real funds or sensitive financial records: outside release scope.

Therefore the complete sponsor-qualified or cloud-production MVP cannot yet be marked unconditionally approved for deployment. The remaining gates are explicit in DEPLOYMENT.md and SPONSOR_SETUP.md. Do not change them to “passed” because an environment variable is present or a logo is displayed.

## Known boundaries

Single organization, three demo-role accounts, one worker and SQLite on one persistent volume. The ledger has local transactional semantics, not distributed settlement guarantees. Source independence is enforced against the demo registry and route permissions; it is not external bank account ownership validation. Cash uses a dated aggregate seven-day commitment snapshot. Audit anchors share the database; external trusted retention is required to detect whole-database rollback. Raw-invoice OCR, raw-document prompt-injection handling, sanctions/AML/KYC, SSO/MFA, enterprise key rotation, customer retention policy and real payment connectors are not implemented.

ADMIT coverage is unassessed without the actual ADMIT source definitions. Resolve's imported gate, receipt, fingerprint, approval and journal features are adapted and traceable through TECHNICAL_SPEC.md and THIRD_PARTY_NOTICES.md.

## Reproduce and extend

Run the README commands in a clean environment. Run the container build and selected-host smoke checks before cloud release. For a real model run, configure the provider and PRISM only through environment secrets, use synthetic egress opt-in, inspect actual trace IDs and dashboard results, and preserve a bad-run/fix/rerun comparison. Use GIDE for a substantive tested change and retain its session evidence. Record the release commit and external results without overwriting this initial evidence.
