"""Build a shareable Money Operations package with valid and rejected edge cases."""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'sample-data' / 'money-operations'
PACKAGE_FILES = (
    'account_configuration.json',
    'business_context_history.json',
    'channel_dimension.csv',
    'customer_dimension.csv',
    'data_dictionary.csv',
    'expense_transactions.csv',
    'monthly_account_summaries.csv',
    'product_dimension.csv',
    'region_dimension.csv',
    'revenue_transactions.csv',
    'vendor_dimension.csv',
)


def read_csv(path: Path) -> list[list[str]]:
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return list(csv.reader(handle, strict=True))


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open('w', encoding='utf-8', newline='') as handle:
        csv.writer(handle, lineterminator='\n').writerows(rows)


def copy_package(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in PACKAGE_FILES:
        shutil.copy2(SOURCE / name, destination / name)


def add_new_activity_periods(destination: Path) -> None:
    summary_path = destination / 'monthly_account_summaries.csv'
    summary = read_csv(summary_path)
    header = summary[0]
    january = dict(zip(header, next(row for row in summary[1:] if row[0] == '2026-01')))
    zero = {name: '0' for name in header}
    zero.update(period='2026-04', period_end='2026-04-30', currency='USD', source_system='Stress GL')
    may = dict(january)
    may.update(period='2026-05', period_end='2026-05-31', source_system='Stress GL')
    summary.extend([[zero[name] for name in header], [may[name] for name in header]])
    write_csv(summary_path, summary)

    for file_name in ('revenue_transactions.csv', 'expense_transactions.csv'):
        path = destination / file_name
        rows = read_csv(path)
        header = rows[0]
        period_index = header.index('period')
        date_index = header.index('date')
        txn_index = header.index('transaction_id')
        invoice_index = header.index('invoice_id')
        additions = []
        for row in rows[1:]:
            if row[period_index] != '2026-01':
                continue
            item = list(row)
            item[period_index] = '2026-05'
            item[date_index] = item[date_index].replace('2026-01', '2026-05')
            item[txn_index] = item[txn_index].replace('202601', '202605')
            item[invoice_index] = item[invoice_index].replace('202601', '202605')
            additions.append(item)
        rows.extend(additions)
        write_csv(path, rows)

    revenue_path = destination / 'revenue_transactions.csv'
    revenue = read_csv(revenue_path)
    header = revenue[0]
    for row in revenue[1:]:
        if row[header.index('period')] == '2026-05' and row[header.index('customer_id')] == 'C001':
            row[header.index('customer_name')] = 'Northstar,\nCommerce'
            row[header.index('channel')] = ''
            break
    write_csv(revenue_path, revenue)


def write_manifest(destination: Path, dataset_id: str, expected: dict) -> None:
    hashes = {
        name: hashlib.sha256((destination / name).read_bytes()).hexdigest()
        for name in PACKAGE_FILES
    }
    manifest = {
        'dataset_id': dataset_id,
        'synthetic': True,
        'period_range': {'from': '2025-10', 'to': '2026-05'},
        'focus_pairs': [
            {'prior': '2026-01', 'current': '2026-02', 'case': 'growth'},
            {'prior': '2026-02', 'current': '2026-03', 'case': 'decline'},
            {'prior': '2026-04', 'current': '2026-05', 'case': 'new_activity_zero_base'},
        ],
        'edge_cases': [
            'revenue increase and decrease', 'zero comparison base', 'new and churned activity',
            'refund sign normalization', 'quoted multiline CSV field', 'blank dimension member',
            'customer concentration', 'unexplained but reconciled expense',
        ],
        'expected': expected,
        'source_hashes': hashes,
    }
    (destination / 'validation_manifest.json').write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + '\n', encoding='utf-8',
    )


