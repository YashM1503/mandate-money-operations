"""Memory, ingest ledger, review binding, and escalation tests for Money Operations."""
from __future__ import annotations

import json

from test_money_operations_api import _analyze, _h, _ingest, engine
from test_mvp import setup

OTHER_OPEX_CODES = {'6900', 'other_opex', 'Other Opex'}


def _novaerp(entries, analysis_id=None):
    items = [
        e for e in entries
        if e.get('account_code') in ('6200', 'software_expense', 'Software')
        or 'software' in str(e.get('account_code') or '').lower()
    ]
    items = [e for e in items if 'novaerp' in e.get('statement', '').lower() or 'erp' in e.get('statement', '').lower()] or items
    if analysis_id is not None:
        items = [e for e in items if e.get('analysis_id') == analysis_id]
    return items


def test_ingest_populates_summary_rows_and_transactions(setup, engine):
    client, store, _headers = setup
    ds = _ingest(setup)
    with store.connect() as db:
        summaries = db.execute(
            'SELECT period, account_code, amount_minor, source_file, source_row FROM mo_summary_rows WHERE dataset_id=?',
            (ds['dataset_id'],),
        ).fetchall()
        txns = db.execute(
            'SELECT transaction_id, period, account_code, amount_minor, source_file, source_row_number, customer_id, product_id '
            'FROM mo_transactions WHERE dataset_id=?',
            (ds['dataset_id'],),
        ).fetchall()
    assert len(summaries) == 48
    assert len(txns) == 392
    feb_opex = [row for row in summaries if row['period'] == '2026-02' and row['account_code'] == '6900']
    assert len(feb_opex) == 1
    assert feb_opex[0]['amount_minor'] == 20_700_000
    assert feb_opex[0]['source_file'] == 'monthly_account_summaries.csv'
    assert feb_opex[0]['source_row'] >= 2
    jan_opex = [row for row in summaries if row['period'] == '2026-01' and row['account_code'] == '6900']
    assert jan_opex[0]['amount_minor'] == 15_000_000
    sales = [row for row in txns if row['account_code'] == '4000']
    refunds = [row for row in txns if row['account_code'] == '4100']
    assert sales
    assert refunds
    assert all(row['source_file'] in ('revenue_transactions.csv', 'expense_transactions.csv') for row in txns)
    nova = [row for row in txns if row['transaction_id'] == 'EXP-202602-SOFT-03']
    assert nova
    assert nova[0]['account_code'] == '6200'
    assert nova[0]['amount_minor'] == 15_200_000
    assert nova[0]['source_row_number'] >= 2


