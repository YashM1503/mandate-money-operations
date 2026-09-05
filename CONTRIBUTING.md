# Contributing

This repository is a synthetic Money Operations demonstration. Contributions
should keep that boundary honest.

## Before you start

1. Open `demo.html` and walk Megan’s January-to-February close.
2. Read `SECURITY.md` and the pull-request template.
3. Do not commit `.env`, `data/`, credentials, SQLite files, or API keys.

## Local checks

```sh
python -m pytest -q
python scripts/check_integrations.py
```

Optional live API:

```sh
python scripts/bootstrap.py
uvicorn mandate.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

## What to keep true

- Canonical amounts are integer minor units. Do not calculate in the model,
  chat, or voice layer.
- Cite existing claim IDs. Do not invent an Other Opex cause.
- Context confirmation does not change calculated amounts.
- Controller review is required before a briefing.
- PRISM, GIDE, Prelint, Tavily, and ElevenLabs status must match evidence.
  Do not describe a handshake as a live receipt.

## Pull requests

Use `.github/pull_request_template.md`. Include test evidence and a risk
note for auth, provenance, review binding, or egress changes.

## License

By contributing, you agree that your contribution is licensed under the
Apache License, Version 2.0. See `LICENSE` and `NOTICE`.
