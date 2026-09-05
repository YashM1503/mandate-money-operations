# Mandate

Mandate checks whether the evidence authorizing a supplier payment is independent, then binds human authority to an exact simulated effect. The demo catches an agent updating a supplier master from an unverified message and later treating its own update as confirmation.

**Scope:** authenticated local API and premium unified HTML, fictional retailer data, no real money. Local tests and browser workflow passed. Live model/PRISM proof, actual GIDE development use, container build and cloud release are pending external gates. See docs/QA_REPORT.md; this is not a production banking certification.

## Start locally

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/bootstrap.py
uvicorn mandate.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

Open http://127.0.0.1:8000. Read the generated `data/demo-credentials.txt` privately. Sign in as analyst to investigate/verify, controller to approve/release, or auditor to inspect. Passwords are random and are not included in this repository. Do not share or commit the data directory.

## Verify

```sh
python -m pytest -q
python scripts/run_evaluation.py
pip-audit -r requirements.lock
```

The deterministic evaluation has 12 authored cases; it does not measure real-world fraud prevention. Use `MANDATE_DATA_DIR` pointing at a new directory and run bootstrap there to create fresh demo state. Each dataset includes $90,000 cash, $30,000 commitments and a $10,000 reserve. Cash and exception attestations expire after 24 hours intentionally.

## Read in this order

1. docs/QUALIFICATION_AND_DEMO.md — differentiation, new Discord requirements, demo sequence and four-hour scope.
2. docs/TECHNICAL_SPEC.md and docs/openapi.json — architecture, exact API, data, security and acceptance.
3. docs/SPONSOR_SETUP.md — mandatory SDK, real PRISM proof and substantive GIDE use.
4. docs/PARALLEL_BUILD_PROMPTS.md — separate ChatGPT, Claude, Cursor and GIDE work segments.
5. docs/DEPLOYMENT.md — local, Docker and cloud prerequisites.
6. docs/INDUSTRY_AND_PERSONA_REVIEW.md — persona gaps, JPMorgan/Mastercard/Visa sources and applicability.
7. docs/QA_REPORT.md — completed checks, artifacts and unresolved gates.

The four Resolve modules under mandate/core are pinned and attributed in THIRD_PARTY_NOTICES.md. The finance adaptation lives in Mandate's surrounding modules and UI. Disclose pre-event work and Resolve reuse to organizers. Confirm mixed-editor eligibility, team-size contradiction and prebuild rules before claiming qualification.
