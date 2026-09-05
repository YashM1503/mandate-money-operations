# Money Operations backend (this phase)

5 September 2026. Dedicated variance/evidence backend for the Maximor **Explain the Change** track. This does not replace or relabel the security-questionnaire MVP. The current UI is intentionally unbound.

## What this phase adds

- Deterministic engine in `mandate/money_operations/` (integer minor units, basis points, drivers, reconciliation, claims).
- Persistence, auth-gated API, versioned context memory, deterministic narrative templates, and exports in `mandate/money_operations_service.py` and `mandate/money_operations_narrative.py`.
- Routes under `/api/money-operations/` (see regenerated `docs/openapi.json`).
- Synthetic fixtures in `sample-data/money-operations/` copied from `money-operations/dataset/`.
- Tests: `tests/test_money_operations_engine.py`, `tests/test_money_operations_api.py`, `tests/test_money_operations_adversarial.py`.

## Authoritative oracle

Packaged `expected_driver_answers.json` and `validation_manifest.json` win over generic spec examples.

Jan 2026 → Feb 2026 (Yari Tech Retail, synthetic):

| Item | Result |
|---|---|
| Gross revenue | +$675,000 / +18.0% (1,800 bps) |
| Enterprise | +$576,000 / +32.0% (3,200 bps) |
| C001/C002/C003 | +$432,000 / exactly 64.0% of the revenue change |
| Other Opex | +$57,000 numerically reconciled; business cause unexplained |

The specification’s example (+$540,000, professional-services $18,000 conflict) is **not** this dataset.

## Honesty

- Engine is authoritative. A model may only phrase validated claims.
- Context from `business_context_history.json` is suggested on a new run and requires current-run confirmation.
- PRISM: never `live_connected` from a handshake. This pass did not run a live trace.
- GIDE: `usage_pending`.
- ElevenLabs: not part of this build.
- Data is synthetic. Not production-certified.
