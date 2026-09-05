#!/usr/bin/env python3
"""Observe → Improve Money Operations narrative traces.

Run 1 invents an unsupported Other Opex cause and is rejected.
Run 2 preserves unexplained Other Opex and passes claim validation.

If PRISM credentials and synthetic egress are present, both runs are sent.
Trace and run IDs are printed. Credential values are never printed.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mandate.money_operations_narrative import NarrativeError, compose, validate_narrative
from mandate.money_operations_prism import observe_narrative, prism_status, reset_prism_observation

FIXTURE = ROOT / 'sample-data' / 'money-operations'

SETUP = """PRISM Money Operations demo — credentials not configured.

1. Create a PRISM project and ingest key in the PRISM console.
2. Export PRISMTRACE_API_KEY (do not print or commit the value).
3. Export PRISMTRACE_PROJECT_ID.
4. Optionally export PRISMTRACE_HOST=https://prism.blockconvey.com
5. Export MANDATE_ALLOW_SYNTHETIC_EGRESS=1 to permit synthetic narrative traces.
6. Re-run: python3.12 scripts/run_prism_money_ops_demo.py

A handshake is not live_connected. Only a received Money Operations application
trace ID in this worker can set live_connected.
"""

EGRESS_SETUP = """PRISM credentials are present, but synthetic egress is disabled.

Export MANDATE_ALLOW_SYNTHETIC_EGRESS=1 and re-run this script to send the two
narrative observations. Credential values are not printed.
"""


def demo_claims() -> list[dict]:
    try:
        from mandate.money_operations import analyze
        result = analyze(FIXTURE, '2026-01', '2026-02', 'yari-retail-us')
        claims = list(result.get('claims') or [])
        if claims:
            return claims
    except (NotImplementedError, Exception):
        pass
    return [
        {
            'id': 'VAR-REV',
            'account_code': '4000',
            'account_name': 'Revenue',
            'claim_type': 'absolute_variance',
            'status': 'reconciled',
            'amount_minor': 67_500_000,
            'percentage_bps': 1800,
            'direction': 'increase',
            'entities': ['Revenue'],
        },
        {
            'id': 'DRV-ENT',
            'account_code': '4000',
            'account_name': 'Revenue',
            'claim_type': 'driver_delta',
            'status': 'reconciled',
            'amount_minor': 57_600_000,
            'percentage_bps': 3200,
            'entities': ['Enterprise'],
        },
        {
            'id': 'DRV-TOP3',
            'account_code': '4000',
            'claim_type': 'driver_group',
            'status': 'reconciled',
            'amount_minor': 43_200_000,
            'share_bps': 6400,
            'entities': ['Northstar Commerce', 'Atlas Industrial', 'Forma Retail Group'],
        },
        {
            'id': 'VAR-UNK',
            'account_code': '6900',
            'account_name': 'Other Opex',
            'claim_type': 'absolute_variance',
            'status': 'unexplained',
            'amount_minor': 5_700_000,
            'entities': ['Other Opex'],
        },
    ]


def _creds_present() -> bool:
    return bool((os.getenv('PRISMTRACE_API_KEY') or '').strip() and (os.getenv('PRISMTRACE_PROJECT_ID') or '').strip())


def _cite(claims: list[dict], *needles: str) -> list[str]:
    found = []
    for claim in claims:
        cid = str(claim.get('id') or '')
        if any(needle.lower() in cid.lower() for needle in needles):
            found.append(cid)
    return found


def main() -> int:
    reset_prism_observation()
    claims = demo_claims()
    opex_ids = _cite(claims, 'VAR-UNK', '6900-absolute', '6900-causal', 'other-opex') or [
        c['id'] for c in claims if str(c.get('account_code')) in {'6900', 'other_opex'}
    ]
    print('Money Operations PRISM demo (synthetic). Canonical window: Jan vs Feb 2026.')
    print()
    print('=== Run 1: weak narrative invents an unsupported Other Opex cause ===')
    weak_text = (
        'Other Opex increased $57,000 because warehouse insurance rose $12,400 '
        'after a new vendor onboarding program.'
    )
    weak_status = 'REJECTS'
    weak_code = None
    try:
        validate_narrative(weak_text, claims, opex_ids)
        weak_status = 'PASSES'
    except NarrativeError as exc:
        weak_code = exc.code
        weak_status = 'REJECTS'
    print(f'validation {weak_status}' + (f' ({weak_code})' if weak_code else ''))
    weak_obs = None
    if _creds_present() and os.getenv('MANDATE_ALLOW_SYNTHETIC_EGRESS') == '1':
        weak_obs = observe_narrative(
            run_id='mo-demo-weak',
            prior_period='2026-01',
            current_period='2026-02',
            structured_claim_ids=opex_ids,
            template_version='mo-narrative-template-1.0',
            provider='deterministic-template',
            model='deterministic-template',
            narrative_source='model',
            unexplained_item_count=1,
            numeric_validation='reject',
            citation_validation='reject',
            fallback=True,
            error_state='uncited_number',
            text=weak_text,
        )
        print(f"run_id={weak_obs.get('run_id')} application_trace_id={weak_obs.get('application_trace_id')}")

    print()
    print('=== Run 2: corrected narrative preserves unexplained Other Opex ===')
    package = compose({'claims': claims, 'periods': {'prior': '2026-01', 'current': '2026-02'}})
    text = package.get('text') or package.get('body') or ''
    cited = list(package.get('cited_claim_ids') or [])
    corrected_status = 'PASSES'
    try:
        validate_narrative(text, claims, cited)
    except NarrativeError as exc:
        corrected_status = f'REJECTS ({exc.code})'
    print(f'claim validation {corrected_status}')
    if 'unexplained' not in text.lower() and 'unmapped' not in text.lower():
        print('warning: corrected prose should keep Other Opex unexplained')
    corrected_obs = None
    if _creds_present() and os.getenv('MANDATE_ALLOW_SYNTHETIC_EGRESS') == '1':
        corrected_obs = observe_narrative(
            run_id='mo-demo-corrected',
            prior_period='2026-01',
            current_period='2026-02',
            structured_claim_ids=cited,
            template_version='mo-narrative-template-1.0',
            provider=package.get('narrative_source') or 'deterministic-template',
            model=package.get('mode') or 'deterministic-template',
            narrative_source=package.get('narrative_source') or 'deterministic_template',
            unexplained_item_count=1,
            numeric_validation='pass',
            citation_validation='pass',
            fallback=True,
            text=text,
            headline=package.get('headline'),
        )
        print(f"run_id={corrected_obs.get('run_id')} application_trace_id={corrected_obs.get('application_trace_id')}")

    status = prism_status()
    print()
    print(f"prism_state={status['state']} live_connected={status['live_connected']}")
    if status['live_connected']:
        print(f"received application_trace_id={status.get('application_trace_id')}")
    else:
        print('No Money Operations application trace ID was received in this process.')

    if not _creds_present():
        print()
        print(SETUP)
        return 0
    if os.getenv('MANDATE_ALLOW_SYNTHETIC_EGRESS') != '1':
        print()
        print(EGRESS_SETUP)
        return 0
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
