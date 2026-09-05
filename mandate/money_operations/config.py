"""Account configuration defaults and loader."""
from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

SCHEMA_VERSION = '1.0'
DEFAULT_CURRENCY = 'USD'
UNCLASSIFIED = 'Unclassified'

DEFAULT_CONFIG: dict = {
    'schema_version': SCHEMA_VERSION,
    'currency': DEFAULT_CURRENCY,
    'materiality': {
        'absolute_minor': 2_500_000,
        'percentage_bps': 500,
        'always_include_top_n': 5,
    },
    'driver_selection': {
        'minimum_contribution_minor': 1_000_000,
        'minimum_share_bps': 1000,
        'target_directional_coverage_bps': 8000,
        'maximum_drivers': 5,
    },
    'reconciliation_tolerance_minor': 1,
    'accounts': [
        {
            'account_code': '4000',
            'account_name': 'Revenue',
            'account_type': 'revenue',
            'summary_column': 'gross_revenue',
            'transaction_source': 'revenue',
            'transaction_types': ['Sale'],
            'analysis_dimensions': ['segment', 'customer_id', 'product', 'region', 'channel'],
        },
        {
            'account_code': '4100',
            'account_name': 'Refunds',
            'account_type': 'contra_revenue',
            'summary_column': 'refunds',
            'transaction_source': 'revenue',
            'transaction_types': ['Refund'],
            'natural_sign': 'positive',
            'analysis_dimensions': ['product', 'segment', 'customer_id', 'region', 'channel'],
        },
        {
            'account_code': '5000',
            'account_name': 'COGS',
            'account_type': 'expense',
            'summary_column': 'cogs',
            'transaction_source': 'expense',
            'expense_account': 'COGS',
            'analysis_dimensions': ['driver_category', 'vendor_id'],
        },
        {
            'account_code': '6200',
            'account_name': 'Software',
            'account_type': 'expense',
            'summary_column': 'software_expense',
            'transaction_source': 'expense',
            'expense_account': 'Software',
            'analysis_dimensions': ['driver_category', 'vendor_id'],
        },
        {
            'account_code': '6300',
            'account_name': 'Logistics',
            'account_type': 'expense',
            'summary_column': 'logistics_expense',
            'transaction_source': 'expense',
            'expense_account': 'Logistics',
            'analysis_dimensions': ['driver_category', 'vendor_id'],
        },
        {
            'account_code': '6400',
            'account_name': 'Payroll',
            'account_type': 'expense',
            'summary_column': 'payroll_expense',
            'transaction_source': 'expense',
            'expense_account': 'Payroll',
            'analysis_dimensions': ['driver_category', 'vendor_id'],
        },
        {
            'account_code': '6500',
            'account_name': 'Marketing',
            'account_type': 'expense',
            'summary_column': 'marketing_expense',
            'transaction_source': 'expense',
            'expense_account': 'Marketing',
            'analysis_dimensions': ['driver_category', 'vendor_id'],
        },
        {
            'account_code': '6900',
            'account_name': 'Other Opex',
            'account_type': 'expense',
            'summary_column': 'other_opex',
            'transaction_source': 'expense',
            'expense_account': 'Other Opex',
            'analysis_dimensions': ['driver_category', 'vendor_id'],
            'causal_unexplained_members': {
                'driver_category': ['Unexplained'],
                'vendor_id': ['V999'],
            },
        },
    ],
}

SKIP_SUMMARY_COLUMNS = frozenset({
    'net_revenue', 'gross_profit', 'total_opex', 'operating_profit', 'headcount',
})

ACCOUNT_COLUMNS = {
    account['summary_column']: account['account_code']
    for account in DEFAULT_CONFIG['accounts']
}

ACCOUNT_CODES = {
    account['account_code']: {
        'account_name': account['account_name'],
        'account_type': account['account_type'],
        'summary_column': account['summary_column'],
    }
    for account in DEFAULT_CONFIG['accounts']
}

EXPENSE_NAME_TO_CODE = {
    'COGS': '5000',
    'Software': '6200',
    'Logistics': '6300',
    'Payroll': '6400',
    'Marketing': '6500',
    'Other Opex': '6900',
}

CONTEXT_ACCOUNT_TO_CODE = {
    'Revenue': '4000',
    'Refunds': '4100',
    'COGS': '5000',
    'Software': '6200',
    'Logistics': '6300',
    'Payroll': '6400',
    'Marketing': '6500',
    'Other Opex': '6900',
}

REQUIRED_SUMMARY_COLUMNS = (
    'period', 'period_end', 'gross_revenue', 'refunds', 'net_revenue', 'cogs',
    'gross_profit', 'software_expense', 'logistics_expense', 'payroll_expense',
    'marketing_expense', 'other_opex', 'total_opex', 'operating_profit',
    'headcount', 'currency', 'source_system',
)

REQUIRED_REVENUE_COLUMNS = (
    'transaction_id', 'date', 'period', 'customer_id', 'customer_name', 'segment',
    'product', 'channel', 'region', 'transaction_type', 'amount', 'source_system',
    'invoice_id',
)

REQUIRED_EXPENSE_COLUMNS = (
    'transaction_id', 'date', 'period', 'account', 'vendor_id', 'vendor_name',
    'driver_category', 'amount', 'headcount_effect', 'source_system', 'invoice_id',
    'description',
)

