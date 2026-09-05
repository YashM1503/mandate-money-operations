from __future__ import annotations

import csv
import json
import random
import shutil
from pathlib import Path

import pytest

from mandate.money_operations import (
    CALCULATION_VERSION,
    DatasetValidationError,
    analyze,
    attribute_drivers,
    compare_periods,
    reconcile_account,
    validate_dataset,
)
from mandate.money_operations.integer import percentage_variance_bps, round_half_away_from_zero

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'sample-data' / 'money-operations'
PRIOR = '2026-01'
CURRENT = '2026-02'


def _claim(analysis: dict, claim_id: str) -> dict:
    return next(item for item in analysis['claims'] if item['id'] == claim_id)


def _copy_fixture(tmp_path: Path) -> Path:
    dest = tmp_path / 'money-operations'
    shutil.copytree(FIXTURE, dest)
    return dest


def _shuffle_csv(path: Path, seed: int) -> None:
    with path.open(encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.reader(handle))
    header, body = rows[0], rows[1:]
    rng = random.Random(seed)
    rng.shuffle(body)
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(body)


def _walk(obj, path='$'):
    if isinstance(obj, float):
        raise AssertionError(f'float at {path}: {obj!r}')
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.endswith(('_minor', '_bps', '_usd')) or key in {
                'headcount_prior', 'headcount_current', 'headcount_change',
                'row_count', 'rank', 'score', 'byte_size',
            }:
                assert value is None or isinstance(value, int), f'{path}.{key}={value!r}'
            _walk(value, f'{path}.{key}')
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            _walk(value, f'{path}[{index}]')


def _write_mini_dataset(tmp_path: Path, *, prior_revenue: int, current_revenue: int,
                        prior_software: int = 0, current_software: int = 0) -> Path:
    dest = tmp_path / 'mini'
    dest.mkdir()
    (dest / 'monthly_account_summaries.csv').write_text(
        'period,period_end,gross_revenue,refunds,net_revenue,cogs,gross_profit,software_expense,'
        'logistics_expense,payroll_expense,marketing_expense,other_opex,total_opex,'
        'operating_profit,headcount,currency,source_system\n'
        f'2026-01,2026-01-31,{prior_revenue},0,{prior_revenue},0,{prior_revenue},{prior_software},'
        f'0,0,0,0,{prior_software},{prior_revenue - prior_software},1,USD,Synthetic GL\n'
        f'2026-02,2026-02-28,{current_revenue},0,{current_revenue},0,{current_revenue},{current_software},'
        f'0,0,0,0,{current_software},{current_revenue - current_software},1,USD,Synthetic GL\n',
        encoding='utf-8',
    )
    revenue_rows = [
        'transaction_id,date,period,customer_id,customer_name,segment,product,channel,region,'
        'transaction_type,amount,source_system,invoice_id',
    ]
    if prior_revenue:
        revenue_rows.append(
            f'REV-202601-C001-01,2026-01-08,2026-01,C001,Northstar Commerce,Enterprise,Platform,'
            f'Direct,Northeast,Sale,{prior_revenue},Synthetic ERP,INV-1',
        )
    if current_revenue:
        revenue_rows.append(
            f'REV-202602-C001-01,2026-02-08,2026-02,C001,Northstar Commerce,Enterprise,Platform,'
            f'Direct,Northeast,Sale,{current_revenue},Synthetic ERP,INV-2',
        )
    (dest / 'revenue_transactions.csv').write_text('\n'.join(revenue_rows) + '\n', encoding='utf-8')
    expense_rows = [
        'transaction_id,date,period,account,vendor_id,vendor_name,driver_category,amount,'
        'headcount_effect,source_system,invoice_id,description',
    ]
    if prior_software:
        expense_rows.append(
            'EXP-202601-SOFT-01,2026-01-08,2026-01,Software,V003,NovaERP,Recurring subscription,'
            f'{prior_software},0,Synthetic AP,BILL-1,ERP',
        )
    if current_software:
        expense_rows.append(
            'EXP-202602-SOFT-01,2026-02-08,2026-02,Software,V003,NovaERP,Recurring subscription,'
            f'{current_software},0,Synthetic AP,BILL-2,ERP',
        )
    (dest / 'expense_transactions.csv').write_text('\n'.join(expense_rows) + '\n', encoding='utf-8')
    return dest


