# Money Operations backend QA

5 September 2026. Observed results after builder + evaluator + lead fixes. Independent findings: `docs/MONEY_OPERATIONS_EVALUATION.md`. This file is not a relabel of `docs/SECURITY_UPDATE_QA.md`.

## Lead fixes after evaluation

Evaluator M1–M4 were applied:

- Multipart upload preserves exact file bytes (no `rstrip` of the CSV terminating newline).
- Analysis re-hashes stored files against `mo_sources` and returns 422 `source_modified` on mismatch.
- Deterministic template names offsets and does not phrase a >100% contributor share as standalone growth.
- `_variance_payload` filters suggested context with `_same_account` (no undefined `needle`).
- Adversarial mutation now actually changes stored bytes (the original `,160000,` substring is not in this dataset).

## Commands observed

```text
python3.12 -m pytest tests/test_money_operations_engine.py -q
11 passed in 0.12s

python3.12 -m pytest tests/test_money_operations_api.py -q
16 passed, 1 warning in 7.96s

python3.12 -m pytest tests/test_money_operations_adversarial.py -q
28 passed, 1 warning in 6.56s

python3.12 -m pytest tests/test_money_operations_engine.py tests/test_money_operations_api.py -q
27 passed, 1 warning in 7.73s

python3.12 -m pytest -q
139 passed, 1 failed, 1 warning, 9 subtests passed in 35.92s
FAILED tests/test_integrations.py::test_sdk_public_trace_and_flush
ModuleNotFoundError: prismtrace

python3.12 scripts/run_evaluation.py
{"total": 12, "passed": 12, "unsafe_cases": 9, "baseline_unsafe_admissions": 9,
 "mandate_unsafe_admissions": 0, "legitimate_cases": 3, "mandate_false_holds": 0}
```

Browser tests were not rerun; UI binding is deferred.

## Oracle and integrity (this session)

- Two consecutive `analyze()` calls produced identical `calculation_digest` `6a807a7ced1135a6…`.
- Oracle values above matched `validation_manifest.json` / `expected_driver_answers.json`.
- Other Opex +$57,000: `reconciliation.status == reconciled`, `causal.status == unexplained`.
- Engine shuffle/grouped-total invariants are in `tests/test_money_operations_engine.py` (passed).
- UI hashes unchanged vs `docs/MONEY_OPERATIONS_UI_HASHES.sha256`:
  - `static/security.html` `ae03afb0b864b4052ccf0d0221fe0ed83e13a640aa79e3b561fb557130ca09ad`
  - `static/index.html` `478b6e122783ba6d33af999c56000c448b301d98f43ae281533e6d9dd8395333`

## Secrets

Tracked-file scan: no `BEGIN … PRIVATE KEY`, `sk-…`, `AKIA…`, or `ghp_…`. `.env`, `data/*`, `*.sqlite3*`, `*.sqlite`, `*.db`, and `*credentials*` remain gitignored. Do not copy `data/` into a GIDE workspace.

## Not verified

Live model narrative, live PRISM application trace, GIDE session, Docker/cloud, UI remapping, ElevenLabs.
