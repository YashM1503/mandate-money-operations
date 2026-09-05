# Support

This is a synthetic hackathon demonstration. It is not a production finance
product and does not move funds.

## Try the close

Open `demo.html` in a browser. No server is required.

If an app is already running, use http://127.0.0.1:8000/demo.html. The
same page is at `/money-operations`. A JSON `Not Found` on `/demo.html`
means restart uvicorn from this checkout.

## Docs

- Product story and run path: `README.md`
- Demo beats: `docs/DEMO.md`
- Judging numbers: `docs/JUDGING_METRICS.md`
- Deployment: `docs/DEPLOYMENT.md`
- Security: `SECURITY.md`

## Questions and defects

Use a GitHub issue for product defects on synthetic data. Use the private
security advisory workflow for vulnerabilities. Do not attach credentials or
real ledgers.

## Integrations

`python scripts/check_integrations.py` reports whether ElevenLabs, a phrasing
model, or PRISM keys are set. It never prints the secret.
