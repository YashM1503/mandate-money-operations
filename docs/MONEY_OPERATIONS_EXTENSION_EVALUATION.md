# Independent evaluation — Money Operations MVP extension

Date: 5 September 2026
Evaluator: Cursor sub-agent (independent reviewer). This Cursor review is **not** GIDE use. GIDE remains `usage_pending`. No rebuild, deploy, push, merge, publish, or live PRISM configuration was performed.

Owner files under `mandate/money_operations/*`, `mandate/money_operations_narrative.py`, `mandate/money_operations_contracts.py`, `mandate/money_operations_prism.py`, `mandate/money_operations_audio.py`, `mandate/api.py`, `mandate/store.py`, builder tests, and `static/*` were not edited except for one bounded confirm-context guard (E1 below).

## Scope and method

Reviewed the wired extension after both builders finished and the lead registered `register_money_operations_extensions` in `mandate/api.py` and forwarded `observe_narrative` kwargs (`analysis_id`, periods, `calculation_digest`, claim IDs, context IDs, validation flags).

Focus: false prior-context amounts, entity/account scope, superseded confirm, stale approval, approval invalidation after narrative recompose, Other Opex cause rejection, unknown claim IDs, prompt-injection storage, PRISM handshake honesty, PRISM timeout/malformed SDK fallback, audio gates, auditor 403s, post-ingest source mutation, offset wording, CSV formula neutralization, secret leakage, NovaERP confirm vs unexplained Other Opex, UI contract endpoints, and read-only chat.

Primary sources: `mandate/money_operations_service.py`, `mandate/money_operations_contracts.py`, `mandate/money_operations_prism.py`, `mandate/money_operations_audio.py`, `mandate/money_operations_narrative.py`, `mandate/api.py`, `sample-data/money-operations/*`.

Method: new tests in `tests/test_money_operations_extensions.py` plus the required builder suites. Command:

```text
/opt/anaconda3/bin/python3.13 -m pytest tests/test_money_operations_extensions.py tests/test_money_operations_engine.py tests/test_money_operations_api.py tests/test_money_operations_adversarial.py tests/test_money_operations_integrations.py -q
```

Result: **97 passed**, 1 Starlette/httpx deprecation warning. No GIDE session. PRISM is **not** `live_connected` in this environment; no real Money Operations application trace was received.

Canonical Jan 2026 vs Feb 2026 figures were not changed: Gross +$675,000 / +18.0%; Enterprise +$576,000 / +32.0%; C001/C002/C003 +$432,000 / exactly 64.0% of total revenue growth; Other Opex +$57,000 numerically reconciled and causally unexplained. Integer minor units.

## Status labels (do not collapse these)

| Label | Meaning in this review |
|---|---|
| **Implemented** | Code path exists in the tree and was exercised against the live engine or service. |
| **Tested-with-mocks** | Behavior was asserted with patched HTTP/SDK/env, not a live sponsor call. |
| **Configured** | Import or env shape exists; no live proof. |
| **Externally verified** | Dashboard, GIDE session, or live application trace inspected. **None.** |
| **Pending** | Not done in this environment. |

| Surface | Status |
|---|---|
| Deterministic engine + integer claims | Implemented |
| Context suggest / confirm / CAS / roles | Implemented |
| UI contracts (overview, graph, account-variances, chat, memo, briefing) | Implemented |
| Other Opex numeric-vs-causal split | Implemented |
| CSV formula neutralization | Implemented |
| PRISM observe allowlist + handshake | Tested-with-mocks |
| PRISM timeout / malformed SDK fallback | Tested-with-mocks |
| ElevenLabs briefing after approval | Tested-with-mocks (integrations suite) |
| `prismtrace` import | Configured |
| Live PRISM Money Operations application trace | Pending — **not** `live_connected` |
| Native GIDE session | Pending — `usage_pending`. This Cursor review is not GIDE. |
| Live model composer | Pending — template fallback only |
| Browser UI remapping | Pending — not in reviewer ownership |

## Acceptance for this reviewer pass

**Extension evaluation tests met.** The required suite is green. One real confirm-context defect was found and given a bounded fix (E1). Residual gaps below are honest and do not fail the current contract tests.

This review does **not** make the product GIDE-complete, PRISM-live, or sponsor-certified.

## Findings

