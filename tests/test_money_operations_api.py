from pathlib import Path
from unittest.mock import patch
import hashlib
import json
import pytest

from mandate.money_operations import analyze as engine_analyze
from mandate.money_operations_narrative import NarrativeError, compose, neutralize_csv_cell, validate_narrative
from test_mvp import setup

FIXTURE = Path(__file__).resolve().parents[1] / 'sample-data' / 'money-operations'


def _fake_analyze(path, prior, current, entity_id='yari-retail-us'):
    customers = [
        {'source_file': 'revenue_transactions.csv', 'transaction_id': f'REV-202602-C00{i}-01', 'source_row_number': i}
        for i in range(1, 6)
    ]
    claims = [
        {
            'id': 'VAR-REV',
            'account_code': 'gross_revenue',
            'account_name': 'Revenue',
            'claim_type': 'variance',
            'status': 'reconciled',
            'amount_minor': 67_500_000,
            'percentage_bps': 1800,
            'direction': 'increase',
            'entities': ['Revenue'],
            'formula': 'current_minor - prior_minor',
            'source_ids': ['src-monthly-account-summaries', 'src-revenue-transactions'],
            'source_rows': [
                {'source_file': 'monthly_account_summaries.csv', 'source_row_id': '2026-01'},
                {'source_file': 'monthly_account_summaries.csv', 'source_row_id': '2026-02'},
            ],
        },
        {
            'id': 'DRV-ENT',
            'account_code': 'gross_revenue',
            'account_name': 'Revenue',
            'claim_type': 'driver',
            'status': 'reconciled',
            'amount_minor': 57_600_000,
            'percentage_bps': 3200,
            'share_bps': 8533,
            'direction': 'increase',
            'entities': ['Enterprise'],
            'formula': 'sum(enterprise current) - sum(enterprise prior)',
            'source_ids': ['src-revenue-transactions'],
            'source_rows': customers[:2],
        },
        {
            'id': 'DRV-TOP3',
            'account_code': 'gross_revenue',
            'account_name': 'Revenue',
            'claim_type': 'driver',
            'status': 'reconciled',
            'amount_minor': 43_200_000,
            'share_bps': 6400,
            'direction': 'increase',
            'entities': ['Northstar Commerce', 'Atlas Industrial', 'Forma Retail Group'],
            'formula': 'sum(C001,C002,C003 deltas)',
            'source_ids': ['src-revenue-transactions'],
            'source_rows': customers,
        },
        {
            'id': 'VAR-SW',
            'account_code': 'software_expense',
            'account_name': 'Software',
            'claim_type': 'variance',
            'status': 'reconciled',
            'amount_minor': 8_200_000,
            'entities': ['NovaERP', 'Software'],
            'formula': 'current_minor - prior_minor',
            'source_ids': ['src-expense-transactions'],
            'source_rows': [{'source_file': 'expense_transactions.csv', 'transaction_id': 'EXP-202602-SOFT-03'}],
        },
        {
            'id': 'VAR-UNK',
            'account_code': 'other_opex',
            'account_name': 'Other Opex',
            'claim_type': 'variance',
            'status': 'unexplained',
            'amount_minor': 5_700_000,
            'unexplained_residual_minor': 5_700_000,
            'entities': ['Other Opex', 'Unmapped clearing batch'],
            'formula': 'current_minor - prior_minor',
            'source_ids': ['src-expense-transactions'],
            'source_rows': [{'source_file': 'expense_transactions.csv', 'transaction_id': 'EXP-202602-OTHE-16'}],
        },
    ]
    digest = hashlib.sha256(json.dumps({'claims': [c['id'] for c in claims], 'prior': prior, 'current': current}, sort_keys=True).encode()).hexdigest()
    return {
        'claims': claims,
        'variances': [c for c in claims if c['claim_type'] == 'variance'],
        'calculation_digest': digest,
        'calculation_version': 'mo-calc-1.0',
        'entity_id': entity_id,
        'periods': {'prior': prior, 'current': current},
        'currency': 'USD',
        'unexplained': [claims[-1]],
        'conflicts': [],
    }


def _engine_ready():
    try:
        engine_analyze(FIXTURE, '2026-01', '2026-02', 'yari-retail-us')
        return True
    except NotImplementedError:
        return False


@pytest.fixture
def engine(monkeypatch):
    if _engine_ready():
        return 'live'
    monkeypatch.setattr('mandate.money_operations.analyze', _fake_analyze)
    return 'stub'


def _h(setup, role):
    return setup[2][role]