def test_validate_dataset_fixture_succeeds():
    result = validate_dataset(FIXTURE)
    assert result['status'] == 'validated'
    assert result['available_periods'] == ['2025-10', '2025-11', '2025-12', '2026-01', '2026-02', '2026-03']
    assert result['findings']
    assert all(item['severity'] == 'info' for item in result['findings'])
    assert all('synthetic' in item['code'] for item in result['findings'])
    hashes = {item['file_name']: item['sha256'] for item in result['sources']}
    manifest = json.loads((FIXTURE / 'validation_manifest.json').read_text(encoding='utf-8'))
    for file_name, digest in manifest['source_hashes'].items():
        assert hashes[file_name] == digest


def test_oracle_revenue_enterprise_and_top3():
    analysis = analyze(FIXTURE, PRIOR, CURRENT)
    assert analysis['calculation_version'] == CALCULATION_VERSION
    revenue = analysis['accounts']['4000']['variance']
    assert revenue['absolute_variance_minor'] == 675_000 * 100
    assert revenue['absolute_variance_usd'] == 675_000
    assert revenue['percentage_variance_bps'] == 1800
    assert revenue['percentage_state'] == 'comparable'
    assert revenue['direction'] == 'increase'
    assert revenue['favorability'] == 'favorable'

    enterprise = _claim(analysis, 'claim-4000-driver-segment-Enterprise')
    assert enterprise['value_json']['delta_minor'] == 576_000 * 100
    assert enterprise['value_json']['percentage_variance_bps'] == 3200
    assert enterprise['value_json']['share_bps'] == 8533

    top3 = _claim(analysis, 'claim-4000-top3-customers')
    assert top3['value_json']['delta_minor'] == 432_000 * 100
    assert top3['value_json']['share_bps'] == 6400
    assert top3['value_json']['customer_ids'] == ['C001', 'C002', 'C003']


def test_oracle_other_opex_reconciled_but_unexplained():
    analysis = analyze(FIXTURE, PRIOR, CURRENT)
    opex = analysis['accounts']['6900']
    assert opex['variance']['absolute_variance_minor'] == 57_000 * 100
    assert opex['reconciliation']['status'] == 'reconciled'
    assert opex['reconciliation']['unexplained_residual_minor'] == 0
    assert opex['causal']['status'] == 'unexplained'
    assert opex['causal']['explained_minor'] == 0
    assert opex['causal']['unexplained_residual_minor'] == 57_000 * 100
    causal = _claim(analysis, 'claim-6900-causal')
    assert causal['status'] == 'unexplained'
    assert reconcile_account(analysis, '6900')['status'] == 'reconciled'


def test_oracle_expense_and_refund_drivers():
    analysis = analyze(FIXTURE, PRIOR, CURRENT)
    assert analysis['accounts']['6200']['variance']['absolute_variance_minor'] == 82_000 * 100
    nova = _claim(analysis, 'claim-6200-driver-vendor-id-V003')
    assert nova['value_json']['delta_minor'] == 82_000 * 100

    logistics = analysis['accounts']['6300']
    assert logistics['variance']['absolute_variance_minor'] == 93_000 * 100
    volume = _claim(analysis, 'claim-6300-driver-driver-category-Volume')
    expedited = _claim(analysis, 'claim-6300-driver-driver-category-Expedited-shipping')
    assert volume['value_json']['delta_minor'] == 60_000 * 100
    assert expedited['value_json']['delta_minor'] == 33_000 * 100

    payroll = analysis['accounts']['6400']
    assert payroll['variance']['absolute_variance_minor'] == 120_000 * 100
    assert payroll['headcount']['change'] == 0
    assert payroll['headcount']['current'] == 118
    bonus = _claim(analysis, 'claim-6400-driver-driver-category-Performance-bonus')
    assert bonus['value_json']['delta_minor'] == 120_000 * 100

    refunds = analysis['accounts']['4100']['variance']
    assert refunds['absolute_variance_minor'] == 48_000 * 100
    assert refunds['favorability'] == 'unfavorable'
    pro = _claim(analysis, 'claim-4100-driver-product-SmartHub-Pro')
    assert pro['value_json']['delta_minor'] == 42_000 * 100
    assert pro['value_json']['share_bps'] == 8750


def test_shuffled_rows_preserve_digest_and_oracle(tmp_path):
    baseline = analyze(FIXTURE, PRIOR, CURRENT)
    dest = _copy_fixture(tmp_path)
    _shuffle_csv(dest / 'revenue_transactions.csv', seed=7)
    _shuffle_csv(dest / 'expense_transactions.csv', seed=11)
    shuffled = analyze(dest, PRIOR, CURRENT)
    assert shuffled['calculation_digest'] == baseline['calculation_digest']
    assert shuffled['accounts']['4000']['variance']['absolute_variance_minor'] == 675_000 * 100
    assert _claim(shuffled, 'claim-4000-driver-segment-Enterprise')['value_json']['delta_minor'] == 576_000 * 100
    assert _claim(shuffled, 'claim-4000-top3-customers')['value_json']['share_bps'] == 6400
    assert shuffled['accounts']['6900']['causal']['status'] == 'unexplained'