| id | severity | location | evidence | disposition |
|---|---|---|---|---|
| E1 | major | `mandate/money_operations_service.py` `confirm_context` | After a successful confirm, the original `context_suggested` row stayed `status=context_suggested`. A second POST to the same id with the new context revision returned **200** and inserted another `user_confirmed` row. Demonstrated by `test_stale_and_superseded_context_cannot_confirm` before the fix. | Bounded fix applied: reject confirm when the row is superseded or tombstoned (`409 invalid_state`). Documented here. Test now passes. |
| R1 | residual | `validate_narrative` | Invented Other Opex causes are rejected when they introduce an uncited dollar amount (`$12,400`) or an uncited catalog entity (`NovaERP`). There is no dedicated “unsupported cause language” parser. A cause-only sentence that uses only cited numbers and no catalog entity would still pass `validate_narrative`. Compose never invents warehouse-insurance / onboarding causes. | Tested the actual contract. Not treated as a suite blocker. |
| R2 | residual | `_persist_ledger_copy` | Prompt-injection text in `expense_transactions.csv` `description` remains on the stored dataset path and is not copied into `mo_transactions` (no description column). Analyze does not execute the instruction or invent doubling. | Stored-as-data contract holds on the source file. |
| R3 | note | `deterministic_template` | Narrative contains `Recurring subscription ($70,000)` as an **offset** of Enterprise. That is a live-engine figure, not CTX-001’s false “monthly run-rate remains $70,000.” Suggestion `measured_amount_minor` for Software is `8200000`, not `7000000`. | Do not treat the offset $70,000 as the stale context amount. Canonical Jan/Feb figures unchanged. |

No Other Opex business cause was invented. Reconciled Other Opex is not placed in `reconciliation_conflicts`. It remains in `causally_unexplained`.

## Checklist (each item is a real test)

| # | Test | Result | Implementation status |
|---|---|---|---|
| 1 | `test_prior_context_false_amount_is_recalculated_not_trusted` | passed | Implemented |
| 2 | `test_wrong_entity_or_account_context_is_not_an_explanation` | passed | Implemented |
| 3 | `test_stale_and_superseded_context_cannot_confirm` | passed after E1 | Implemented (fix applied) |
| 4 | `test_approval_against_outdated_analysis_revision_is_409` | passed | Implemented |
| 5 | `test_context_confirm_after_approval_invalidates_approval` | passed | Implemented |
| 6 | `test_unsupported_other_opex_cause_is_rejected_by_validate_narrative` | passed | Implemented (via uncited number/entity; see R1) |
| 7 | `test_nonexistent_claim_id_is_rejected_by_validate_narrative` | passed | Implemented |
| 8 | `test_transaction_description_injection_is_stored_not_executed` | passed | Implemented |
| 9 | `test_prism_handshake_without_application_trace_is_never_live_connected` | passed | Tested-with-mocks |
| 10 | `test_prism_timeout_and_malformed_sdk_fall_back_to_deterministic_narrative` | passed | Tested-with-mocks |
| 11 | `test_audio_requested_before_approval_is_approval_required` | passed | Implemented |
| 12 | `test_audio_requested_after_narrative_digest_change_is_rejected` | passed | Implemented |
| 13 | `test_auditor_cannot_confirm_review_or_tombstone` | passed | Implemented |
| 14 | `test_source_file_modification_after_ingestion_fails_closed` | passed | Implemented |
| 15 | `test_offsetting_drivers_are_not_used_as_calculated_truth` | passed | Implemented |
| 16 | `test_csv_formula_injection_is_neutralized_on_export` | passed | Implemented |
| 17 | `test_secrets_do_not_appear_in_traces_exports_or_audio_requests` | passed | Tested-with-mocks for observe; implemented for export/briefing payload |

Also passed in the same file:

- `test_novaerp_is_confirmable_and_other_opex_stays_unexplained`
- `test_overview_keeps_reconciled_other_opex_out_of_conflicts`
- `test_ui_contract_endpoints_exist`
- `test_chat_does_not_mutate_through_ordinary_or_approval_questions`

## Suite counts

| File | Collected | Result |
|---|---|---|
| `tests/test_money_operations_extensions.py` | 21 | passed |
| `tests/test_money_operations_engine.py` | 11 | passed |
| `tests/test_money_operations_api.py` | 16 | passed |
| `tests/test_money_operations_adversarial.py` | 28 | passed |
| `tests/test_money_operations_integrations.py` | 21 | passed |
| **Total** | **97** | **passed** |

## Explicit honesty statements

- **This Cursor review is not GIDE.** No native GIDE session, JSONL, or GIDE diff was produced. See `docs/GIDE_EVALUATION_RUNBOOK.md` for the later paste-in prompt. Status remains `gide: usage_pending`.
- **PRISM is not `live_connected` in this environment.** Handshake, timeout, and SDK paths were mocked. A payment-adapter or setup-doctor `live_connected` is remapped away. No Money Operations application trace ID was received here.
- Observe payloads are allowlisted metadata only. API keys, source rows, and credentials are dropped. That was tested with mocks and by inspecting captured kwargs / export / briefing JSON.
- Chat approve/reject questions do not change `review_status`.

## Bounded corrective change (E1)

File: `mandate/money_operations_service.py`, `confirm_context` only.

Before: superseded `context_suggested` rows could be confirmed again.

After: if the row id is in `_superseded_ids(db)` or `tombstoned`, raise `MoneyOpsError(409, 'invalid_state', ...)`.

Supporting test: `test_stale_and_superseded_context_cannot_confirm`.

## What this evaluation did not do

- Native GIDE
- Live PRISM dashboard ingest
- Live ElevenLabs or live model
- Browser UI walkthrough (out of reviewer file ownership)
- Commit, push, or deploy
- Invent a business cause for Other Opex
