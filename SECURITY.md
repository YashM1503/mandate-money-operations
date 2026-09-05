# Security policy

## Scope

MANDATE is a synthetic hackathon demonstration. It does not connect to a bank,
ERP, payment rail, or production financial dataset. Do not use it to authorize
or execute real financial activity.

## Reporting a vulnerability

Report vulnerabilities privately through GitHub's **Security → Report a
vulnerability** workflow for this repository. Do not open a public issue for a
suspected vulnerability and do not include credentials, customer data, or
exploit data in public channels.

Include the affected component, reproduction steps, impact, and a suggested
fix when available. The repository owner will acknowledge a report as soon as
practical during the event and will coordinate remediation before disclosure.

## Secrets and local data

Never commit `.env`, `data/`, `demo-credentials.txt`, SQLite/database files,
API keys, access tokens, password hashes, or GIDE/PRISM credential exports.
Use runtime environment variables for PRISM and ElevenLabs configuration.

The packaged `sample-data/` records are fictional. Any replacement dataset
must be synthetic or properly authorized and must be reviewed for personal,
confidential, and regulated information before use.

## Security boundaries

- Authentication tokens remain in memory and expire server-side.
- Calculation and narrative claims are separated; context cannot change
  calculated values or lineage.
- Controller review is bound to the analysis revision and calculation and
  narrative digests.
- Chat and voice interfaces cannot approve, edit, submit, or distribute.
- PRISM receives allowlisted narrative metadata rather than raw source rows or
  credentials.
- Live sponsor status must be based on actual trace/provider evidence.

## Supported version

Only the current default branch is supported during the hackathon.