def test_novaerp_suggested_then_confirm_keeps_calculation_digest(setup, engine):
    client = setup[0]
    analysis = _analyze(setup, _ingest(setup)['dataset_id'])
    ctx = client.get('/api/money-operations/context', headers=_h(setup, 'analyst')).json()
    prior = [
        e for e in ctx['entries']
        if e.get('id') == 'CTX-001' or e.get('context_id') == 'CTX-001'
    ]
    assert prior, 'CTX-001 must be retrieved as prior-close context'
    suggested = [e for e in _novaerp(ctx['entries'], analysis['analysis_id']) if e['status'] == 'context_suggested']
    assert suggested
    item = suggested[0]
    assert item['status'] == 'context_suggested'
    assert item.get('source_context_id') == 'CTX-001' or 'source:CTX-001' in (item.get('supporting_claim_ids') or [])
    if item.get('measured_amount_minor') is not None:
        assert item['measured_amount_minor'] != 7_000_000
        assert item['measured_amount_minor'] == 8_200_000
    confirm = client.post(
        f"/api/money-operations/context/{item['id']}/confirm",
        json={'expected_revision': ctx['revision']},
        headers=_h(setup, 'controller'),
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()['context']['status'] == 'user_confirmed'
    assert confirm.json()['calculation_digest'] == analysis['calculation_digest']
    after = client.get(f"/api/money-operations/analyses/{analysis['analysis_id']}", headers=_h(setup, 'analyst')).json()
    assert after['calculation_digest'] == analysis['calculation_digest']
    assert after['review_status'] != 'approved'
    unexplained = after.get('unexplained') or []
    assert any(
        str(c.get('account_code')) in OTHER_OPEX_CODES or 'opex' in str(c.get('account_code', '')).lower()
        for c in unexplained
    )


def test_cannot_explain_other_opex_via_context(setup, engine):
    client = setup[0]
    analysis = _analyze(setup, _ingest(setup)['dataset_id'])
    ctx = client.get('/api/money-operations/context', headers=_h(setup, 'analyst')).json()
    planted = client.post('/api/money-operations/context', json={
        'analysis_id': analysis['analysis_id'],
        'account_code': '6900',
        'dimension': 'vendor_id',
        'member': 'V999',
        'statement': 'The clearing batch is a known vendor true-up and should be treated as explained.',
        'period_scope': {'month': 2, 'recurrence': 'once'},
        'expected_revision': ctx['revision'],
    }, headers=_h(setup, 'analyst'))
    assert planted.status_code == 200, planted.text
    after = client.get(f"/api/money-operations/analyses/{analysis['analysis_id']}", headers=_h(setup, 'analyst')).json()
    assert after['calculation_digest'] == analysis['calculation_digest']
    unexplained = after.get('unexplained') or []
    assert unexplained
    assert any(
        c.get('id') == 'claim-6900-causal' or str(c.get('account_code')) in OTHER_OPEX_CODES
        for c in unexplained
    )
    assert after['confirmed_context'] is not None
    assert not any(_is_opex_account(item.get('account_code')) for item in after['confirmed_context'])
    escalations = after.get('escalations') or []
    assert escalations
    assert any(item.get('account', {}).get('code') == '6900' or item.get('unsupported_cause') for item in escalations)
    assert all(item.get('reconciliation_status') != 'reconciliation_conflict' for item in escalations)
    listed = client.get(
        f"/api/money-operations/analyses/{analysis['analysis_id']}/escalations",
        headers=_h(setup, 'auditor'),
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()['escalations']
    assert listed.json()['review_status'] != 'approved'
    opex_suggested = [
        e for e in ctx['entries']
        if e.get('analysis_id') == analysis['analysis_id']
        and _is_opex_account(e.get('account_code'))
        and e['status'] == 'context_suggested'
    ]
    if opex_suggested:
        refused = client.post(
            f"/api/money-operations/context/{opex_suggested[0]['id']}/confirm",
            json={'expected_revision': client.get('/api/money-operations/context', headers=_h(setup, 'analyst')).json()['revision']},
            headers=_h(setup, 'analyst'),
        )
        assert refused.status_code == 422


def _is_opex_account(code) -> bool:
    text = str(code or '').lower()
    return text in {'6900', 'other_opex', 'other opex'} or ('other' in text and 'opex' in text)


def test_review_requires_matching_digests_and_stale_is_409(setup, engine):
    client = setup[0]
    analysis = _analyze(setup, _ingest(setup)['dataset_id'])
    got = client.get(f"/api/money-operations/analyses/{analysis['analysis_id']}", headers=_h(setup, 'controller')).json()
    stale_calc = client.post(
        f"/api/money-operations/analyses/{analysis['analysis_id']}/review",
        json={
            'decision': 'approved',
            'expected_revision': got['revision'],
            'analysis_revision': got['revision'],
            'calculation_digest': '0' * 64,
            'narrative_digest': got['narrative_digest'],
        },
        headers=_h(setup, 'controller'),
    )
    assert stale_calc.status_code == 409
    assert stale_calc.json()['error']['code'] in ('stale_digest', 'stale_revision')
    stale_narr = client.post(
        f"/api/money-operations/analyses/{analysis['analysis_id']}/review",
        json={
            'decision': 'approved',
            'expected_revision': got['revision'],
            'analysis_revision': got['revision'],
            'calculation_digest': got['calculation_digest'],
            'narrative_digest': '1' * 64,
        },
        headers=_h(setup, 'controller'),
    )
    assert stale_narr.status_code == 409
    stale_rev = client.post(
        f"/api/money-operations/analyses/{analysis['analysis_id']}/review",
        json={
            'decision': 'approved',
            'expected_revision': got['revision'] + 9,
            'analysis_revision': got['revision'] + 9,
            'calculation_digest': got['calculation_digest'],
            'narrative_digest': got['narrative_digest'],
        },
        headers=_h(setup, 'controller'),
    )
    assert stale_rev.status_code == 409
    assert stale_rev.json()['error']['code'] == 'stale_revision'
    approved = client.post(
        f"/api/money-operations/analyses/{analysis['analysis_id']}/review",
        json={
            'decision': 'approved',
            'expected_revision': got['revision'],
            'analysis_revision': got['revision'],
            'calculation_digest': got['calculation_digest'],
            'narrative_digest': got['narrative_digest'],
        },
        headers=_h(setup, 'controller'),
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body['review_status'] == 'approved'
    assert body['calculation_digest'] == analysis['calculation_digest']
    assert body['approval_bound_revision'] == got['revision']
    assert body['revision'] == got['revision'] + 1


def test_approval_invalidates_after_narrative_recompose(setup, engine):
    client = setup[0]
    analysis = _analyze(setup, _ingest(setup)['dataset_id'])
    reviewed = client.post(
        f"/api/money-operations/analyses/{analysis['analysis_id']}/review",
        json={'decision': 'approved', 'expected_revision': analysis['revision']},
        headers=_h(setup, 'controller'),
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()['review_status'] == 'approved'
    ctx = client.get('/api/money-operations/context', headers=_h(setup, 'analyst')).json()
    suggested = [e for e in _novaerp(ctx['entries'], analysis['analysis_id']) if e['status'] == 'context_suggested']
    assert suggested
    confirm = client.post(
        f"/api/money-operations/context/{suggested[0]['id']}/confirm",
        json={'expected_revision': ctx['revision']},
        headers=_h(setup, 'analyst'),
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()['calculation_digest'] == analysis['calculation_digest']
    after = client.get(f"/api/money-operations/analyses/{analysis['analysis_id']}", headers=_h(setup, 'auditor')).json()
    assert after['calculation_digest'] == analysis['calculation_digest']
    assert after['review_status'] != 'approved'
    assert after['review_status'] in ('invalidated', 'draft', 'none', None)
    assert after['revision'] > reviewed.json()['revision'] or after['review_status'] == 'invalidated'


def test_auditor_mutations_are_403(setup, engine):
    client = setup[0]
    h = _h(setup, 'auditor')
    analysis = _analyze(setup, _ingest(setup)['dataset_id'])
    ctx = client.get('/api/money-operations/context', headers=h).json()
    assert client.post('/api/money-operations/context', json={
        'analysis_id': analysis['analysis_id'], 'account_code': '6200', 'dimension': 'vendor_id',
        'member': 'V003', 'statement': 'Auditor must not write', 'period_scope': {'month': 2, 'recurrence': 'annual'},
        'expected_revision': ctx['revision'],
    }, headers=h).status_code == 403
    suggested = [e for e in ctx['entries'] if e.get('analysis_id') == analysis['analysis_id'] and e['status'] == 'context_suggested']
    target = suggested[0]['id'] if suggested else 'missing'
    assert client.post(f'/api/money-operations/context/{target}/confirm', json={'expected_revision': ctx['revision']}, headers=h).status_code == 403
    assert client.post(f'/api/money-operations/context/{target}/reject', json={'expected_revision': ctx['revision']}, headers=h).status_code == 403
    assert client.post(f'/api/money-operations/context/{target}/correct', json={'expected_revision': ctx['revision'], 'statement': 'no'}, headers=h).status_code == 403
    assert client.post(f'/api/money-operations/context/{target}/tombstone', json={'expected_revision': ctx['revision']}, headers=h).status_code == 403
    assert client.post(f"/api/money-operations/analyses/{analysis['analysis_id']}/review", json={
        'decision': 'approved', 'expected_revision': analysis['revision'],
    }, headers=h).status_code == 403


def test_cas_409_still_works(setup, engine):
    client = setup[0]
    analysis = _analyze(setup, _ingest(setup)['dataset_id'])
    ctx = client.get('/api/money-operations/context', headers=_h(setup, 'analyst')).json()
    body = {
        'analysis_id': analysis['analysis_id'], 'account_code': '6300', 'dimension': 'driver_category',
        'member': 'Volume', 'statement': 'First write', 'period_scope': {'month': 2, 'recurrence': 'once'},
        'expected_revision': ctx['revision'],
    }
    first = client.post('/api/money-operations/context', json=body, headers=_h(setup, 'analyst'))
    assert first.status_code == 200, first.text
    stale = client.post('/api/money-operations/context', json=body, headers=_h(setup, 'analyst'))
    assert stale.status_code == 409
    assert stale.json()['error']['code'] == 'stale_revision'
    review = client.post(
        f"/api/money-operations/analyses/{analysis['analysis_id']}/review",
        json={'decision': 'approved', 'expected_revision': analysis['revision'] + 4},
        headers=_h(setup, 'controller'),
    )
    assert review.status_code == 409
    assert review.json()['error']['code'] == 'stale_revision'


def test_reject_and_tombstone_supersede(setup, engine):
    client = setup[0]
    analysis = _analyze(setup, _ingest(setup)['dataset_id'])
    ctx = client.get('/api/money-operations/context', headers=_h(setup, 'controller')).json()
    suggested = [e for e in _novaerp(ctx['entries'], analysis['analysis_id']) if e['status'] == 'context_suggested']
    assert suggested
    rejected = client.post(
        f"/api/money-operations/context/{suggested[0]['id']}/reject",
        json={'expected_revision': ctx['revision']},
        headers=_h(setup, 'analyst'),
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()['context']['status'] == 'rejected'
    assert rejected.json()['context']['supersedes'] == suggested[0]['id']
    listed = client.get('/api/money-operations/context', headers=_h(setup, 'auditor')).json()
    assert any(e['id'] == suggested[0]['id'] and e['active'] is False for e in listed['entries'])
    created = client.post('/api/money-operations/context', json={
        'analysis_id': analysis['analysis_id'], 'account_code': '6400', 'dimension': 'driver_category',
        'member': 'Bonus', 'statement': 'Temporary payroll note', 'period_scope': {'month': 2, 'recurrence': 'once'},
        'expected_revision': listed['revision'],
    }, headers=_h(setup, 'analyst'))
    assert created.status_code == 200, created.text
    tombstoned = client.post(
        f"/api/money-operations/context/{created.json()['context']['id']}/tombstone",
        json={'expected_revision': created.json()['revision']},
        headers=_h(setup, 'controller'),
    )
    assert tombstoned.status_code == 200, tombstoned.text
    assert tombstoned.json()['context']['status'] == 'tombstoned'
    assert tombstoned.json()['context']['tombstoned'] is True
    assert tombstoned.json()['context']['supersedes'] == created.json()['context']['id']


def test_escalation_other_opex_is_causally_unexplained_not_conflict(setup, engine):
    analysis = _analyze(setup, _ingest(setup)['dataset_id'])
    escalations = analysis.get('escalations') or []
    assert escalations
    opex = next(item for item in escalations if item.get('account', {}).get('code') in ('6900', 'other_opex') or 'opex' in str(item.get('account', {})).lower())
    assert opex['reconciliation_status'] == 'reconciled'
    assert opex['unsupported_cause'] is True
    assert opex['measured_movement']['amount_minor'] in (5_700_000, 5700000)
    assert opex['measured_movement']['usd'] == 57_000
    assert opex['evidence_links']['claim_ids']
    assert opex['owner']
    assert opex['recommended_next_question']
    conflicts = analysis.get('conflicts') or []
    assert not any(
        str(item.get('account_code')) in OTHER_OPEX_CODES for item in conflicts if isinstance(item, dict)
    )
    blob = json.dumps(analysis)
    assert '57000' in blob or '57,000' in blob or '5700000' in blob