def _ingest(setup, role='analyst'):
    client = setup[0]
    res = client.post('/api/money-operations/datasets', json={'fixture': 'reference'}, headers=_h(setup, role))
    assert res.status_code == 201, res.text
    return res.json()


def _analyze(setup, dataset_id, role='analyst', status=201, **extra):
    client = setup[0]
    body = {'dataset_id': dataset_id, 'entity_id': 'yari-retail-us', 'prior_period': '2026-01', 'current_period': '2026-02', **extra}
    res = client.post('/api/money-operations/analyses', json=body, headers=_h(setup, role))
    assert res.status_code == status, res.text
    return res.json()


def _blob(obj):
    return json.dumps(obj)


def test_money_operations_page_is_served(setup):
    client = setup[0]
    page = client.get('/money-operations')
    assert page.status_code == 200
    assert 'text/html' in page.headers.get('content-type', '')
    assert b'Connected API' in page.content
    assert client.get('/').status_code == 200
    assert client.get('/security').status_code == 200


def test_unauthenticated_requests_are_401(setup):
    client = setup[0]
    assert client.get('/api/money-operations/context').status_code == 401
    assert client.post('/api/money-operations/datasets', json={'fixture': 'reference'}).status_code == 401
    assert client.post('/api/money-operations/analyses', json={
        'dataset_id': 'x', 'entity_id': 'yari-retail-us', 'prior_period': '2026-01', 'current_period': '2026-02',
    }).status_code == 401


def test_auditor_writes_are_403(setup, engine):
    client = setup[0]
    h = _h(setup, 'auditor')
    assert client.post('/api/money-operations/datasets', json={'fixture': 'reference'}, headers=h).status_code == 403
    ds = _ingest(setup)
    assert client.post('/api/money-operations/analyses', json={
        'dataset_id': ds['dataset_id'], 'entity_id': 'yari-retail-us', 'prior_period': '2026-01', 'current_period': '2026-02',
    }, headers=h).status_code == 403
    analysis = _analyze(setup, ds['dataset_id'])
    ctx = client.get('/api/money-operations/context', headers=h)
    assert ctx.status_code == 200
    assert client.post('/api/money-operations/context', json={
        'analysis_id': analysis['analysis_id'], 'account_code': 'software_expense', 'dimension': 'vendor_id',
        'member': 'V003', 'statement': 'Auditor must not write', 'period_scope': {'month': 2, 'recurrence': 'annual'},
        'expected_revision': ctx.json()['revision'],
    }, headers=h).status_code == 403
    assert client.post(f"/api/money-operations/analyses/{analysis['analysis_id']}/review", json={
        'decision': 'approved', 'expected_revision': analysis['revision'],
    }, headers=h).status_code == 403
    ctx = client.get('/api/money-operations/context', headers=_h(setup, 'analyst')).json()
    suggested = [e for e in ctx['entries'] if e.get('analysis_id') == analysis['analysis_id'] and e['status'] == 'context_suggested']
    if suggested:
        assert client.post(f"/api/money-operations/context/{suggested[0]['id']}/reject", json={
            'expected_revision': ctx['revision'],
        }, headers=h).status_code == 403
        assert client.post(f"/api/money-operations/context/{suggested[0]['id']}/tombstone", json={
            'expected_revision': ctx['revision'],
        }, headers=h).status_code == 403


def test_stale_revision_returns_409_envelope(setup, engine):
    client = setup[0]
    ds = _ingest(setup)
    analysis = _analyze(setup, ds['dataset_id'])
    ctx = client.get('/api/money-operations/context', headers=_h(setup, 'analyst')).json()
    body = {
        'analysis_id': analysis['analysis_id'], 'account_code': 'logistics_expense', 'dimension': 'driver_category',
        'member': 'Volume', 'statement': 'First write', 'period_scope': {'month': 2, 'recurrence': 'once'},
        'expected_revision': ctx['revision'],
    }
    first = client.post('/api/money-operations/context', json=body, headers=_h(setup, 'analyst'))
    assert first.status_code == 200, first.text
    stale = client.post('/api/money-operations/context', json=body, headers=_h(setup, 'analyst'))
    assert stale.status_code == 409
    err = stale.json()['error']
    assert err['code'] == 'stale_revision'
    assert 'actual_revision' in err['details']
    review = client.post(f"/api/money-operations/analyses/{analysis['analysis_id']}/review", json={
        'decision': 'approved', 'expected_revision': analysis['revision'] + 5,
    }, headers=_h(setup, 'controller'))
    assert review.status_code == 409
    assert review.json()['error']['code'] == 'stale_revision'