PACKAGE_FILES = (
    'monthly_account_summaries.csv',
    'revenue_transactions.csv',
    'expense_transactions.csv',
    'customer_dimension.csv',
    'product_dimension.csv',
    'channel_dimension.csv',
    'region_dimension.csv',
    'vendor_dimension.csv',
    'data_dictionary.csv',
    'business_context_history.json',
    'expected_driver_answers.json',
    'validation_manifest.json',
    'account_configuration.json',
)

CORE_FILES = (
    'monthly_account_summaries.csv',
    'revenue_transactions.csv',
    'expense_transactions.csv',
)

REVENUE_DIMENSIONS = ('segment', 'customer_id', 'product', 'region', 'channel')
EXPENSE_DIMENSIONS = ('driver_category', 'vendor_id')
LABEL_FIELDS = {
    'customer_id': 'customer_name',
    'vendor_id': 'vendor_name',
}

ACCOUNT_CODE_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,31}$')
SAFE_FIELD_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_]{0,63}$')
ACCOUNT_TYPES = frozenset({'revenue', 'contra_revenue', 'expense'})
TRANSACTION_SOURCES = frozenset({'revenue', 'expense'})
ALLOWED_DIMENSIONS = frozenset((*REVENUE_DIMENSIONS, *EXPENSE_DIMENSIONS))


def _bounded_int(value, name: str, *, minimum: int = 0, maximum: int = 10**12) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name} must be an integer from {minimum} to {maximum}')
    return value


def _validate_config(config: dict) -> dict:
    if config.get('schema_version') != SCHEMA_VERSION:
        raise ValueError(f'unsupported account configuration schema_version: {config.get("schema_version")!r}')
    currency = config.get('currency')
    if not isinstance(currency, str) or not re.fullmatch(r'[A-Z]{3}', currency):
        raise ValueError('account configuration currency must be a three-letter uppercase code')
    _bounded_int(config.get('reconciliation_tolerance_minor'), 'reconciliation_tolerance_minor', maximum=100_000_000)
    for section in ('materiality', 'driver_selection'):
        if not isinstance(config.get(section), dict):
            raise ValueError(f'{section} must be an object')
        for key, value in config[section].items():
            _bounded_int(value, f'{section}.{key}', maximum=10**12)
    accounts = config.get('accounts')
    if not isinstance(accounts, list) or not accounts or len(accounts) > 100:
        raise ValueError('accounts must be a non-empty list with at most 100 entries')
    seen: set[str] = set()
    for index, account in enumerate(accounts):
        if not isinstance(account, dict):
            raise ValueError(f'accounts[{index}] must be an object')
        code = account.get('account_code')
        if not isinstance(code, str) or not ACCOUNT_CODE_RE.fullmatch(code):
            raise ValueError(f'accounts[{index}].account_code is invalid')
        if code in seen:
            raise ValueError(f'duplicate account_code: {code}')
        seen.add(code)
        name = account.get('account_name')
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise ValueError(f'accounts[{index}].account_name is invalid')
        account_type = account.get('account_type')
        source = account.get('transaction_source')
        if account_type not in ACCOUNT_TYPES or source not in TRANSACTION_SOURCES:
            raise ValueError(f'accounts[{index}] has an unsupported account type or transaction source')
        summary_column = account.get('summary_column')
        if not isinstance(summary_column, str) or not SAFE_FIELD_RE.fullmatch(summary_column):
            raise ValueError(f'accounts[{index}].summary_column is invalid')
        dimensions = account.get('analysis_dimensions')
        if (
            not isinstance(dimensions, list)
            or not dimensions
            or len(dimensions) != len(set(dimensions))
            or any(item not in ALLOWED_DIMENSIONS for item in dimensions)
        ):
            raise ValueError(f'accounts[{index}].analysis_dimensions is invalid')
        if source == 'revenue':
            types = account.get('transaction_types')
            if not isinstance(types, list) or not types or any(item not in {'Sale', 'Refund'} for item in types):
                raise ValueError(f'accounts[{index}].transaction_types is invalid')
        elif not isinstance(account.get('expense_account'), str) or not account['expense_account'].strip():
            raise ValueError(f'accounts[{index}].expense_account is required')
    return config


def default_config() -> dict:
    return deepcopy(DEFAULT_CONFIG)


def load_config(path: str | Path | None) -> dict:
    if path is None:
        return default_config()
    config_path = Path(path)
    if not config_path.is_file():
        return default_config()
    payload = json.loads(config_path.read_text(encoding='utf-8'))
    config = default_config()
    if isinstance(payload, dict):
        for key in ('schema_version', 'currency', 'reconciliation_tolerance_minor'):
            if key in payload:
                config[key] = payload[key]
        for key in ('materiality', 'driver_selection'):
            if isinstance(payload.get(key), dict):
                config[key].update(payload[key])
        if isinstance(payload.get('accounts'), list) and payload['accounts']:
            config['accounts'] = payload['accounts']
    return _validate_config(config)


def account_by_code(config: dict, account_code: str) -> dict:
    for account in config['accounts']:
        if account['account_code'] == account_code:
            return account
    raise KeyError(account_code)
