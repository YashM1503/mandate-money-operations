# MANDATE Money Operations — start here

The primary hackathon demonstration explains financial changes across periods
from account summaries and transaction-level synthetic data. Open
`/money-operations` in connected mode to show the January-to-February close:
gross revenue increased $675,000 (18.0%), enterprise contributed $576,000
(32.0%), and three customers contributed $432,000 (64.0% of total growth).
Prior-close context requires current-run confirmation, and Other Opex remains
visibly reconciled but causally unexplained pending human review.

The offline visual replay is `static/money-operations.html`. PRISM live traces
for the rejected and corrected narratives were verified in the sponsor
dashboard; see `docs/PRISM_LIVE_EVIDENCE.md`. GIDE usage requires a separate
native evaluation, and ElevenLabs briefing is optional and restricted to an
approved memo. All included financial records are fictional.

## Run the Money Operations demo

Python 3.12 or newer is required.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/bootstrap.py
uvicorn mandate.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

Open <http://127.0.0.1:8000/money-operations>, choose **Connected API**, and use
the locally generated credentials in `data/demo-credentials.txt`. Never commit
the `data/` directory.

Or, after Docker is available:

```sh
docker compose up --build
```

The first container start bootstraps `/data`. Read credentials from the volume,
not from Git. See `docs/DEPLOYMENT.md`.

## Additional reference workflows

### Security analyst demo

The Regodit security questionnaire workflow remains an additional reference demonstration. Open `static/security.html` directly for an offline synthetic replay, or start the API using the commands below and visit `/security` for authenticated server mode. `/` retains the earlier payment MVP.

Try: MFA conflict → Complete backups → yes → daily → yes → Actually backups are weekly → load new synthetic IAM evidence → export questionnaire → decision memo.

The security analyst is a bounded deterministic engine. It does not yet make live model calls or submit security traces to PRISM. The existing AP model/PRISM adapter is retained. Meaningful GIDE usage and verified PRISM ingestion remain required event work; this package does not claim qualification or production readiness.

See `docs/Mandate_UI_Specification.docx`, `docs/Mandate_Business_Explanation.docx`, `docs/SECURITY_UPDATE_QA.md` and `docs/MASTER_BUILD_PROMPTS.md`. Synthetic security records live in `sample-data/security-*.json`. The editable reference story deck is under `demo/`.

---

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

1. docs/JUDGING_METRICS.md — five official buckets, measured numbers, labor estimates.
2. docs/DEMO.md — 45-second product clip and what is on camera.
3. docs/PRISM_LIVE_EVIDENCE.md and docs/GIDE_ATTEMPT_EVIDENCE.md — sponsor results only.
4. docs/DEPLOYMENT.md — local, Docker and cloud prerequisites.
5. docs/MONEY_OPERATIONS_BACKEND.md — engine, claims, Other Opex boundary.
6. docs/QA_REPORT.md — completed checks and unresolved gates.

The four Resolve modules under mandate/core are pinned and attributed in THIRD_PARTY_NOTICES.md. The finance adaptation lives in Mandate's surrounding modules and UI. Disclose pre-event work and Resolve reuse to organizers. Confirm mixed-editor eligibility, team-size contradiction and prebuild rules before claiming qualification.
