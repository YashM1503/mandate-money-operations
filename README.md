# Mandate — Megan’s financial change analyst

Megan runs a $47 million tech retailer with a five-person finance team. Every
close delivers the numbers before it delivers the explanation. The team can
see that revenue moved. Proving the drivers still takes hours.

Mandate is the change analyst for that close. It compares two periods, ranks
the material moves, drills to transaction rows, and writes a controller-ready
memo. Megan keeps the last click.

## The February close

January → February 2026, synthetic pack:

- Revenue increased **$675,000**, or **18.0%**
- Enterprise accounts increased **32.0%**
- Three customers accounted for **64.0%** of the increase
- Other Opex increased **$57,000**. The amount ties. The cause stays open.

That is the move from “Revenue increased 18%” to the sentence judges asked
for — with one residual left honest.

## What it does

1. **Observe** — first pass can be thin: revenue increased 18%.
2. **Improve** — rerun from the ledger. Rank, attribute, reconcile.
3. **Prove** — click a claim. Source file, row, and calculation digest stay
   attached.
4. **Human in the loop** — confirm prior-close context for this run. Approve
   the memo. Do not invent a cause for Other Opex.

The engine owns the math (integer cents). Chat and voice only phrase cited
claims. They cannot approve, edit, or release.

## Run Megan’s close

**No server.** Open `demo.html` in a browser (double-click it, or
File → Open). That file is the synthetic February close. Click through
Overview, the explorer, Ask Mandate, review, and the memo. Approve, then
**Listen to briefing** for the local readout.

The same page also lives at `static/money-operations.html`. Both work over
`file://`. Nothing calls localhost unless you choose **Connected API** on a
running app.

Optional live API (only if you want credentials and packaged CSV ingest):

```sh
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/bootstrap.py
uvicorn mandate.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

Then open http://127.0.0.1:8000/demo.html or `/money-operations`. Use
`data/demo-credentials.txt` for Connected API.

```sh
docker compose up --build
```

## Chat and voice briefing

Ask Mandate answers from validated claims. After Megan (controller) approves
the memo, **Listen to briefing** reads that approved text.

| Need | Where | Notes |
|---|---|---|
| Local `.env` | copy `.env.example` → `.env` | Never commit `.env` |
| Voice | `MONEY_OPS_AUDIO_ENABLED=true` plus `ELEVENLABS_API_KEY` and `ELEVENLABS_VOICE_ID` | Speaks approved memo only |
| Chat phrasing | `MANDATE_ALLOW_SYNTHETIC_EGRESS=1` plus `MANDATE_MODEL_URL`, `MANDATE_MODEL_KEY`, `MANDATE_MODEL_NAME` | Draft is re-validated; failure falls back to the template |
| Check wiring | `python scripts/check_integrations.py` | Prints set/missing, never the secret |

Without keys, synthetic replay still reads the memo locally after approval.
Connected mode without ElevenLabs returns the approved transcript and
`audio_unavailable`.

## How the build is structured

- **Deterministic engine** — 392 rows, 8 accounts, 107 claims, digest
  `6a807a7ced1135a6`. p50 analyze is about 5 ms.
- **Narrative boundary** — 18 / 32 / 64 is cited. Other Opex cannot be
  explained from the account name.
- **Context memory** — NovaERP is suggested until this close confirms it.
  Confirmation does not change amounts.
- **Review** — approval is bound to analysis revision, calculation digest,
  and narrative digest.
- **PRISM** — observed the weak 18% story (quality 25) and the corrected
  story (quality 45). Runtime stays `live_trace_pending` without an SDK
  receipt. See `docs/PRISM_LIVE_EVIDENCE.md`.
- **GIDE** — native app received the evaluation prompt and was rate-limited.
  See `docs/GIDE_ATTEMPT_EVIDENCE.md`.

Judging numbers and so-what: `docs/JUDGING_METRICS.md`. Demo beats:
`docs/DEMO.md`.

## Additional features

These are in the same service. They are not Megan’s close.

- **Ask Mandate** — claim-backed Q&A on the same analysis.
- **Voice briefing** — ElevenLabs readout of an approved memo.
- **Assurance** — lineage, integration status, no handshake-as-live-proof.
- **Security questionnaire** — `/security`, a separate evidence-first intake.
- **Supplier payment MVP** — `/`, independent-evidence gates on a synthetic
  ledger. Not a bank rail.

## Verify

```sh
python -m pytest -q
python scripts/check_integrations.py
```
