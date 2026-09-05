"""Dataset validation and integer-minor-unit ingestion."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .config import (
    CONTEXT_ACCOUNT_TO_CODE,
    CORE_FILES,
    EXPENSE_NAME_TO_CODE,
    PACKAGE_FILES,
    REQUIRED_EXPENSE_COLUMNS,
    REQUIRED_REVENUE_COLUMNS,
    REQUIRED_SUMMARY_COLUMNS,
    SCHEMA_VERSION,
    UNCLASSIFIED,
    default_config,
    load_config,
)
from .integer import DATE_RE, PERIOD_RE, MoneyParseError, parse_int, parse_whole_dollars_to_minor


class DatasetValidationError(ValueError):
    """Dataset failed closed validation and must not be analyzed."""

    def __init__(self, message: str, findings: list[dict] | None = None):
        super().__init__(message)
        self.findings = findings or []


def _finding(code: str, severity: str, message: str, source_id: str | None = None,
             details: dict | None = None) -> dict:
    item = {'code': code, 'severity': severity, 'message': message}
    if source_id:
        item['source_id'] = source_id
    if details:
        item['details'] = details
    return item


def _source_id(file_name: str) -> str:
    return f'src-{Path(file_name).stem}'


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _member(value: str | None) -> str:
    text = '' if value is None else str(value).strip()
    return text if text else UNCLASSIFIED


def _read_csv_bytes(path: Path) -> tuple[bytes, list[dict], list[str]]:
    data = path.read_bytes()
    text = data.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text, newline=''), strict=True)
    fieldnames = list(reader.fieldnames or [])
    rows = [{k: (v if v is not None else '') for k, v in row.items()} for row in reader]
    return data, rows, fieldnames


def _missing_columns(fieldnames: list[str], required: tuple[str, ...]) -> list[str]:
    present = {name.strip() for name in fieldnames}
    return [name for name in required if name not in present]


def _duplicate_columns(fieldnames: list[str]) -> list[str]:
    return sorted({name for name in fieldnames if fieldnames.count(name) > 1})


def _unexpected_columns(fieldnames: list[str], required: tuple[str, ...]) -> list[str]:
    allowed = set(required)
    return sorted(name for name in fieldnames if name not in allowed)


def _valid_period(value: str) -> bool:
    if not PERIOD_RE.fullmatch(value):
        return False
    try:
        year, month = map(int, value.split('-'))
        date(year, month, 1)
    except ValueError:
        return False
    return True


def _valid_date_in_period(value: str, period: str) -> bool:
    if not DATE_RE.fullmatch(value) or not _valid_period(period):
        return False
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return False
    return parsed.strftime('%Y-%m') == period


def _load_dimension_ids(path: Path, key: str, dataset) -> set[str]:
    if not path.is_file():
        return set()
    try:
        _, rows, fieldnames = _read_csv_bytes(path)
    except (UnicodeDecodeError, csv.Error, OSError) as exc:
        dataset.findings.append(_finding(
            'invalid_encoding' if isinstance(exc, UnicodeDecodeError) else 'invalid_csv',
            'error', f'could not parse {path.name}', source_id=_source_id(path.name),
        ))
        return set()
    if key not in fieldnames:
        dataset.findings.append(_finding(
            'invalid_schema', 'error', f'{path.name} missing key column {key}',
            source_id=_source_id(path.name),
        ))
        return set()
    duplicates = _duplicate_columns(fieldnames)
    if duplicates:
        dataset.findings.append(_finding(
            'duplicate_csv_header', 'error', f'{path.name} contains duplicate columns: {duplicates}',
            source_id=_source_id(path.name),
        ))
    values: set[str] = set()
    for index, row in enumerate(rows, start=2):
        value = _member(row.get(key))
        if value == UNCLASSIFIED:
            continue
        if value in values:
            dataset.findings.append(_finding(
                'duplicate_dimension_key', 'error', f'{path.name} contains duplicate {key} {value}',
                source_id=_source_id(path.name), details={'row': index, key: value},
            ))
        values.add(value)
    return values


@dataclass
class LoadedDataset:
    root: Path
    config: dict
    sources: list[dict] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    available_periods: list[str] = field(default_factory=list)
    summaries: dict[str, dict] = field(default_factory=dict)
    transactions: list[dict] = field(default_factory=list)
    context_entries: list[dict] = field(default_factory=list)
    manifest: dict | None = None
    synthetic: bool = False

    @property
    def error_findings(self) -> list[dict]:
        return [item for item in self.findings if item.get('severity') == 'error']

    @property
    def valid(self) -> bool:
        return not self.error_findings

    def transactions_for(self, account_code: str, period: str) -> list[dict]:
        return [
            txn for txn in self.transactions
            if txn['account_code'] == account_code and txn['period'] == period
        ]


def load_dataset(path: str | Path, *, enforce_manifest_hashes: bool = True) -> LoadedDataset:
    root = Path(path).resolve()
    config_error = None
    try:
        config = load_config(root / 'account_configuration.json')
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        config = default_config()
        config_error = type(exc).__name__
    dataset = LoadedDataset(root=root, config=config)
    if config_error:
        dataset.findings.append(_finding(
            'invalid_account_configuration', 'error',
            'account_configuration.json failed strict validation',
            source_id=_source_id('account_configuration.json'),
            details={'reason': config_error},
        ))
    if not root.is_dir():
        dataset.findings.append(_finding(
            'missing_file', 'error', f'dataset path is not a directory: {root}',
        ))
        return dataset

    manifest_path = root / 'validation_manifest.json'
    if manifest_path.is_file():
        try:
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            if not isinstance(manifest, dict):
                raise ValueError('manifest must be an object')
            dataset.manifest = manifest
            dataset.synthetic = manifest.get('synthetic') is True
            if dataset.synthetic:
                dataset.findings.append(_finding(
                    'synthetic_dataset',
                    'info',
                    'Dataset is labeled synthetic and is safe only for demonstration.',
                    source_id=_source_id('validation_manifest.json'),
                    details={'dataset_id': manifest.get('dataset_id')},
                ))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            dataset.findings.append(_finding(
                'invalid_manifest', 'error', 'validation_manifest.json is invalid',
                source_id=_source_id('validation_manifest.json'),
                details={'reason': type(exc).__name__},
            ))

    expected_hashes = (dataset.manifest or {}).get('source_hashes') or {}
    currencies: set[str] = set()
    transaction_ids: dict[str, str] = {}
    customer_ids = _load_dimension_ids(root / 'customer_dimension.csv', 'customer_id', dataset)
    vendor_ids = _load_dimension_ids(root / 'vendor_dimension.csv', 'vendor_id', dataset)

    for file_name in PACKAGE_FILES:
        file_path = root / file_name
        if file_name in CORE_FILES and not file_path.is_file():
            dataset.findings.append(_finding(
                'missing_file', 'error', f'required file is missing: {file_name}',
                source_id=_source_id(file_name),
            ))
            continue
        if not file_path.is_file():
            continue
        raw = file_path.read_bytes()
        digest = _sha256_bytes(raw)
        if enforce_manifest_hashes and file_name in expected_hashes and expected_hashes[file_name] != digest:
            dataset.findings.append(_finding(
                'hash_mismatch',
                'error',
                f'SHA-256 does not match validation_manifest.json for {file_name}',
                source_id=_source_id(file_name),
                details={'expected': expected_hashes[file_name], 'actual': digest},
            ))
        source = {
            'source_id': _source_id(file_name),
            'file_name': file_name,
            'sha256': digest,
            'byte_size': len(raw),
            'row_count': 0,
            'schema_version': SCHEMA_VERSION,
            'periods': [],
            'synthetic': dataset.synthetic,
        }
        if file_name.endswith('.csv'):
            try:
                _, rows, fieldnames = _read_csv_bytes(file_path)
            except (UnicodeDecodeError, csv.Error, OSError) as exc:
                dataset.findings.append(_finding(
                    'invalid_encoding' if isinstance(exc, UnicodeDecodeError) else 'invalid_csv',
                    'error', f'could not parse {file_name}', source_id=source['source_id'],
                    details={'reason': type(exc).__name__},
                ))
                dataset.sources.append(source)
                continue
            source['row_count'] = len(rows)
            duplicates = _duplicate_columns(fieldnames)
            if duplicates:
                dataset.findings.append(_finding(
                    'duplicate_csv_header', 'error',
                    f'{file_name} contains duplicate columns: {duplicates}',
                    source_id=source['source_id'],
                ))
                dataset.sources.append(source)
                continue
            if any(None in row for row in rows):
                dataset.findings.append(_finding(
                    'invalid_csv', 'error', f'{file_name} contains rows wider than its header',
                    source_id=source['source_id'],
                ))
                dataset.sources.append(source)
                continue
            if file_name == 'monthly_account_summaries.csv':
                _ingest_summaries(dataset, source, rows, fieldnames, currencies)
            elif file_name == 'revenue_transactions.csv':
                _ingest_revenue(dataset, source, rows, fieldnames, transaction_ids, customer_ids)
            elif file_name == 'expense_transactions.csv':
                _ingest_expenses(dataset, source, rows, fieldnames, transaction_ids, vendor_ids)
            elif 'period' in fieldnames:
                source['periods'] = sorted({row.get('period', '') for row in rows if row.get('period')})
        elif file_name == 'business_context_history.json':
            _ingest_context(dataset, source, raw)
        dataset.sources.append(source)

    if len(currencies) > 1:
        dataset.findings.append(_finding(
            'mixed_currency', 'error',
            f'dataset contains mixed currencies: {sorted(currencies)}',
        ))
    unsupported = {code for code in currencies if code != dataset.config.get('currency', 'USD')}
    if unsupported:
        dataset.findings.append(_finding(
            'unsupported_currency', 'error',
            f'unsupported currencies: {sorted(unsupported)}',
        ))

    dataset.available_periods = sorted(dataset.summaries)
    dataset.sources.sort(key=lambda item: item['file_name'])
    return dataset


def _ingest_summaries(dataset: LoadedDataset, source: dict, rows: list[dict],
                      fieldnames: list[str], currencies: set[str]) -> None:
    missing = _missing_columns(fieldnames, REQUIRED_SUMMARY_COLUMNS)
    if missing:
        dataset.findings.append(_finding(
            'invalid_schema', 'error',
            f'monthly_account_summaries.csv missing columns: {missing}',
            source_id=source['source_id'],
        ))
        return
    extra = _unexpected_columns(fieldnames, REQUIRED_SUMMARY_COLUMNS)
    if extra:
        dataset.findings.append(_finding(
            'unexpected_column', 'error',
            f'monthly_account_summaries.csv contains unexpected columns: {extra}',
            source_id=source['source_id'],
        ))
        return
    periods: list[str] = []
    money_fields = [
        name for name in REQUIRED_SUMMARY_COLUMNS
        if name not in {'period', 'period_end', 'headcount', 'currency', 'source_system'}
    ]
    for index, row in enumerate(rows, start=2):
        period = (row.get('period') or '').strip()
        if not _valid_period(period):
            dataset.findings.append(_finding(
                'invalid_period', 'error', f'invalid summary period at row {index}',
                source_id=source['source_id'], details={'row': index, 'period': period},
            ))
            continue
        period_end = (row.get('period_end') or '').strip()
        if not _valid_date_in_period(period_end, period):
            dataset.findings.append(_finding(
                'invalid_date', 'error', f'summary period_end does not fall in period at row {index}',
                source_id=source['source_id'], details={'row': index},
            ))
        if period in dataset.summaries:
            dataset.findings.append(_finding(
                'duplicate_summary_period', 'error',
                f'duplicate summary period {period}',
                source_id=source['source_id'], details={'period': period},
            ))
            continue
        currency = (row.get('currency') or '').strip()
        currencies.add(currency)
        amounts: dict[str, int] = {}
        try:
            for field_name in money_fields:
                amounts[field_name] = parse_whole_dollars_to_minor(row[field_name], field=field_name)
            headcount = parse_int(row.get('headcount', ''), field='headcount')
        except MoneyParseError as exc:
            dataset.findings.append(_finding(
                'non_integer_dollars', 'error', str(exc),
                source_id=source['source_id'], details={'row': index, 'period': period},
            ))
            continue
        equations = {
            'net_revenue': amounts['gross_revenue'] - amounts['refunds'],
            'gross_profit': amounts['net_revenue'] - amounts['cogs'],
            'total_opex': sum(amounts[name] for name in (
                'software_expense', 'logistics_expense', 'payroll_expense',
                'marketing_expense', 'other_opex',
            )),
            'operating_profit': amounts['gross_profit'] - amounts['total_opex'],
        }
        for field_name, calculated in equations.items():
            if amounts[field_name] != calculated:
                dataset.findings.append(_finding(
                    'summary_equation', 'error',
                    f'{field_name} does not satisfy its accounting identity at row {index}',
                    source_id=source['source_id'],
                    details={
                        'row': index,
                        'period': period,
                        'field': field_name,
                        'reported_minor': amounts[field_name],
                        'calculated_minor': calculated,
                        'difference_minor': amounts[field_name] - calculated,
                    },
                ))
        dataset.summaries[period] = {
            'period': period,
            'period_end': period_end,
            'currency': currency,
            'source_system': row.get('source_system', ''),
            'headcount': headcount,
            'amounts_minor': amounts,
            'source_id': source['source_id'],
            'source_row_number': index,
        }
        periods.append(period)
    source['periods'] = sorted(set(periods))


def _ingest_revenue(dataset: LoadedDataset, source: dict, rows: list[dict],
                    fieldnames: list[str], transaction_ids: dict[str, str],
                    customer_ids: set[str]) -> None:
    missing = _missing_columns(fieldnames, REQUIRED_REVENUE_COLUMNS)
    if missing:
        dataset.findings.append(_finding(
            'invalid_schema', 'error',
            f'revenue_transactions.csv missing columns: {missing}',
            source_id=source['source_id'],
        ))
        return
    extra = _unexpected_columns(fieldnames, REQUIRED_REVENUE_COLUMNS)
    if extra:
        dataset.findings.append(_finding(
            'unexpected_column', 'error',
            f'revenue_transactions.csv contains unexpected columns: {extra}',
            source_id=source['source_id'],
        ))
        return
    periods: list[str] = []
    for index, row in enumerate(rows, start=2):
        txn_id = (row.get('transaction_id') or '').strip()
        if not txn_id:
            dataset.findings.append(_finding(
                'invalid_schema', 'error', f'missing transaction_id at row {index}',
                source_id=source['source_id'],
            ))
            continue
        if txn_id in transaction_ids:
            dataset.findings.append(_finding(
                'duplicate_transaction_id', 'error',
                f'duplicate transaction_id {txn_id}',
                source_id=source['source_id'],
                details={'transaction_id': txn_id, 'first_source': transaction_ids[txn_id]},
            ))
            continue
        transaction_ids[txn_id] = source['source_id']
        period = (row.get('period') or '').strip()
        posted = (row.get('date') or '').strip()
        if not _valid_date_in_period(posted, period):
            dataset.findings.append(_finding(
                'invalid_date', 'error', f'revenue date/period mismatch at row {index}',
                source_id=source['source_id'], details={'transaction_id': txn_id},
            ))
            continue
        invoice_id = (row.get('invoice_id') or '').strip()
        if not invoice_id:
            dataset.findings.append(_finding(
                'invalid_schema', 'error', f'missing invoice_id at row {index}',
                source_id=source['source_id'], details={'transaction_id': txn_id},
            ))
            continue
        txn_type = (row.get('transaction_type') or '').strip()
        if txn_type not in {'Sale', 'Refund'}:
            dataset.findings.append(_finding(
                'invalid_schema', 'error', f'unsupported transaction_type {txn_type!r}',
                source_id=source['source_id'], details={'transaction_id': txn_id},
            ))
            continue
        try:
            signed_minor = parse_whole_dollars_to_minor(row.get('amount', ''), field='amount')
        except MoneyParseError as exc:
            dataset.findings.append(_finding(
                'non_integer_dollars', 'error', str(exc),
                source_id=source['source_id'], details={'transaction_id': txn_id},
            ))
            continue
        if txn_type == 'Sale' and signed_minor < 0:
            dataset.findings.append(_finding(
                'sign_convention', 'error', f'sale amount must be non-negative: {txn_id}',
                source_id=source['source_id'],
            ))
            continue
        if txn_type == 'Refund' and signed_minor > 0:
            dataset.findings.append(_finding(
                'sign_convention', 'error', f'refund amount must be non-positive: {txn_id}',
                source_id=source['source_id'],
            ))
            continue
        customer_id = _member(row.get('customer_id'))
        if customer_ids and customer_id != UNCLASSIFIED and customer_id not in customer_ids:
            dataset.findings.append(_finding(
                'unmapped_dimension', 'error',
                f'customer_id {customer_id} is not in customer_dimension.csv',
                source_id=source['source_id'], details={'transaction_id': txn_id},
            ))
        account_code = '4000' if txn_type == 'Sale' else '4100'
        amount_minor = signed_minor if txn_type == 'Sale' else -signed_minor
        dimensions = {
            'segment': _member(row.get('segment')),
            'customer_id': customer_id,
            'customer_name': (row.get('customer_name') or '').strip() or UNCLASSIFIED,
            'product': _member(row.get('product')),
            'channel': _member(row.get('channel')),
            'region': _member(row.get('region')),
        }
        dataset.transactions.append({
            'transaction_id': txn_id,
            'date': posted,
            'period': period,
            'account_code': account_code,
            'amount_minor': amount_minor,
            'signed_source_minor': signed_minor,
            'currency': dataset.config.get('currency', 'USD'),
            'source_id': source['source_id'],
            'source_row_number': index,
            'invoice_id': invoice_id,
            'transaction_type': txn_type,
            'dimensions': dimensions,
            'headcount_effect': 0,
        })
        periods.append(period)
    source['periods'] = sorted(set(periods))


def _ingest_expenses(dataset: LoadedDataset, source: dict, rows: list[dict],
                     fieldnames: list[str], transaction_ids: dict[str, str],
                     vendor_ids: set[str]) -> None:
    missing = _missing_columns(fieldnames, REQUIRED_EXPENSE_COLUMNS)
    if missing:
        dataset.findings.append(_finding(
            'invalid_schema', 'error',
            f'expense_transactions.csv missing columns: {missing}',
            source_id=source['source_id'],
        ))
        return
    extra = _unexpected_columns(fieldnames, REQUIRED_EXPENSE_COLUMNS)
    if extra:
        dataset.findings.append(_finding(
            'unexpected_column', 'error',
            f'expense_transactions.csv contains unexpected columns: {extra}',
            source_id=source['source_id'],
        ))
        return
    periods: list[str] = []
    for index, row in enumerate(rows, start=2):
        txn_id = (row.get('transaction_id') or '').strip()
        if not txn_id:
            dataset.findings.append(_finding(
                'invalid_schema', 'error', f'missing transaction_id at row {index}',
                source_id=source['source_id'],
            ))
            continue
        if txn_id in transaction_ids:
            dataset.findings.append(_finding(
                'duplicate_transaction_id', 'error',
                f'duplicate transaction_id {txn_id}',
                source_id=source['source_id'],
                details={'transaction_id': txn_id, 'first_source': transaction_ids[txn_id]},
            ))
            continue
        transaction_ids[txn_id] = source['source_id']
        period = (row.get('period') or '').strip()
        posted = (row.get('date') or '').strip()
        if not _valid_date_in_period(posted, period):
            dataset.findings.append(_finding(
                'invalid_date', 'error', f'expense date/period mismatch at row {index}',
                source_id=source['source_id'], details={'transaction_id': txn_id},
            ))
            continue
        invoice_id = (row.get('invoice_id') or '').strip()
        if not invoice_id:
            dataset.findings.append(_finding(
                'invalid_schema', 'error', f'missing invoice_id at row {index}',
                source_id=source['source_id'], details={'transaction_id': txn_id},
            ))
            continue
        account_name = (row.get('account') or '').strip()
        account_code = EXPENSE_NAME_TO_CODE.get(account_name)
        if account_code is None:
            dataset.findings.append(_finding(
                'invalid_schema', 'error', f'unsupported expense account {account_name!r}',
                source_id=source['source_id'], details={'transaction_id': txn_id},
            ))
            continue
        try:
            amount_minor = parse_whole_dollars_to_minor(row.get('amount', ''), field='amount')
            headcount_effect = parse_int(row.get('headcount_effect', '0'), field='headcount_effect')
        except MoneyParseError as exc:
            dataset.findings.append(_finding(
                'non_integer_dollars', 'error', str(exc),
                source_id=source['source_id'], details={'transaction_id': txn_id},
            ))
            continue
        if amount_minor < 0:
            dataset.findings.append(_finding(
                'sign_convention', 'error', f'expense amount must be non-negative: {txn_id}',
                source_id=source['source_id'],
            ))
            continue
        vendor_id = _member(row.get('vendor_id'))
        if vendor_ids and vendor_id != UNCLASSIFIED and vendor_id not in vendor_ids:
            dataset.findings.append(_finding(
                'unmapped_dimension', 'error',
                f'vendor_id {vendor_id} is not in vendor_dimension.csv',
                source_id=source['source_id'], details={'transaction_id': txn_id},
            ))
        dimensions = {
            'driver_category': _member(row.get('driver_category')),
            'vendor_id': vendor_id,
            'vendor_name': (row.get('vendor_name') or '').strip() or UNCLASSIFIED,
        }
        dataset.transactions.append({
            'transaction_id': txn_id,
            'date': posted,
            'period': period,
            'account_code': account_code,
            'amount_minor': amount_minor,
            'signed_source_minor': amount_minor,
            'currency': dataset.config.get('currency', 'USD'),
            'source_id': source['source_id'],
            'source_row_number': index,
            'invoice_id': invoice_id,
            'transaction_type': 'Expense',
            'dimensions': dimensions,
            'headcount_effect': headcount_effect,
            'description': row.get('description', ''),
        })
        periods.append(period)
    source['periods'] = sorted(set(periods))


def _ingest_context(dataset: LoadedDataset, source: dict, raw: bytes) -> None:
    try:
        payload = json.loads(raw.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        dataset.findings.append(_finding(
            'invalid_schema', 'error', 'business_context_history.json is not valid JSON',
            source_id=source['source_id'],
        ))
        return
    entries = payload.get('entries') if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return
    periods: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        account_name = str(entry.get('account') or '')
        dataset.context_entries.append({
            'context_id': entry.get('context_id'),
            'account_code': CONTEXT_ACCOUNT_TO_CODE.get(account_name),
            'account': account_name,
            'statement': entry.get('statement', ''),
            'seed_status': entry.get('status'),
            'status': 'context_suggested',
            'confirmed_by': entry.get('confirmed_by'),
            'effective_period': entry.get('effective_period'),
            'revision': entry.get('revision'),
            'supersedes': entry.get('supersedes'),
            'source_run_id': entry.get('source_run_id'),
        })
        if entry.get('effective_period'):
            periods.append(str(entry['effective_period']))
    source['row_count'] = len(dataset.context_entries)
    source['periods'] = sorted(set(periods))
