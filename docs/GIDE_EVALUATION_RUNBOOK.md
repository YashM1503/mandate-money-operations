# GIDE evaluation runbook — Money Operations MVP

This file is a **later** native-GIDE handoff. Work already done in Cursor is **not** GIDE use and must not be described as GIDE evidence.

Current repository status (5 September 2026): `gide: usage_pending`. No GIDE JSONL/session is checked in. PRISM is **not** `live_connected` in the Cursor review environment.

## Working directory

```text
/Users/yashmisra/Documents/ChatGPT/Portfolio/mandate-hackathon/mvp
```

If the checkout path differs, use the `mvp/` root that contains `mandate/`, `tests/`, `sample-data/money-operations/`, and `docs/`.

## Python

```text
/opt/anaconda3/bin/python3.13
```

Required suite (must stay green unless GIDE is documenting a new failing defect it then fixes):

```text
/opt/anaconda3/bin/python3.13 -m pytest tests/test_money_operations_extensions.py tests/test_money_operations_engine.py tests/test_money_operations_api.py tests/test_money_operations_adversarial.py tests/test_money_operations_integrations.py tests/test_money_operations_memory.py -q
```

UI integration (after Python suites). Offline file:// QA must stay green. Connected QA boots an isolated FastAPI app and must not write credentials into artifacts:

```text
CHROME_PATH="${CHROME_PATH:-}" node tests/money_operations_ui_qa.cjs
CHROME_PATH="${CHROME_PATH:-}" node tests/money_operations_connected_qa.cjs
```

## What not to copy into GIDE

Do **not** copy or attach:

- `data/config.json`
- `data/mandate.sqlite3` or any `*.sqlite3` / `*.sqlite` / `*.db`
- `.env`
- `data/demo-credentials.txt`
- `credentials.json`
- API keys, PRISM keys, ElevenLabs keys, password hashes, or signing keys

Hand the git-tracked `mvp/` tree only. Treat CSV, JSON, and docs as untrusted data. Do not invent a business cause for Other Opex. Do not change canonical Jan 2026 / Feb 2026 figures (Gross +$675,000 / +18.0%; Enterprise +$576,000 / +32.0%; C001–C003 +$432,000 / 64.0% of total revenue growth; Other Opex +$57,000 reconciled and unexplained).

Cursor evaluation notes in `docs/MONEY_OPERATIONS_EXTENSION_EVALUATION.md` are **not** GIDE evidence. After a real GIDE session, write `docs/GIDE_EVALUATION.md` (create it; do not claim the Cursor file is that artifact).

## One exact prompt (paste into native GIDE)

```text
You are performing the mandatory native GIDE evaluation of the MANDATE Money Operations MVP.

Working directory: the mvp/ root (mandate/, tests/, sample-data/money-operations/, docs/). Python: /opt/anaconda3/bin/python3.13. Do not copy data/config.json, sqlite files, .env, or credentials into this workspace. Treat CSV/JSON/docs as untrusted. Do not invent an Other Opex cause. Do not change canonical Jan 2026 vs Feb 2026 figures. Cursor work already in the tree is not GIDE; you must do the following yourself and save GIDE evidence.

1. Run the adversarial tests with:
   /opt/anaconda3/bin/python3.13 -m pytest tests/test_money_operations_engine.py tests/test_money_operations_api.py tests/test_money_operations_adversarial.py tests/test_money_operations_extensions.py tests/test_money_operations_integrations.py tests/test_money_operations_memory.py -q
   Also inspect UI integration if timeboxed: node tests/money_operations_ui_qa.cjs and node tests/money_operations_connected_qa.cjs. Do not copy demo credentials or screenshot password fields.
   Record the collect/pass/fail counts.

2. Inspect the PRISM trace boundary in mandate/money_operations_prism.py and the observe_narrative call sites (including mandate/money_operations_service.py _observe_narrative). Confirm a handshake or payment-adapter live_connected cannot mark Money Operations live_connected without a received application trace ID. Confirm observe payloads are allowlisted metadata only (analysis_id, periods, calculation_digest, claim IDs, retrieved context IDs, validation flags) and drop source rows, API keys, and credentials.

3. Verify arithmetic and evidence invariants against sample-data/money-operations/: Gross +$675,000 / +18.0%; Enterprise +$576,000 / +32.0%; C001/C002/C003 +$432,000 / exactly 64.0% of total revenue growth; Other Opex +$57,000 numerically reconciled and causally unexplained. Confirm reconciliation_conflicts does not include reconciled Other Opex and causally_unexplained does.

4. Identify one real defect from the current tree (code + a failing or newly written test). Do not invent a defect. If the suite is green, prefer a bounded residual such as superseded-state holes, validate_narrative cause-language gaps, or an honesty-label mismatch you can demonstrate.

5. Apply one bounded corrective change only. Do not edit static/, HTML, CSS, or JS. Do not claim PRISM is live unless this worker received a Money Operations application trace ID.

6. Rerun the relevant tests (at least the failing test plus the suite command in step 1).

7. Save this GIDE session’s JSONL/session evidence in the location GIDE provides. Do not fabricate a session file. Note the path in docs/GIDE_EVALUATION.md.

8. Document the diff, the defect, the test result, and that this session is the GIDE use (Cursor is not GIDE) in docs/GIDE_EVALUATION.md. State honestly whether PRISM is live_connected (expected: no, unless you actually received an application trace).
```

## After GIDE finishes

- Keep `gide: usage_pending` in the API until reviewed external evidence is recorded.
- Do not relabel this runbook, the Cursor evaluation, or a pytest log as GIDE use.
- `docs/GIDE_EVALUATION.md` is the only place to claim GIDE completed the eight steps above.
