# Demo — Money Operations

Two halves. Maximum 90 seconds. Synthetic replay is allowed.

## First 45 seconds — deck

Megan pitch slides. Problem: the close delivers numbers before the explanation.

## Second 45 seconds — product

File: `qa-evidence/money-operations-demo/mandate-money-operations-product-45s.mp4` (45.00 s).
Script: `qa-evidence/money-operations-demo/VOICEOVER-PRODUCT-45s.txt`.

| Time | On screen | Result shown |
|---|---|---|
| 0:00 | Observe | First pass is “Revenue increased 18%.” |
| 0:08 | Improve | Run analysis from the ledger |
| 0:16 | Prove | 18.0% / 32.0% / 64.0% · click a claim |
| 0:24 | Provenance | Revenue trail, then Other Opex cause open |
| 0:32 | Human in the loop | Keep cause open · confirm context · approve memo |
| 0:38 | Memo | Review-ready letter with $57,000 unexplained |

On camera (~70%): cycle, 18 / 32 / 64, provenance, review, memo.
Spoken if asked (~30%): PRISM 25 → 45, ~$270 / close, 196 tests, GIDE rate limit.

After approval, **Listen to briefing** reads the memo. Synthetic replay uses
the browser speech engine. Connected mode uses ElevenLabs when
`MONEY_OPS_AUDIO_ENABLED` and the API key / voice id are set.

## Run locally

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/bootstrap.py
uvicorn mandate.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

Open http://127.0.0.1:8000/money-operations. Use `data/demo-credentials.txt` for Connected API. Never commit `data/`.

```sh
docker compose up --build
```
