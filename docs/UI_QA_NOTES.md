# Frontend verification

The unified frontend is `static/index.html`. It uses the same-origin API and has no external fonts, scripts, or runtime dependencies. The prototype in the parent folder is a separate local simulation; this frontend uses server decisions.

## Verified during construction

- JavaScript syntax checked with Node.
- Headless Chrome interaction test with synthetic HTTP responses: sign-in, payment selection, investigation, exact-destination verification payload, trusted contact identifier binding, disabled controller approval for analyst, evidence-node selection, metrics navigation.
- Desktop 1440 × 1100 and mobile 390 × 844 screenshots inspected. No document-level horizontal overflow; evidence nodes scroll within their own panel. No browser JavaScript errors in the tested path.
- UI reconciled against the implemented API: `WAITING_HUMAN`, `MORE_EVIDENCE_REQUIRED`, `BLOCKED`; release requires a server-valid approval; role constraints; revoked/invalid approvals; compensation state; server logout.
- All dynamic strings inserted into HTML are escaped. Session bearer tokens stay in JavaScript memory and are cleared on sign-out. Password field clears after sign-in. Case export downloads JSON through an authenticated fetch.
- Modal actions capture the current intent version. Release retries reuse an idempotency key for that case and version. Buttons lock during outstanding actions. The server remains authoritative for expiry, changed state, role, approval, and cash checks.

## Scope of this evidence

The browser interaction test used intercepted synthetic API responses. It verifies frontend behavior and request shape, not backend security or live sponsor connectivity. Backend integration tests and final browser smoke testing against the running API must be recorded separately. Browser screenshots are development QA evidence, not live-payment evidence.

## Final live-API smoke checklist

1. Sign in as analyst. Atlas shows a hold; its bank evidence traces back to the change request. Inspect the complete SHA-256 and parent references.
2. Investigate Atlas. Confirm replay or live model mode is accurately labeled. Add a synthetic independent attestation through the established contact.
3. Sign out and sign in as controller. Approve the current intent, then release. Confirm exactly one synthetic ledger entry and a reduced available balance.
4. Refresh and inspect activity and export. Confirm the effect verification event and provenance records.
5. Sign in as analyst and mutate a different case's destination; old authority cannot release it. Sign in as auditor and confirm all mutation buttons are disabled.
6. Confirm expired/revoked approvals are rejected at the server even when a browser remains open. Confirm network failure gives an actionable error and does not falsely present an unverified release.
7. Confirm PRISM/GIDE status reflects the actual deployment configuration and recorded usage. Never describe pending integrations as complete.

The interface intentionally calls a payment a hold rather than fraud. Source-root counts are explanatory metadata, not a fraud probability or confidence score. Financial values are synthetic cash-snapshot values, not a forecast or regulatory assessment.

## Actual API result and reproducible script

Final local API walkthrough passed on 5 September 2026, including separate analyst/controller sessions and approval binding to the displayed decision fingerprint. The portable equivalent is tests/browser_smoke.cjs. It requires a fresh bootstrapped data directory, the service running on port 8000, and Playwright 1.62.1. Install the optional Node development dependency and its Chromium browser, then run npm run test:browser. Alternatively set CHROME_PATH to an authorized installed Chrome executable. This script consumes Atlas once; use another fresh dataset before rerunning. It reads generated credentials privately and never prints them. Desktop/mobile screenshots go to ignored artifacts/.

The small final UI correction labels an already consumed grant correctly and restricts sponsor status display to model, PRISM and GIDE. The browser remains a view of server authority.
