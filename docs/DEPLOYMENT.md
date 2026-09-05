# Local and cloud deployment

Judges who only need the synthetic close should open `demo.html`. That path
does not use localhost.

## Tested local path

Python 3.12 or newer is required. From the repository root:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python scripts/bootstrap.py
python -m pytest -q
uvicorn mandate.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

Open http://127.0.0.1:8000. Read `data/demo-credentials.txt` privately for the analyst, controller and auditor passwords. Credentials are generated, never hardcoded. Bootstrap refuses to overwrite existing configuration. The database is seeded on first startup with fresh dates. Secrets, sessions and SQLite data must not enter Git or the package archive.

Use a new `MANDATE_DATA_DIR` to start a fresh demo; never reset a database while the service is running. The test suite uses isolated temporary databases. Cash snapshots older than 24 hours and changed-beneficiary attestations older than 24 hours stop authorization intentionally. This MVP has no cash-import endpoint; a fresh synthetic dataset is the demo reset procedure.

## Container path

The image copies `mandate/`, `static/`, `scripts/`, and `sample-data/` (required for the connected Money Operations reference package). First start runs `scripts/bootstrap.py` when `/data/config.json` is missing and `MANDATE_SIGNING_KEY` is unset. Credentials stay on the persistent volume.

```sh
docker compose up --build
curl -fsS http://127.0.0.1:8000/healthz
curl -fsS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/money-operations
docker compose exec mandate cat /data/demo-credentials.txt
```

Retrieve credentials only through an authorized container shell. Never paste them into a public README, screenshot or CI log. Check health, login, held Atlas, independent verification, separate approval, release, restart persistence and idempotent retry. The service runs as UID 10001 with a read-only root filesystem, writable data volume, no Linux capabilities and one worker.

CI builds the image and runs `scripts/smoke_image.sh` (health, `/money-operations`, packaged fixtures, bootstrap config). Do not describe a *hosted* cloud URL as verified until a named platform deploy passes the checklist below.

## Cloud API and web service

Use a platform supporting a Docker web service and a persistent disk. Mount `/data` writable by UID 10001. Set `PORT` to the platform port. `127.0.0.1` and `localhost` are always allowed for health checks. Also set `MANDATE_ALLOWED_HOSTS` to the public hostname, or rely on `RENDER_EXTERNAL_HOSTNAME`, `RAILWAY_PUBLIC_DOMAIN`, `WEBSITE_HOSTNAME`, or `FLY_APP_NAME` when the platform injects them. Use `*` only for a private demo. Use HTTPS ingress and platform access restrictions. Keep one instance and one worker. Do not use a sleeping ephemeral function or horizontally scaled replicas with local SQLite.

Provision secrets with the platform secret manager. Either persist bootstrap's configuration securely on the volume or supply `MANDATE_SIGNING_KEY` and `MANDATE_USERS_JSON`; the latter is the salted PBKDF2 user map from generated config, not plaintext passwords. No default credentials exist. Set the model and PRISM variables only when ready to allow synthetic outbound metadata. Start command is `scripts/entrypoint.sh`.

A cloud provider, account, region and URL have not been selected; no hosted deployment was performed. Cloud release remains conditional on a real image build, vulnerability scan, runtime health check, persistent-volume restart test, HTTPS and authentication tests, outbound provider/PRISM tests and private access review. Record the release commit and results in QA_REPORT.md.

## Before any real financial data or payment rail

Replace demo identities with individual SSO/MFA and managed roles; implement organization isolation and access reviews. Use a transactional managed database for concurrency requirements and a separate protected audit-anchor destination. Define retention, deletion, encryption, incident response, provider data processing and jurisdiction with the customer. Replace fictional vendor-contact attestations with independently evidenced enterprise workflows. Add ERP/API connectors, real account validation where applicable, payment-provider idempotency, asynchronous settlement reconciliation and failure recovery. An actual bank transfer is not generally reversible like this simulated ledger.

Public deployment of this hackathon service is not approval for real funds or sensitive customer data. These are scoped system gaps, not assertions that a particular regulation applies to every retailer.

## Failure handling

401: sign in again. 403: use the assigned role. 409: refresh and review the current decision; integrity failures require operator investigation. 422: correct the validated input. 429: wait one minute before retrying login. Provider failure: local deterministic assessment stays authoritative and the UI labels replay or an integration error. PRISM failure: retain actual trace ID and diagnostics; no payment authority is granted by PRISM status. Backend unexpected errors must not be reported as successful release.

Back up the SQLite database using SQLite's online backup facility or after stopping the service, together with protected configuration. Restore to a separate environment and verify all journals and ledger reconciliation. Losing the signing key makes historical verification impossible. Copying both the data and its same-database anchors cannot prove absence of whole-database rollback; keep exported anchors independently if that matters.