def mutate_variant(source: Path, destination: Path, case: str) -> str:
    shutil.copytree(source, destination)
    manifest = destination / 'validation_manifest.json'
    manifest.unlink()
    if case == 'duplicate_transaction_id':
        path = destination / 'revenue_transactions.csv'
        rows = read_csv(path)
        rows.append(list(rows[1]))
        write_csv(path, rows)
        return 'duplicate_transaction_id'
    if case == 'positive_refund':
        path = destination / 'revenue_transactions.csv'
        rows = read_csv(path)
        header = rows[0]
        row = next(row for row in rows[1:] if row[header.index('transaction_type')] == 'Refund')
        row[header.index('amount')] = row[header.index('amount')].lstrip('-')
        write_csv(path, rows)
        return 'sign_convention'
    if case == 'mixed_currency':
        path = destination / 'monthly_account_summaries.csv'
        rows = read_csv(path)
        rows[1][rows[0].index('currency')] = 'EUR'
        write_csv(path, rows)
        return 'mixed_currency'
    if case == 'date_period_mismatch':
        path = destination / 'expense_transactions.csv'
        rows = read_csv(path)
        rows[1][rows[0].index('date')] = '2026-12-31'
        write_csv(path, rows)
        return 'invalid_date'
    if case == 'broken_accounting_identity':
        path = destination / 'monthly_account_summaries.csv'
        rows = read_csv(path)
        rows[1][rows[0].index('net_revenue')] = '1'
        write_csv(path, rows)
        return 'summary_equation'
    if case == 'unmapped_customer':
        path = destination / 'revenue_transactions.csv'
        rows = read_csv(path)
        rows[1][rows[0].index('customer_id')] = 'UNKNOWN-CUSTOMER'
        write_csv(path, rows)
        return 'unmapped_dimension'
    if case == 'fractional_dollars':
        path = destination / 'expense_transactions.csv'
        rows = read_csv(path)
        rows[1][rows[0].index('amount')] = '10.25'
        write_csv(path, rows)
        return 'non_integer_dollars'
    if case == 'duplicate_header':
        path = destination / 'revenue_transactions.csv'
        rows = read_csv(path)
        rows[0][-1] = rows[0][0]
        write_csv(path, rows)
        return 'duplicate_csv_header'
    raise ValueError(case)


def build(output_zip: Path) -> None:
    work = output_zip.parent / (output_zip.stem + '-contents')
    if work.exists():
        shutil.rmtree(work)
    valid = work / 'valid_hardened_package'
    copy_package(valid)
    add_new_activity_periods(valid)

    sys.path.insert(0, str(ROOT))
    from mandate.money_operations import analyze
    expected = {}
    for prior, current in (('2026-01', '2026-02'), ('2026-02', '2026-03'), ('2026-04', '2026-05')):
        result = analyze(valid, prior, current)
        revenue = next(item for item in result['variances'] if item['account_code'] == '4000')
        top3 = next(item for item in result['claims'] if item['id'] == 'claim-4000-top3-customers')
        expected[f'{prior}_to_{current}'] = {
            'revenue_change_minor': revenue['absolute_variance_minor'],
            'percentage_state': revenue['percentage_state'],
            'top3_customer_ids': top3['value_json']['customer_ids'],
            'top3_delta_minor': top3['value_json']['delta_minor'],
            'top3_share_bps': top3['value_json']['share_bps'],
        }
    write_manifest(valid, 'MANDATE-MONEY-OPS-HARDENED-V2', expected)

    rejected = {}
    (work / 'rejected_cases').mkdir(parents=True, exist_ok=True)
    for case in (
        'duplicate_transaction_id', 'positive_refund', 'mixed_currency', 'date_period_mismatch',
        'broken_accounting_identity', 'unmapped_customer', 'fractional_dollars', 'duplicate_header',
    ):
        rejected[case] = mutate_variant(valid, work / 'rejected_cases' / case, case)

    matrix = {
        'how_to_use': 'Upload every file inside one package directory together. The valid package must analyze; each rejected package must fail validation with its expected code.',
        'valid_package': 'valid_hardened_package',
        'valid_comparisons': list(expected),
        'rejected_cases': rejected,
    }
    (work / 'test_matrix.json').write_text(json.dumps(matrix, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    (work / 'README.txt').write_text(
        'Money Operations hardened test bundle\n\n'
        'Use valid_hardened_package for successful analysis. It retains the repository file names and schemas.\n'
        'Use each rejected_cases subdirectory separately to verify that validation fails closed.\n'
        'Expected outcomes are in test_matrix.json and the valid package validation_manifest.json.\n',
        encoding='utf-8',
    )
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    if output_zip.exists():
        output_zip.unlink()
    with zipfile.ZipFile(output_zip, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(work.rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(work))


if __name__ == '__main__':
    destination = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'outputs' / 'Mandate_Money_Operations_Hardened_Test_Bundle.zip'
    build(destination.resolve())
    print(destination.resolve())