def test_fixture_ingest_and_analyze(setup, engine):
    ds = _ingest(setup)
    assert ds['status'] == 'validated'
    assert '2026-01' in ds['available_periods'] and '2026-02' in ds['available_periods']
    assert any(s.get('file_name') == 'monthly_account_summaries.csv' for s in ds['sources'])
    analysis = _analyze(setup, ds['dataset_id'])
    assert analysis['analysis_id']
    blob = _blob(analysis)
    assert '675000' in blob or '675,000' in blob
    assert '18.0%' in blob or '1800' in blob
    assert '576000' in blob or '576,000' in blob
    assert '432000' in blob or '432,000' in blob
    assert analysis['calculation_digest']
    assert analysis['calculation_version']
    got = setup[0].get(f"/api/money-operations/analyses/{analysis['analysis_id']}", headers=_h(setup, 'auditor'))
    assert got.status_code == 200
    assert got.json()['calculation_digest'] == analysis['calculation_digest']
    variance = setup[0].get(
        f"/api/money-operations/analyses/{analysis['analysis_id']}/variances/other_opex",
        headers=_h(setup, 'analyst'),
    )
    assert variance.status_code == 200, variance.text


def test_context_suggested_not_auto_confirmed(setup, engine):
    client = setup[0]
    analysis = _analyze(setup, _ingest(setup)['dataset_id'])
    ctx = client.get('/api/money-operations/context', headers=_h(setup, 'analyst')).json()
    suggested = [e for e in ctx['entries'] if e['status'] == 'context_suggested' and e.get('analysis_id') == analysis['analysis_id']]
    software = [
        e for e in suggested
        if e['account_code'] in ('6200', 'software_expense', 'Software') or 'software' in str(e['account_code']).lower()
    ]
    software = [e for e in software if 'novaerp' in e['statement'].lower() or 'erp' in e['statement'].lower()] or software
    assert software, ctx['entries']
    assert software[0]['status'] == 'context_suggested'
    prior = [
        e for e in ctx['entries']
        if e['status'] == 'user_confirmed' and e.get('analysis_id') in (None, '')
        and e['account_code'] in ('6200', 'software_expense', 'Software')
    ]
    assert prior
    assert analysis['calculation_digest']
    confirm = client.post(
        f"/api/money-operations/context/{software[0]['id']}/confirm",
        json={'expected_revision': ctx['revision']},
        headers=_h(setup, 'analyst'),
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()['context']['status'] == 'user_confirmed'
    assert confirm.json()['calculation_digest'] == analysis['calculation_digest']
    after = client.get(f"/api/money-operations/analyses/{analysis['analysis_id']}", headers=_h(setup, 'analyst')).json()
    assert after['calculation_digest'] == analysis['calculation_digest']


def test_correct_supersedes_and_keeps_history(setup, engine):
    client = setup[0]
    analysis = _analyze(setup, _ingest(setup)['dataset_id'])
    ctx = client.get('/api/money-operations/context', headers=_h(setup, 'controller')).json()
    created = client.post('/api/money-operations/context', json={
        'analysis_id': analysis['analysis_id'], 'account_code': 'payroll_expense', 'dimension': 'driver_category',
        'member': 'Bonus', 'statement': 'Bonuses explain payroll.', 'period_scope': {'month': 2, 'recurrence': 'once'},
        'expected_revision': ctx['revision'],
    }, headers=_h(setup, 'analyst'))
    assert created.status_code == 200, created.text
    digest = created.json()['calculation_digest']
    original_id = created.json()['context']['id']
    corrected = client.post(f'/api/money-operations/context/{original_id}/correct', json={
        'expected_revision': created.json()['revision'],
        'statement': '=1+2 corrected payroll note',
    }, headers=_h(setup, 'controller'))
    assert corrected.status_code == 200, corrected.text
    body = corrected.json()
    assert body['context']['supersedes'] == original_id
    assert body['context']['statement'] == '=1+2 corrected payroll note'
    assert len(body['history']) >= 2
    assert {item['id'] for item in body['history']} >= {original_id, body['context']['id']}
    assert body['calculation_digest'] == digest
    listed = client.get('/api/money-operations/context', headers=_h(setup, 'auditor')).json()['entries']
    assert any(e['id'] == original_id for e in listed)
    assert any(e['id'] == original_id and e['active'] is False for e in listed)
    assert any(e['id'] == body['context']['id'] and e['active'] for e in listed)


def test_invalid_upload_rejected(setup):
    client = setup[0]
    h = _h(setup, 'analyst')
    txt = client.post('/api/money-operations/datasets', files={'file': ('notes.txt', b'not a dataset', 'text/plain')}, headers=h)
    assert txt.status_code == 422
    assert txt.json()['error']['code'] == 'invalid_upload'
    xlsx = client.post('/api/money-operations/datasets', files={'file': ('ledger.xlsx', b'PK', 'application/vnd.ms-excel')}, headers=h)
    assert xlsx.status_code == 422
    traversal = client.post(
        '/api/money-operations/datasets',
        files={'file': ('../secret.csv', b'period,gross_revenue\n2026-01,1\n', 'text/csv')},
        headers=h,
    )
    assert traversal.status_code == 422
    extra = client.post('/api/money-operations/datasets', json={'fixture': 'reference', 'role': 'controller'}, headers=h)
    assert extra.status_code == 422


def test_evidence_pagination(setup, engine):
    analysis = _analyze(setup, _ingest(setup)['dataset_id'])
    claim_id = next((c['id'] for c in analysis['claims'] if c.get('source_rows')), analysis['claims'][0]['id'])
    client = setup[0]
    first = client.get(f'/api/money-operations/claims/{claim_id}/evidence', params={'limit': 2, 'cursor': 0}, headers=_h(setup, 'auditor'))
    assert first.status_code == 200, first.text
    payload = first.json()
    assert payload['total'] >= 1
    assert len(payload['items']) <= 2
    if payload['total'] > 2:
        assert payload['next_cursor'] == 2
        second = client.get(f'/api/money-operations/claims/{claim_id}/evidence', params={'limit': 2, 'cursor': 2}, headers=_h(setup, 'analyst'))
        assert second.status_code == 200
        assert second.json()['items'] != payload['items'] or payload['total'] <= 4
    missing = client.get('/api/money-operations/claims/does-not-exist/evidence', headers=_h(setup, 'analyst'))
    assert missing.status_code == 404


def test_csv_formula_neutralization(setup, engine):
    assert neutralize_csv_cell('=cmd') == "'=cmd"
    assert neutralize_csv_cell('+1+1') == "'+1+1"
    assert neutralize_csv_cell('-57000') == "'-57000"
    assert neutralize_csv_cell('@SUM(A1)') == "'@SUM(A1)"
    assert neutralize_csv_cell('\t=1') == "'\t=1"
    client = setup[0]
    analysis = _analyze(setup, _ingest(setup)['dataset_id'])
    ctx = client.get('/api/money-operations/context', headers=_h(setup, 'analyst')).json()
    planted = client.post('/api/money-operations/context', json={
        'analysis_id': analysis['analysis_id'], 'account_code': 'other_opex', 'dimension': 'vendor_id',
        'member': 'V999', 'statement': "=HYPERLINK(\"http://evil.example\",\"x\")",
        'period_scope': {'month': 2, 'recurrence': 'once'}, 'expected_revision': ctx['revision'],
    }, headers=_h(setup, 'analyst'))
    assert planted.status_code == 200, planted.text
    exported = client.get(f"/api/money-operations/analyses/{analysis['analysis_id']}/export.csv", headers=_h(setup, 'auditor'))
    assert exported.status_code == 200
    text = exported.text
    assert "'=HYPERLINK" in text
    for line in text.splitlines()[1:]:
        for cell in line.split(','):
            raw = cell.strip().strip('"')
            assert not raw.startswith(('=', '+', '-', '@', '\t')) or raw.startswith("'")


def test_export_contains_unexplained(setup, engine):
    client = setup[0]
    analysis = _analyze(setup, _ingest(setup)['dataset_id'])
    exported = client.get(f"/api/money-operations/analyses/{analysis['analysis_id']}/export.json", headers=_h(setup, 'auditor'))
    assert exported.status_code == 200
    body = exported.json()
    blob = _blob(body)
    assert body['unexplained']
    assert 'other_opex' in blob.lower() or 'other opex' in blob.lower()
    assert '57000' in blob or '57,000' in blob
    assert any(str(item.get('status', '')).lower() == 'unexplained' for item in body['unexplained'])
    csv_text = client.get(f"/api/money-operations/analyses/{analysis['analysis_id']}/export.csv", headers=_h(setup, 'analyst')).text
    assert 'unexplained' in csv_text.lower()
    assert 'other_opex' in csv_text.lower() or 'other opex' in csv_text.lower()
    memo = client.get(f"/api/money-operations/analyses/{analysis['analysis_id']}/memo.html", headers=_h(setup, 'controller'))
    assert memo.status_code == 200
    assert 'unexplained' in memo.text.lower()
    lineage = client.get(f"/api/money-operations/analyses/{analysis['analysis_id']}/lineage", headers=_h(setup, 'auditor'))
    assert lineage.status_code == 200
    assert lineage.json()['calculation_digest'] == analysis['calculation_digest']


def test_integration_status_is_not_live(setup, engine):
    client = setup[0]
    analysis = _analyze(setup, _ingest(setup)['dataset_id'])
    status = client.get(
        f"/api/money-operations/analyses/{analysis['analysis_id']}/integration-status",
        headers=_h(setup, 'auditor'),
    ).json()
    assert status['prism'] in (
        'not_configured', 'pending', 'credential_ok', 'credential_configured',
        'live_trace_pending', 'error',
    )
    assert status['prism'] != 'live_connected'
    assert 'live_connected' not in json.dumps(status)
    assert status['gide'] == 'usage_pending'
    assert status['narrative'] == 'deterministic_template'
    assert analysis['integration_status']['prism'] != 'live_connected'


def test_model_and_prism_failure_falls_back_to_template(setup, engine, monkeypatch):
    def bad_compose(package):
        return {
            'text': 'Revenue doubled to $540,000 because I guessed.',
            'cited_claim_ids': ['claim-does-not-exist'],
            'headline': 'Invented',
        }

    monkeypatch.setattr('mandate.money_operations_narrative.try_model_compose', bad_compose)
    analysis = _analyze(setup, _ingest(setup)['dataset_id'])
    narrative = analysis['narrative']
    assert narrative['narrative_source'] == 'deterministic_template'
    assert narrative.get('model_error') == 'validation_or_provider_failed'
    assert '540,000' not in (narrative.get('text') or '')
    assert 'claim-does-not-exist' not in json.dumps(narrative)
    status = setup[0].get(
        f"/api/money-operations/analyses/{analysis['analysis_id']}/integration-status",
        headers=_h(setup, 'analyst'),
    ).json()
    assert status['narrative'] == 'deterministic_template'
    assert status['prism'] != 'live_connected'


def test_narrative_rejects_unknown_claim_ids():
    claims = [{'id': 'VAR-REV', 'amount_minor': 67_500_000, 'percentage_bps': 1800, 'entities': ['Revenue']}]
    with pytest.raises(NarrativeError) as err:
        validate_narrative('Gross revenue increased 18.0% ($675,000).', claims, ['missing-id'])
    assert err.value.code == 'unknown_claim_ids'
    with pytest.raises(NarrativeError) as err:
        validate_narrative('Gross revenue increased $540,000.', claims, ['VAR-REV'])
    assert err.value.code == 'uncited_number'


def test_controller_review_does_not_change_digest(setup, engine):
    client = setup[0]
    analysis = _analyze(setup, _ingest(setup)['dataset_id'])
    reviewed = client.post(
        f"/api/money-operations/analyses/{analysis['analysis_id']}/review",
        json={'decision': 'approved', 'expected_revision': analysis['revision']},
        headers=_h(setup, 'controller'),
    )
    assert reviewed.status_code == 200, reviewed.text
    body = reviewed.json()
    assert body['calculation_digest'] == analysis['calculation_digest']
    assert body['review_status'] == 'approved'
    assert body['revision'] == analysis['revision'] + 1
    assert body.get('approval_bound_revision') == analysis['revision']


def test_real_engine_contract_or_xfail():
    try:
        result = engine_analyze(FIXTURE, '2026-01', '2026-02', 'yari-retail-us')
    except NotImplementedError:
        pytest.xfail('analyze() is not implemented yet')
    assert isinstance(result, dict)
    assert result.get('claims')
    assert 'calculation_digest' in result or 'claims' in result
    blob = json.dumps(result)
    assert '675000' in blob or '675,000' in blob


def test_compose_uses_template_when_model_raises():
    with patch('mandate.money_operations_narrative.try_model_compose', side_effect=RuntimeError('provider down')):
        result = compose({'claims': _fake_analyze(FIXTURE, '2026-01', '2026-02')['claims']})
    assert result['narrative_source'] == 'deterministic_template'
    assert 'unmapped clearing batch' in result['text'].lower()
    assert '$57,000' in result['text']
    assert '$675,000' in result['text']
