from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import pytest

from mandate.money_operations import DatasetValidationError, analyze
from mandate.money_operations.ingest import load_dataset
from mandate.money_operations_narrative import deterministic_template
from mandate.money_operations_service import parse_multipart_files
from test_money_operations_api import _analyze, _h, _ingest, engine, setup


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'sample-data' / 'money-operations'


def _copy_fixture(tmp_path: Path) -> Path:
    destination = tmp_path / 'dataset'
    shutil.copytree(FIXTURE, destination)
    (destination / 'validation_manifest.json').unlink()
    return destination


def test_same_reference_dataset_can_be_ingested_twice(setup):
    first = _ingest(setup)
    second = _ingest(setup)
    assert first['dataset_id'] != second['dataset_id']


def test_dataset_quota_is_enforced(setup, monkeypatch):
    monkeypatch.setenv('MANDATE_MAX_DATASETS_PER_USER', '1')
    _ingest(setup)
    response = setup[0].post(
        '/api/money-operations/datasets',
        json={'fixture': 'reference'},
        headers=_h(setup, 'analyst'),
    )
    assert response.status_code == 429
    assert response.json()['error']['code'] == 'dataset_quota_exceeded'


def test_uploaded_manifest_cannot_authorize_external_egress(setup):
    files = [
        ('files', (path.name, path.read_bytes(), 'text/csv' if path.suffix == '.csv' else 'application/json'))
        for path in FIXTURE.iterdir()
        if path.suffix in {'.csv', '.json'}
    ]
    response = setup[0].post(
        '/api/money-operations/datasets', files=files, headers=_h(setup, 'analyst'),
    )
    assert response.status_code == 201, response.text
    assert response.json()['synthetic'] is False


def test_analysis_must_use_dataset_entity(setup, engine):
    dataset = _ingest(setup)
    response = setup[0].post('/api/money-operations/analyses', json={
        'dataset_id': dataset['dataset_id'],
        'entity_id': 'another-company',
        'prior_period': '2026-01',
        'current_period': '2026-02',
    }, headers=_h(setup, 'analyst'))
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'entity_mismatch'


def test_claim_evidence_requires_analysis_when_claim_id_is_ambiguous(setup, engine):
    dataset = _ingest(setup)
    first = _analyze(setup, dataset['dataset_id'])
    second = _analyze(setup, dataset['dataset_id'])
    original_id = first['claims'][0]['id']
    ambiguous = setup[0].get(
        f'/api/money-operations/claims/{original_id}/evidence',
        headers=_h(setup, 'auditor'),
    )
    assert ambiguous.status_code == 409
    scoped = setup[0].get(
        f'/api/money-operations/claims/{original_id}/evidence',
        params={'analysis_id': second['analysis_id']},
        headers=_h(setup, 'auditor'),
    )
    assert scoped.status_code == 200


def test_exports_exclude_context_from_another_entity(setup, engine):
    client = setup[0]
    home_dataset = _ingest(setup)
    home = _analyze(setup, home_dataset['dataset_id'])
    foreign_dataset = _ingest(setup, entity_id='foreign-company')
    foreign = _analyze(setup, foreign_dataset['dataset_id'], entity_id='foreign-company')
    revision = client.get('/api/money-operations/context', headers=_h(setup, 'analyst')).json()['revision']
    marker = 'FOREIGN-CONTEXT-MUST-NOT-LEAK'
    created = client.post('/api/money-operations/context', json={
        'analysis_id': foreign['analysis_id'],
        'account_code': '6200',
        'dimension': 'vendor_id',
        'member': 'V003',
        'statement': marker,
        'period_scope': {'month': 2, 'recurrence': 'once'},
        'expected_revision': revision,
    }, headers=_h(setup, 'analyst'))
    assert created.status_code == 200, created.text
    for suffix in ('export.json', 'export.csv', 'memo.html'):
        response = client.get(
            f"/api/money-operations/analyses/{home['analysis_id']}/{suffix}",
            headers=_h(setup, 'auditor'),
        )
        assert response.status_code == 200
        assert marker not in response.text