def test_grouped_member_sums_equal_account_detail_totals():
    analysis = analyze(FIXTURE, PRIOR, CURRENT)
    for account in analysis['accounts'].values():
        detail = account['detail']
        blocks = [account['drivers']['primary'], *account['drivers']['alternatives']]
        for block in blocks:
            assert sum(row['prior_minor'] for row in block['members']) == detail['prior_minor']
            assert sum(row['current_minor'] for row in block['members']) == detail['current_minor']


def test_sum_of_driver_deltas_equals_detail_variance():
    analysis = analyze(FIXTURE, PRIOR, CURRENT)
    for account in analysis['accounts'].values():
        detail_variance = account['detail']['variance_minor']
        blocks = [account['drivers']['primary'], *account['drivers']['alternatives']]
        for block in blocks:
            assert sum(row['delta_minor'] for row in block['members']) == detail_variance
        assert account['reconciliation']['status'] == 'reconciled'
        assert account['reconciliation']['variance_reconciliation_difference_minor'] == 0


def test_zero_prior_new_activity(tmp_path):
    dest = _write_mini_dataset(tmp_path, prior_revenue=0, current_revenue=5000, current_software=0)
    analysis = analyze(dest, PRIOR, CURRENT)
    revenue = analysis['accounts']['4000']['variance']
    assert revenue['prior_minor'] == 0
    assert revenue['current_minor'] == 5000 * 100
    assert revenue['absolute_variance_minor'] == 5000 * 100
    assert revenue['percentage_variance_bps'] is None
    assert revenue['percentage_state'] == 'new_activity'

    flat = analysis['accounts']['6200']['variance']
    assert flat['prior_minor'] == 0
    assert flat['current_minor'] == 0
    assert flat['percentage_variance_bps'] == 0
    assert flat['percentage_state'] == 'comparable'

    bps, state = percentage_variance_bps(0, 0)
    assert bps == 0 and state == 'comparable'
    bps, state = percentage_variance_bps(100, 0)
    assert bps is None and state == 'new_activity'
    assert round_half_away_from_zero(5, 2) == 3
    assert round_half_away_from_zero(-5, 2) == -3


def test_source_hash_change_and_duplicate_ids_fail_closed(tmp_path):
    changed = _copy_fixture(tmp_path / 'changed')
    revenue = changed / 'revenue_transactions.csv'
    revenue.write_bytes(revenue.read_bytes() + b' ')
    result = validate_dataset(changed)
    assert result['status'] == 'invalid'
    assert any(item['code'] == 'hash_mismatch' for item in result['findings'])

    duplicated = _copy_fixture(tmp_path / 'duplicated')
    path = duplicated / 'revenue_transactions.csv'
    text = path.read_text(encoding='utf-8')
    first_data = text.splitlines()[1]
    path.write_text(text.rstrip() + '\n' + first_data + '\n', encoding='utf-8')
    result = validate_dataset(duplicated)
    assert result['status'] == 'invalid'
    assert any(item['code'] == 'duplicate_transaction_id' for item in result['findings'])
    with pytest.raises(DatasetValidationError):
        analyze(duplicated, PRIOR, CURRENT)


def test_integer_only_minor_units():
    analysis = analyze(FIXTURE, PRIOR, CURRENT)
    _walk(analysis)
    for account in analysis['accounts'].values():
        assert isinstance(account['variance']['absolute_variance_minor'], int)
        assert isinstance(account['detail']['prior_minor'], int)
        assert isinstance(account['detail']['current_minor'], int)
        if account['variance']['percentage_variance_bps'] is not None:
            assert isinstance(account['variance']['percentage_variance_bps'], int)


def test_compare_and_attribute_public_interfaces():
    analysis = analyze(FIXTURE, PRIOR, CURRENT)
    compared = compare_periods(FIXTURE, PRIOR, CURRENT)
    assert [item['account_code'] for item in compared['variances']] == [
        item['account_code'] for item in analysis['variances']
    ]
    drivers = attribute_drivers(analysis, '4000')
    assert drivers['primary_dimension'] == 'segment'
    assert any(row['member'] == 'Enterprise' for row in drivers['primary']['members'])
    reconciliation = reconcile_account(analysis, '4000')
    assert reconciliation['status'] == 'reconciled'