def test_multipart_boundary_keeps_original_case():
    boundary = 'AaB03xZ'
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="files"; '
        'filename="monthly_account_summaries.csv"\r\nContent-Type: text/csv\r\n\r\n'
        f'period\n2026-01\n\r\n--{boundary}--\r\n'
    ).encode()
    files = parse_multipart_files(f'multipart/form-data; boundary={boundary}', body)
    assert files == [('monthly_account_summaries.csv', b'period\n2026-01\n')]


def test_csp_allows_hashed_scripts_without_unsafe_inline(setup):
    response = setup[0].get('/money-operations')
    policy = response.headers['content-security-policy']
    script_policy = policy.split('script-src ', 1)[1].split(';', 1)[0]
    assert "'sha256-" in script_policy
    assert "'unsafe-inline'" not in script_policy


def test_narrative_does_not_use_expense_driver_as_revenue_offset():
    result = analyze(FIXTURE, '2026-01', '2026-02')
    narrative = deterministic_template(result['claims'])
    enterprise = next(item for item in narrative['why'] if 'Enterprise' in item['text'])
    assert 'Recurring subscription' not in enterprise['text']
    assert enterprise['claim_ids']
    assert all('6200' not in claim_id for claim_id in enterprise['claim_ids'])


def test_top_three_customers_are_ranked_instead_of_hardcoded(tmp_path: Path):
    dataset_path = _copy_fixture(tmp_path)
    for file_name in ('revenue_transactions.csv', 'customer_dimension.csv'):
        path = dataset_path / file_name
        text = path.read_text(encoding='utf-8')
        for old, new in (('C001', 'X901'), ('C002', 'X902'), ('C003', 'X903')):
            text = text.replace(old, new)
        path.write_text(text, encoding='utf-8')
    result = analyze(dataset_path, '2026-01', '2026-02')
    top_three = next(item for item in result['claims'] if item['id'] == 'claim-4000-top3-customers')
    assert top_three['value_json']['customer_ids'] == ['X901', 'X902', 'X903']
    assert top_three['value_json']['delta_minor'] == 43_200_000


@pytest.mark.parametrize(
    ('file_name', 'replace_from', 'replace_to', 'expected_code'),
    [
        ('monthly_account_summaries.csv', '2026-02-28', '2026-02-30', 'invalid_date'),
        ('monthly_account_summaries.csv', '2187000,-10000,118,USD', '2187000,-9999,118,USD', 'summary_equation'),
        ('revenue_transactions.csv', ',Synthetic ERP,INV-202510-C001A', ',Synthetic ERP,', 'invalid_schema'),
    ],
)
def test_malformed_financial_records_fail_closed(
    tmp_path: Path, file_name: str, replace_from: str, replace_to: str, expected_code: str,
):
    dataset_path = _copy_fixture(tmp_path)
    path = dataset_path / file_name
    original = path.read_text(encoding='utf-8')
    assert replace_from in original
    path.write_text(original.replace(replace_from, replace_to, 1), encoding='utf-8')
    loaded = load_dataset(dataset_path)
    assert expected_code in {finding['code'] for finding in loaded.error_findings}
    with pytest.raises(DatasetValidationError):
        analyze(dataset_path, '2026-01', '2026-02')


def test_duplicate_dimension_key_and_header_are_rejected(tmp_path: Path):
    dataset_path = _copy_fixture(tmp_path)
    customer_path = dataset_path / 'customer_dimension.csv'
    with customer_path.open(encoding='utf-8', newline='') as handle:
        rows = list(csv.reader(handle))
    rows[0].append(rows[0][0])
    rows[1].append(rows[1][0])
    rows.append(rows[1])
    with customer_path.open('w', encoding='utf-8', newline='') as handle:
        csv.writer(handle).writerows(rows)
    codes = {finding['code'] for finding in load_dataset(dataset_path).error_findings}
    assert {'duplicate_csv_header', 'duplicate_dimension_key'} <= codes


def test_account_configuration_rejects_markup_code(tmp_path: Path):
    dataset_path = _copy_fixture(tmp_path)
    config_path = dataset_path / 'account_configuration.json'
    config = json.loads(config_path.read_text(encoding='utf-8'))
    config['accounts'][0]['account_code'] = '\" onmouseover=\"alert(1)'
    config_path.write_text(json.dumps(config), encoding='utf-8')
    loaded = load_dataset(dataset_path)
    assert 'invalid_account_configuration' in {item['code'] for item in loaded.error_findings}
