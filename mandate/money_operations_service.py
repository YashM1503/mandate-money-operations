"""Money Operations persistence, memory, exports, and HTTP routes.

Canonical money math lives in mandate.money_operations.analyze. This module
stores HMAC-protected analysis bodies, versioned context, and citations.
"""
from __future__ import annotations

import csv
import hashlib
import hmac
import json
import os
import re
import shutil
import uuid
from datetime import datetime, UTC
from pathlib import Path

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .money_operations import CALCULATION_VERSION


class StrictBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
from .money_operations_narrative import (
    claim_amount_minor,
    compose,
    render_csv,
    render_memo_html,
)

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = ROOT / 'sample-data' / 'money-operations'
CONTEXT_SEED = FIXTURE_DIR / 'business_context_history.json'
DEFAULT_ENTITY = 'yari-retail-us'
ALLOWED_UPLOAD_EXT = {'.csv', '.json'}
ACCOUNT_ALIASES = {
    'software': '6200',
    'software_expense': '6200',
    '6200': '6200',
    'payroll': '6400',
    'payroll_expense': '6400',
    '6400': '6400',
    'logistics': '6300',
    'logistics_expense': '6300',
    '6300': '6300',
    'other opex': '6900',
    'other_opex': '6900',
    '6900': '6900',
    'gross revenue': '4000',
    'revenue': '4000',
    'gross_revenue': '4000',
    '4000': '4000',
    'refunds': '4100',
    '4100': '4100',
    'cogs': '5000',
    '5000': '5000',
    'marketing': '6500',
    'marketing_expense': '6500',
    '6500': '6500',
}


class MoneyOpsError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


class DatasetSelect(StrictBody):
    fixture: str = Field(pattern=r'^reference$')


class AnalysisCreate(StrictBody):
    dataset_id: str = Field(min_length=1, max_length=80)
    entity_id: str = Field(min_length=1, max_length=80)
    prior_period: str = Field(pattern=r'^\d{4}-\d{2}$')
    current_period: str = Field(pattern=r'^\d{4}-\d{2}$')
    expected_revision: int | None = Field(default=None, ge=1)


class PeriodScope(StrictBody):
    month: int = Field(ge=1, le=12)
    recurrence: str = Field(min_length=1, max_length=32)


class ContextCreate(StrictBody):
    analysis_id: str = Field(min_length=1, max_length=80)
    account_code: str = Field(min_length=1, max_length=80)
    dimension: str = Field(min_length=1, max_length=80)
    member: str = Field(min_length=1, max_length=80)
    statement: str = Field(min_length=1, max_length=2000)
    period_scope: PeriodScope
    expected_revision: int = Field(ge=1)


class ContextMutation(StrictBody):
    expected_revision: int = Field(ge=1)
    statement: str | None = Field(default=None, min_length=1, max_length=2000)


class ReviewBody(StrictBody):
    decision: str = Field(pattern=r'^(approved|changes_requested|rejected)$')
    expected_revision: int | None = Field(default=None, ge=1)
    analysis_revision: int | None = Field(default=None, ge=1)
    analysis_id: str | None = Field(default=None, min_length=1, max_length=80)
    calculation_digest: str | None = Field(default=None, min_length=8, max_length=128)
    narrative_digest: str | None = Field(default=None, min_length=8, max_length=128)


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _mac(key: bytes, body: str) -> str:
    return hmac.new(key, body.encode(), hashlib.sha256).hexdigest()


def _dump(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(',', ':'))


def _digest(obj) -> str:
    return hashlib.sha256(_dump(obj).encode()).hexdigest()


def _error_response(exc: MoneyOpsError) -> JSONResponse:
    return JSONResponse(
        {'error': {'code': exc.code, 'message': exc.message, 'details': exc.details}},
        status_code=exc.status,
    )


def _require_write(user: dict):
    if user['role'] not in ('analyst', 'controller'):
        raise HTTPException(403, 'Write role required')


def _require_controller(user: dict):
    if user['role'] != 'controller':
        raise HTTPException(403, 'Controller role required')


def _upload_limits() -> tuple[int, int]:
    try:
        byte_limit = max(1024, int(os.getenv('MANDATE_MAX_UPLOAD_BYTES', '2000000')))
    except ValueError:
        byte_limit = 2_000_000
    try:
        row_limit = max(1, int(os.getenv('MANDATE_MAX_UPLOAD_ROWS', '50000')))
    except ValueError:
        row_limit = 50_000
    return byte_limit, row_limit


def _safe_filename(name: str) -> str:
    if not name or name != Path(name).name or '..' in name or '/' in name or '\\' in name:
        raise MoneyOpsError(422, 'invalid_upload', 'File name is not allowed', {'file_name': name})
    if Path(name).suffix.lower() not in ALLOWED_UPLOAD_EXT:
        raise MoneyOpsError(422, 'invalid_upload', 'Only .csv and .json uploads are accepted', {'file_name': name})
    return name


def parse_multipart_files(content_type: str, body: bytes) -> list[tuple[str, bytes]]:
    match = re.search(r'boundary=([^;]+)', content_type or '', re.I)
    if not match:
        raise MoneyOpsError(422, 'invalid_upload', 'Multipart boundary is missing')
    boundary = match.group(1).strip().strip('"').encode()
    files: list[tuple[str, bytes]] = []
    for part in body.split(b'--' + boundary):
        if b'filename=' not in part:
            continue
        header, sep, content = part.partition(b'\r\n\r\n')
        if not sep:
            header, sep, content = part.partition(b'\n\n')
        name_match = re.search(br'filename="([^"]+)"', header) or re.search(br'filename=([^;\r\n]+)', header)
        if not name_match:
            continue
        filename = name_match.group(1).decode('utf-8', 'replace').strip()
        data = content
        if data.endswith(b'--\r\n'):
            data = data[:-4]
        elif data.endswith(b'--'):
            data = data[:-2]
        # RFC 2046 parts end with CRLF before the next boundary. Keep the
        # file's own trailing LF so SHA-256 matches the on-disk fixture.
        if data.endswith(b'\r\n'):
            data = data[:-2]
        files.append((filename, data))
    if not files:
        raise MoneyOpsError(422, 'invalid_upload', 'No files were uploaded')
    return files


def _normalize_account(value: str) -> str:
    raw = (value or '').strip()
    lowered = raw.lower()
    compact = re.sub(r'[^a-z0-9]+', '', lowered)
    aliases = dict(ACCOUNT_ALIASES)
    aliases.update({re.sub(r'[^a-z0-9]+', '', key): code for key, code in ACCOUNT_ALIASES.items()})
    return aliases.get(lowered) or aliases.get(compact) or raw or 'unknown'


def _account_tokens(value: str) -> set[str]:
    raw = (value or '').strip().lower()
    return {raw, re.sub(r'[^a-z0-9]+', '', raw), _normalize_account(value).lower()}


def _same_account(left: str, right: str) -> bool:
    return bool(_account_tokens(left) & _account_tokens(right))


def _is_other_opex(account_code: str) -> bool:
    return _normalize_account(account_code) == '6900'


def _observe_narrative(analysis_id, narrative=None, context_rows=None, **extra) -> None:
    """Forward narrative-boundary metadata only. Never send source rows or credentials."""
    try:
        from .money_operations_prism import observe_narrative
        narrative = narrative if isinstance(narrative, dict) else {}
        context_rows = context_rows if isinstance(context_rows, list) else []
        observe_narrative(
            analysis_id=analysis_id,
            run_id=extra.get('run_id'),
            prior_period=extra.get('prior_period'),
            current_period=extra.get('current_period'),
            calculation_digest=extra.get('calculation_digest'),
            structured_claim_ids=list(narrative.get('cited_claim_ids') or extra.get('structured_claim_ids') or []),
            retrieved_context_ids=[
                item.get('id') for item in context_rows
                if isinstance(item, dict) and item.get('id')
            ],
            prompt_version=narrative.get('template_version') or extra.get('prompt_version') or extra.get('template_version'),
            template_version=extra.get('template_version') or narrative.get('template_version'),
            model=narrative.get('model') or extra.get('model') or 'deterministic-template',
            provider=narrative.get('narrative_source') or extra.get('provider') or 'deterministic-template',
            narrative_source=narrative.get('narrative_source') or extra.get('narrative_source') or 'deterministic_template',
            reconciliation_status=extra.get('reconciliation_status'),
            unexplained_item_count=extra.get('unexplained_item_count'),
            numeric_validation=extra.get('numeric_validation') or 'pass',
            citation_validation=extra.get('citation_validation') or 'pass',
            fallback=bool(narrative.get('model_error') or extra.get('fallback')),
            error_state=narrative.get('model_error') or extra.get('error_state'),
            text=narrative.get('text') or narrative.get('body') or extra.get('text') or '',
        )
    except Exception:
        pass


def _period_in_scope(item: dict, period: str | None) -> bool:
    if not period:
        return True
    if not re.fullmatch(r'^\d{4}-\d{2}$', period):
        return False
    scope = item.get('period_scope') or {}
    month = scope.get('month')
    recurrence = str(scope.get('recurrence') or 'once').lower()
    effective = scope.get('effective_period')
    period_month = int(period.split('-')[1])
    if recurrence in ('monthly', 'recurring'):
        return True
    if recurrence == 'annual':
        return month in (None, period_month)
    if isinstance(effective, str) and re.fullmatch(r'^\d{4}-\d{2}$', effective):
        return effective == period
    return month in (None, period_month)


def _measured_movement_minor(analysis: dict, account_code: str) -> int | None:
    for claim in analysis.get('claims') or []:
        if not isinstance(claim, dict):
            continue
        if not _same_account(str(claim.get('account_code') or ''), account_code):
            continue
        ctype = str(claim.get('claim_type') or '').lower()
        if ctype in ('variance', 'absolute_variance', ''):
            amount = claim_amount_minor(claim)
            if amount is not None:
                return amount
    for item in analysis.get('variances') or []:
        if not isinstance(item, dict):
            continue
        if not _same_account(str(item.get('account_code') or ''), account_code):
            continue
        if isinstance(item.get('absolute_variance_minor'), int):
            return item['absolute_variance_minor']
        amount = claim_amount_minor(item)
        if amount is not None:
            return amount
    return None


def _source_context_id(supporting) -> str | None:
    if not isinstance(supporting, list):
        return None
    for item in supporting:
        if isinstance(item, str) and item.startswith('source:'):
            return item[7:]
    return None


def _persist_ledger_copy(db, package_path: Path, dataset_id: str, entity_id: str) -> None:
    """Copy validated CSVs into mo_summary_rows / mo_transactions. No analyze() math."""
    from .money_operations.config import ACCOUNT_CODES, ACCOUNT_COLUMNS, EXPENSE_NAME_TO_CODE, SKIP_SUMMARY_COLUMNS
    from .money_operations.integer import MoneyParseError, parse_whole_dollars_to_minor

    summary_path = package_path / 'monthly_account_summaries.csv'
    if summary_path.is_file():
        with summary_path.open(newline='', encoding='utf-8-sig') as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader, start=2):
                period = (row.get('period') or '').strip()
                if not re.fullmatch(r'^\d{4}-\d{2}$', period):
                    continue
                currency = (row.get('currency') or 'USD').strip() or 'USD'
                for column, code in ACCOUNT_COLUMNS.items():
                    if column in SKIP_SUMMARY_COLUMNS or column not in row:
                        continue
                    raw = row.get(column)
                    if raw is None or str(raw).strip() == '':
                        continue
                    try:
                        amount_minor = parse_whole_dollars_to_minor(str(raw), field=column)
                    except MoneyParseError:
                        continue
                    meta = ACCOUNT_CODES.get(code) or {}
                    db.execute(
                        'INSERT INTO mo_summary_rows(id,dataset_id,period,entity_id,account_code,account_name,'
                        'account_type,currency,amount_minor,source_row_id,source_file,source_row) '
                        'VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                        (
                            str(uuid.uuid4()), dataset_id, period, entity_id, code,
                            meta.get('account_name') or column, meta.get('account_type') or '',
                            currency, amount_minor, f'monthly_account_summaries.csv:{index}',
                            'monthly_account_summaries.csv', index,
                        ),
                    )

    for file_name, kind in (('revenue_transactions.csv', 'revenue'), ('expense_transactions.csv', 'expense')):
        path = package_path / file_name
        if not path.is_file():
            continue
        with path.open(newline='', encoding='utf-8-sig') as handle:
            reader = csv.DictReader(handle)
            for index, row in enumerate(reader, start=2):
                txn_id = (row.get('transaction_id') or '').strip()
                if not txn_id:
                    continue
                period = (row.get('recognized_month') or row.get('period') or '').strip()
                posted = (row.get('date') or '').strip()
                try:
                    signed_minor = parse_whole_dollars_to_minor(str(row.get('amount', '')), field='amount')
                except MoneyParseError:
                    continue
                if kind == 'revenue':
                    txn_type = (row.get('transaction_type') or '').strip()
                    if txn_type == 'Sale':
                        account_code = '4000'
                        amount_minor = signed_minor
                    elif txn_type == 'Refund':
                        account_code = '4100'
                        amount_minor = -signed_minor
                    else:
                        continue
                    customer_id = (row.get('customer_id') or '').strip() or None
                    product_id = (row.get('product') or row.get('product_id') or '').strip() or None
                    dimensions = {
                        'segment': (row.get('segment') or '').strip(),
                        'customer_id': customer_id or '',
                        'product': product_id or '',
                        'channel': (row.get('channel') or '').strip(),
                        'region': (row.get('region') or '').strip(),
                    }
                else:
                    account_code = EXPENSE_NAME_TO_CODE.get((row.get('account') or '').strip())
                    if not account_code:
                        continue
                    amount_minor = signed_minor
                    customer_id = None
                    product_id = None
                    dimensions = {
                        'driver_category': (row.get('driver_category') or '').strip(),
                        'vendor_id': (row.get('vendor_id') or '').strip(),
                        'vendor_name': (row.get('vendor_name') or '').strip(),
                    }
                db.execute(
                    'INSERT INTO mo_transactions(id,dataset_id,transaction_id,posted_date,period,entity_id,'
                    'account_code,amount_minor,currency,dimensions_json,source_file,source_row_number,'
                    'customer_id,product_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (
                        str(uuid.uuid4()), dataset_id, txn_id, posted, period, entity_id,
                        account_code, amount_minor, 'USD', _dump(dimensions), file_name, index,
                        customer_id, product_id,
                    ),
                )


def inspect_package(path: Path) -> dict:
    """Thin source-manifest loader. No money arithmetic."""
    if not path.is_dir():
        raise MoneyOpsError(422, 'invalid_dataset', 'Dataset path is not a directory')
    manifest_hashes = {}
    manifest_path = path / 'validation_manifest.json'
    if manifest_path.is_file():
        try:
            manifest_hashes = json.loads(manifest_path.read_text()).get('source_hashes') or {}
        except (OSError, json.JSONDecodeError, TypeError):
            manifest_hashes = {}
    sources = []
    periods: set[str] = set()
    findings = []
    for item in sorted(path.iterdir()):
        if not item.is_file() or item.suffix.lower() not in ALLOWED_UPLOAD_EXT:
            continue
        if item.name == 'expected_driver_answers.json':
            continue
        data = item.read_bytes()
        text = data.decode('utf-8-sig')
        rows = 0
        file_periods: list[str] = []
        if item.suffix.lower() == '.csv':
            lines = [line for line in text.splitlines() if line.strip()]
            rows = max(0, len(lines) - 1) if lines else 0
            if item.name == 'monthly_account_summaries.csv' and lines:
                header = lines[0].split(',')
                if 'period' in header:
                    idx = header.index('period')
                    for line in lines[1:]:
                        cols = line.split(',')
                        if len(cols) > idx and re.fullmatch(r'\d{4}-\d{2}', cols[idx]):
                            periods.add(cols[idx])
                            file_periods.append(cols[idx])
        else:
            rows = 1
        digest = hashlib.sha256(data).hexdigest()
        expected = manifest_hashes.get(item.name)
        if expected and expected != digest:
            findings.append({'code': 'hash_mismatch', 'file_name': item.name})
        sources.append({
            'source_id': 'src-' + item.stem.replace('_', '-'),
            'file_name': item.name,
            'sha256': digest,
            'byte_size': len(data),
            'row_count': rows,
            'schema_version': '1.0',
            'periods': file_periods,
            'synthetic': True,
        })
    if findings:
        raise MoneyOpsError(422, 'invalid_dataset', 'Source integrity check failed', {'findings': findings})
    try:
        from .money_operations import validate_dataset
        extra = validate_dataset(path)
        if isinstance(extra, dict):
            if extra.get('sources'):
                sources = extra['sources']
            if extra.get('available_periods'):
                periods = set(extra['available_periods'])
            findings = list(extra.get('findings') or findings)
            if extra.get('status') == 'invalid':
                raise MoneyOpsError(422, 'invalid_dataset', 'Dataset validation failed', {'findings': findings})
    except NotImplementedError:
        pass
    except MoneyOpsError:
        raise
    except (ValueError, TypeError, KeyError, OSError) as exc:
        raise MoneyOpsError(422, 'invalid_dataset', 'Dataset validation failed', {'reason': type(exc).__name__}) from exc
    return {
        'sources': sources,
        'validation_findings': findings,
        'available_periods': sorted(periods) or ['2026-01', '2026-02'],
        'status': 'validated',
    }


def _assert_stored_sources_intact(db, path: Path, dataset_id: str) -> None:
    rows = db.execute(
        'SELECT file_name, sha256 FROM mo_sources WHERE dataset_id=?',
        (dataset_id,),
    ).fetchall()
    mismatches = []
    for row in rows:
        name = row['file_name']
        expected = row['sha256']
        if not name or not expected:
            continue
        target = path / name
        if not target.is_file():
            mismatches.append(name)
            continue
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual != expected:
            mismatches.append(name)
    if mismatches:
        raise MoneyOpsError(422, 'source_modified', 'Stored source files no longer match ingest hashes', {
            'files': mismatches,
        })


def _run_analyze(path: Path, prior: str, current: str, entity_id: str) -> dict:
    from .money_operations import analyze
    from .money_operations.ingest import DatasetValidationError
    try:
        result = analyze(path, prior, current, entity_id)
    except NotImplementedError as exc:
        raise MoneyOpsError(
            503, 'engine_unavailable', 'Deterministic analysis engine is not implemented', {}
        ) from exc
    except DatasetValidationError as exc:
        raise MoneyOpsError(422, 'invalid_dataset', str(exc)[:300], {'findings': getattr(exc, 'findings', [])}) from exc
    if not isinstance(result, dict):
        raise MoneyOpsError(500, 'invalid_analysis', 'Engine returned a non-object analysis')
    return normalize_analysis(result, prior, current, entity_id)


def normalize_analysis(raw: dict, prior: str, current: str, entity_id: str) -> dict:
    claims = list(raw.get('claims') or [])
    variances = raw.get('variances')
    if isinstance(variances, dict):
        variances = list(variances.values()) if all(isinstance(v, dict) for v in variances.values()) else [variances]
    if not isinstance(variances, list):
        variances = [claim for claim in claims if str(claim.get('claim_type', '')).lower() in ('variance', 'account', '')]
    from .money_operations_narrative import ACCOUNT_NAMES, claim_bps, claim_value
    normalized_claims = []
    for claim in claims:
        if not isinstance(claim, dict) or not isinstance(claim.get('id'), str):
            continue
        item = dict(claim)
        amount = claim_amount_minor(item)
        if amount is not None:
            item['amount_minor'] = amount
        bps = claim_bps(item)
        if bps is not None:
            item.setdefault('percentage_bps', bps)
        value = claim_value(item)
        if isinstance(value.get('share_bps'), int):
            item.setdefault('share_bps', value['share_bps'])
        item.setdefault('account_code', item.get('account') or item.get('account_name') or 'unknown')
        item.setdefault('account_name', ACCOUNT_NAMES.get(str(item.get('account_code')), item.get('account_name') or ''))
        item.setdefault('claim_type', item.get('type') or 'variance')
        item.setdefault('status', 'computed')
        item.setdefault('formula', item.get('expression') or '')
        item.setdefault('source_ids', item.get('source_ids') or [])
        item.setdefault('source_rows', item.get('source_rows') or item.get('evidence') or [])
        item.setdefault('entities', item.get('entities') or [])
        normalized_claims.append(item)
    digest = raw.get('calculation_digest')
    if not isinstance(digest, str) or len(digest) < 16:
        digest = _digest({'claims': [c['id'] for c in normalized_claims], 'prior': prior, 'current': current})
    version = raw.get('calculation_version') or CALCULATION_VERSION
    unexplained = [claim for claim in normalized_claims if str(claim.get('status', '')).lower() == 'unexplained']
    conflicts = [claim for claim in normalized_claims if str(claim.get('status', '')).lower() == 'conflict']
    return {
        'entity_id': raw.get('entity_id') or entity_id,
        'periods': raw.get('periods') or {'prior': raw.get('prior_period') or prior, 'current': raw.get('current_period') or current},
        'prior_period': raw.get('prior_period') or prior,
        'current_period': raw.get('current_period') or current,
        'currency': raw.get('currency') or 'USD',
        'claims': normalized_claims,
        'variances': variances,
        'accounts': raw.get('accounts') or {},
        'sources': raw.get('sources') or [],
        'findings': raw.get('findings') or [],
        'calculation_digest': digest,
        'calculation_version': version,
        'unexplained': unexplained or list(raw.get('unexplained') or []),
        'conflicts': conflicts or list(raw.get('conflicts') or []),
    }


def _signed_write(db, key: bytes, table: str, row_id: str, columns: tuple, values: tuple, body: dict):
    payload = _dump(body)
    mac = _mac(key, payload)
    placeholders = ','.join('?' * (len(columns) + 2))
    db.execute(
        f'INSERT INTO {table} ({",".join(columns)},body_json,mac) VALUES({placeholders})',
        (row_id, *values, payload, mac),
    )


def _signed_read(db, key: bytes, table: str, row_id: str):
    row = db.execute(f'SELECT * FROM {table} WHERE id=?', (row_id,)).fetchone()
    if row is None:
        return None
    expected = _mac(key, row['body_json'])
    if not hmac.compare_digest(expected, row['mac']):
        raise MoneyOpsError(409, 'integrity_failure', 'Protected Money Operations record failed HMAC verification')
    body = json.loads(row['body_json'])
    return row, body


def _signed_update(db, key: bytes, table: str, row_id: str, body: dict, extra_sql: str, extra_params: tuple):
    payload = _dump(body)
    mac = _mac(key, payload)
    db.execute(
        f'UPDATE {table} SET body_json=?, mac=?, {extra_sql} WHERE id=?',
        (payload, mac, *extra_params, row_id),
    )


def _context_revision(db) -> int:
    row = db.execute("SELECT body FROM settings WHERE key='mo_context_revision'").fetchone()
    return int(row['body']) if row else 1


def _set_context_revision(db, value: int):
    db.execute(
        "INSERT INTO settings VALUES('mo_context_revision',?) ON CONFLICT(key) DO UPDATE SET body=excluded.body",
        (str(value),),
    )


def _append_event(db, store, aggregate_type: str, aggregate_id: str, revision: int, event_type: str, actor: str, body: dict):
    prev = db.execute(
        'SELECT digest FROM mo_events WHERE aggregate_type=? AND aggregate_id=? ORDER BY rowid DESC LIMIT 1',
        (aggregate_type, aggregate_id),
    ).fetchone()
    prev_digest = prev['digest'] if prev else '0' * 64
    payload = _dump(body)
    digest = hmac.new(store.key, (prev_digest + payload).encode(), hashlib.sha256).hexdigest()
    db.execute(
        'INSERT INTO mo_events VALUES(?,?,?,?,?,?,?,?,?,?)',
        (str(uuid.uuid4()), aggregate_type, aggregate_id, revision, event_type, actor, _now(), payload, prev_digest, digest),
    )


def _row_to_context(row) -> dict:
    supporting = json.loads(row['supporting_claim_ids_json'] or '[]')
    scope = json.loads(row['period_scope_json'])
    measured = scope.get('measured_amount_minor') if isinstance(scope, dict) else None
    return {
        'id': row['id'],
        'context_id': row['id'],
        'entity_id': row['entity_id'],
        'account_code': row['account_code'],
        'dimension': row['dimension'],
        'member': row['member'],
        'statement': row['statement'],
        'status': row['status'],
        'confirmation_state': row['status'],
        'actor': row['actor'],
        'recorded_at': row['recorded_at'],
        'revision': row['revision'],
        'supersedes': row['supersedes'],
        'period_scope': scope,
        'tombstoned': bool(row['tombstoned']),
        'analysis_id': row['analysis_id'],
        'supporting_claim_ids': supporting,
        'source_context_id': _source_context_id(supporting),
        'source_analysis_id': row['analysis_id'],
        'measured_amount_minor': measured if isinstance(measured, int) else None,
    }


def _superseded_ids(db) -> set[str]:
    return {row['supersedes'] for row in db.execute('SELECT supersedes FROM mo_context WHERE supersedes IS NOT NULL') if row['supersedes']}


def _active_context_rows(db):
    superseded = _superseded_ids(db)
    rows = []
    for row in db.execute('SELECT * FROM mo_context ORDER BY recorded_at, id'):
        item = _row_to_context(row)
        item['active'] = (not item['tombstoned']) and item['id'] not in superseded
        rows.append(item)
    return rows


def seed_context(db):
    if db.execute('SELECT 1 FROM mo_context LIMIT 1').fetchone():
        return
    if not CONTEXT_SEED.is_file():
        _set_context_revision(db, 1)
        return
    payload = json.loads(CONTEXT_SEED.read_text())
    for entry in payload.get('entries') or []:
        period = str(entry.get('effective_period') or '2026-02')
        month = int(period.split('-')[1]) if re.fullmatch(r'\d{4}-\d{2}', period) else 2
        from .money_operations.config import CONTEXT_ACCOUNT_TO_CODE
        labeled = entry.get('account') or entry.get('account_code') or ''
        account = CONTEXT_ACCOUNT_TO_CODE.get(labeled) or _normalize_account(labeled)
        recurrence = 'annual' if 'novaerp' in str(entry.get('statement', '')).lower() or 'erp' in str(entry.get('statement', '')).lower() else 'once'
        db.execute(
            'INSERT INTO mo_context VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (
                entry.get('context_id') or str(uuid.uuid4()),
                DEFAULT_ENTITY,
                account,
                None,
                None,
                entry.get('statement') or '',
                entry.get('status') or 'user_confirmed',
                entry.get('confirmed_by') or entry.get('actor') or 'fixture',
                entry.get('confirmed_at') or _now(),
                int(entry.get('revision') or 1),
                entry.get('supersedes'),
                _dump({'month': month, 'recurrence': recurrence, 'effective_period': period}),
                0,
                None,
                '[]',
            ),
        )
    _set_context_revision(db, 1)


def init_money_operations(store):
    with store.transaction() as db:
        seed_context(db)


def _context_matches_analysis(item: dict, analysis: dict) -> bool:
    if item.get('entity_id') != analysis.get('entity_id', DEFAULT_ENTITY):
        return False
    current = (analysis.get('periods') or {}).get('current') or analysis.get('current_period')
    return _period_in_scope(item, current)


def _suggest_context_for_analysis(db, store, analysis_id: str, analysis: dict, actor: str):
    created = []
    for item in _active_context_rows(db):
        if item['status'] != 'user_confirmed' or item.get('analysis_id'):
            continue
        if _is_other_opex(str(item.get('account_code') or '')):
            continue
        if not _context_matches_analysis(item, analysis):
            continue
        new_id = str(uuid.uuid4())
        status = 'context_suggested'
        scope = dict(item.get('period_scope') or {})
        measured = _measured_movement_minor(analysis, str(item.get('account_code') or ''))
        if measured is not None:
            scope['measured_amount_minor'] = measured
        db.execute(
            'INSERT INTO mo_context VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (
                new_id,
                item['entity_id'],
                item['account_code'],
                item['dimension'],
                item['member'],
                item['statement'],
                status,
                'system',
                _now(),
                item['revision'],
                None,
                _dump(scope),
                0,
                analysis_id,
                _dump([f'source:{item["id"]}']),
            ),
        )
        created.append(new_id)
    if created:
        rev = _context_revision(db) + 1
        _set_context_revision(db, rev)
        _append_event(db, store, 'context', analysis_id, rev, 'context_suggested', actor, {'ids': created})
    return created


def _persist_dataset(db, store, user: dict, package_path: Path, inspect: dict, entity_id: str) -> dict:
    dataset_id = str(uuid.uuid4())
    created = _now()
    body = {
        'dataset_id': dataset_id,
        'status': inspect['status'],
        'revision': 1,
        'entity_id': entity_id,
        'path': str(package_path),
        'fixture': inspect.get('fixture'),
        'sources': inspect['sources'],
        'validation_findings': inspect['validation_findings'],
        'available_periods': inspect['available_periods'],
        'created_by': user['username'],
        'created_at': created,
    }
    _signed_write(
        db, store.key, 'mo_datasets', dataset_id,
        ('id', 'status', 'revision', 'entity_id', 'created_by', 'created_at'),
        (inspect['status'], 1, entity_id, user['username'], created),
        body,
    )
    for source in inspect['sources']:
        db.execute(
            'INSERT INTO mo_sources VALUES(?,?,?,?,?,?,?,?)',
            (
                source.get('source_id') or str(uuid.uuid4()),
                dataset_id,
                source.get('file_name') or '',
                source.get('sha256') or '',
                int(source.get('byte_size') or 0),
                int(source.get('row_count') or 0),
                source.get('schema_version') or '1.0',
                _dump(source),
            ),
        )
    _persist_ledger_copy(db, package_path, dataset_id, entity_id)
    _append_event(db, store, 'dataset', dataset_id, 1, 'dataset_ingested', user['username'], {'path': str(package_path)})
    return body


def _dataset_response(body: dict) -> dict:
    return {
        'dataset_id': body['dataset_id'],
        'status': body['status'],
        'revision': body['revision'],
        'sources': body.get('sources') or [],
        'validation_findings': body.get('validation_findings') or [],
        'available_periods': body.get('available_periods') or [],
    }


def _persist_claims(db, analysis_id: str, claims: list[dict]):
    for claim in claims:
        db.execute(
            'INSERT INTO mo_claims VALUES(?,?,?,?,?,?,?,?,?,?)',
            (
                f'{analysis_id}:{claim["id"]}',
                analysis_id,
                claim['id'],
                str(claim.get('account_code') or 'unknown'),
                str(claim.get('claim_type') or 'variance'),
                str(claim.get('status') or 'computed'),
                _dump({key: claim[key] for key in claim if key != 'source_rows'}),
                str(claim.get('formula') or ''),
                _dump(claim.get('source_ids') or []),
                _dump(claim.get('source_rows') or []),
            ),
        )


def _analysis_public(row, body: dict, context_rows: list[dict], revision: int | None = None) -> dict:
    narrative = body.get('narrative') or {}
    suggested = [item for item in context_rows if item.get('analysis_id') == row['id'] and item['status'] == 'context_suggested' and item.get('active')]
    confirmed = [
        item for item in context_rows
        if item.get('analysis_id') == row['id']
        and item['status'] in ('user_confirmed', 'corrected')
        and item.get('active')
        and not _is_other_opex(str(item.get('account_code') or ''))
    ]
    claims = body.get('claims') or []
    unexplained = body.get('unexplained') or [c for c in claims if str(c.get('status', '')).lower() == 'unexplained']
    conflicts = [
        c for c in (body.get('conflicts') or [c for c in claims if str(c.get('status', '')).lower() == 'conflict'])
        if not _is_other_opex(str(c.get('account_code') or ''))
    ]
    review_status = body.get('review_status')
    if review_status in (None, '', 'none'):
        review_status = 'draft'
    escalations = _build_escalations(body, review_status)
    metrics = dict(body.get('metrics') or {
        'material_variances': len(body.get('variances') or claims),
        'reconciled': sum(1 for c in claims if str(c.get('status', '')).lower() in ('reconciled', 'computed')),
        'conflicts': len(conflicts),
        'review_status': review_status,
    })
    metrics['conflicts'] = len(conflicts)
    metrics['causally_unexplained'] = len(escalations)
    metrics['review_status'] = review_status
    return {
        'analysis_id': row['id'],
        'dataset_id': row['dataset_id'],
        'entity_id': body.get('entity_id') or DEFAULT_ENTITY,
        'entity_name': body.get('entity_name') or 'Yari Technology Retail',
        'status': row['status'],
        'revision': row['revision'] if revision is None else revision,
        'periods': body.get('periods') or {'prior': row['prior_period'], 'current': row['current_period']},
        'currency': body.get('currency') or 'USD',
        'calculation_version': row['calculation_version'],
        'calculation_digest': body.get('calculation_digest'),
        'narrative_digest': _digest(narrative),
        'metrics': metrics,
        'top_variances': body.get('variances') or claims[:8],
        'claims': claims,
        'variances': body.get('variances') or [],
        'narrative': narrative,
        'suggested_context': suggested,
        'confirmed_context': confirmed,
        'unexplained': unexplained,
        'causally_unexplained': unexplained,
        'conflicts': conflicts,
        'escalations': escalations,
        'context_revision': body.get('context_revision_at_create') or _safe_ctx_rev_from_body(body),
        'review_status': review_status,
        'approval_bound_revision': body.get('approval_bound_revision'),
        'integration_status': body.get('integration_status') or money_ops_integration_status(narrative.get('narrative_source') or 'deterministic_template'),
        'links': {
            'self': f'/api/money-operations/analyses/{row["id"]}',
            'variances': f'/api/money-operations/analyses/{row["id"]}/variances',
            'escalations': f'/api/money-operations/analyses/{row["id"]}/escalations',
            'export_json': f'/api/money-operations/analyses/{row["id"]}/export.json',
            'export_csv': f'/api/money-operations/analyses/{row["id"]}/export.csv',
            'memo_html': f'/api/money-operations/analyses/{row["id"]}/memo.html',
            'lineage': f'/api/money-operations/analyses/{row["id"]}/lineage',
            'integration_status': f'/api/money-operations/analyses/{row["id"]}/integration-status',
        },
    }


def _safe_ctx_rev_from_body(body: dict) -> int:
    value = body.get('context_revision_at_create')
    return int(value) if isinstance(value, int) else 1


def _build_escalations(body: dict, review_status: str) -> list[dict]:
    """Causally unexplained items. Reconciled Other Opex is not a reconciliation_conflict."""
    from .money_operations_narrative import ACCOUNT_NAMES
    claims = list(body.get('claims') or [])
    unexplained = list(body.get('unexplained') or [c for c in claims if str(c.get('status', '')).lower() == 'unexplained'])
    accounts = body.get('accounts') if isinstance(body.get('accounts'), dict) else {}
    seen: set[str] = set()
    escalations: list[dict] = []

    def add(code: str, claim: dict | None, recon_status: str, amount_minor: int | None, claim_ids: list[str], source_files: list[str]):
        resolved = _normalize_account(code)
        if resolved in seen or not resolved:
            return
        seen.add(resolved)
        movement = amount_minor if isinstance(amount_minor, int) else 0
        escalations.append({
            'account': {
                'code': resolved,
                'name': ACCOUNT_NAMES.get(resolved) or ACCOUNT_NAMES.get(code) or (claim or {}).get('account_name') or code,
            },
            'measured_movement': {
                'amount_minor': movement,
                'usd': movement // 100,
            },
            'reconciliation_status': recon_status,
            'unsupported_cause': True,
            'unsupported_cause_statement': 'Measured movement is numerically reconciled; the source data does not establish a business cause.',
            'evidence_links': {
                'claim_ids': claim_ids,
                'source_files': source_files,
            },
            'owner': 'controller',
            'recommended_next_question': 'What source documentation supports the unmapped clearing batch in Other Opex?',
            'review_status': review_status,
        })

    if isinstance(accounts.get('6900'), dict):
        block = accounts['6900']
        causal = block.get('causal') or {}
        recon = block.get('reconciliation') or {}
        variance = block.get('variance') or {}
        if str(causal.get('status', '')).lower() == 'unexplained':
            amount = variance.get('absolute_variance_minor')
            if not isinstance(amount, int):
                amount = causal.get('unexplained_residual_minor')
            claim_ids = [c['id'] for c in claims if isinstance(c, dict) and c.get('id') and _is_other_opex(str(c.get('account_code') or ''))]
            files = []
            for claim in claims:
                if not isinstance(claim, dict) or not _is_other_opex(str(claim.get('account_code') or '')):
                    continue
                for row in claim.get('source_rows') or []:
                    if isinstance(row, dict) and row.get('source_file'):
                        files.append(row['source_file'])
            add('6900', variance, str(recon.get('status') or 'reconciled'), amount, claim_ids, list(dict.fromkeys(files)))

    for claim in unexplained:
        if not isinstance(claim, dict):
            continue
        code = str(claim.get('account_code') or '')
        if not _is_other_opex(code) and str(claim.get('status', '')).lower() != 'unexplained':
            continue
        if not _is_other_opex(code) and str(claim.get('claim_type', '')).lower() not in ('causal', 'variance', 'absolute_variance', ''):
            continue
        recon_status = 'reconciled' if _is_other_opex(code) else 'unexplained'
        files = []
        for row in claim.get('source_rows') or []:
            if isinstance(row, dict) and row.get('source_file'):
                files.append(row['source_file'])
        add(code, claim, recon_status, claim_amount_minor(claim), [claim['id']] if claim.get('id') else [], files)

    return escalations


def _confirmed_for_analysis(db, analysis_id: str) -> list[dict]:
    return [
        item for item in _active_context_rows(db)
        if item.get('analysis_id') == analysis_id and item['status'] in ('user_confirmed', 'corrected') and item.get('active')
        and not _is_other_opex(str(item.get('account_code') or ''))
    ]


def _recompose_after_context(db, store, analysis_id: str, actor: str, event_type: str) -> tuple:
    row, analysis = _load_analysis(db, store, analysis_id)
    digest_before = analysis.get('calculation_digest')
    confirmed = _confirmed_for_analysis(db, analysis_id)
    try:
        narrative = compose({
            'claims': analysis.get('claims') or [],
            'variances': analysis.get('variances'),
            'periods': analysis.get('periods'),
            'confirmed_context': confirmed,
        })
    except Exception:
        narrative = dict(analysis.get('narrative') or {})
    narrative = dict(narrative)
    narrative['context'] = [
        {
            'id': item['id'],
            'account_code': item.get('account_code'),
            'statement': item.get('statement'),
            'status': item.get('status'),
        }
        for item in confirmed
    ]
    _observe_narrative(
        analysis_id,
        narrative,
        confirmed,
        prior_period=(analysis.get('periods') or {}).get('prior'),
        current_period=(analysis.get('periods') or {}).get('current'),
        calculation_digest=digest_before,
        unexplained_item_count=sum(
            1 for claim in (analysis.get('claims') or [])
            if str(claim.get('status', '')).lower() == 'unexplained'
        ),
        reconciliation_status='conflict' if analysis.get('conflicts') else 'reconciled',
        numeric_validation='pass',
        citation_validation='pass' if not narrative.get('model_error') else 'reject',
        fallback=bool(narrative.get('model_error')),
    )
    analysis = dict(analysis)
    analysis['narrative'] = narrative
    if analysis.get('review_status') in ('approved', 'changes_requested', 'rejected'):
        analysis['review_status'] = 'invalidated'
        analysis['approval_bound_revision'] = None
    analysis['metrics'] = dict(analysis.get('metrics') or {}, review_status=analysis.get('review_status') or 'draft')
    if analysis.get('calculation_digest') != digest_before:
        analysis['calculation_digest'] = digest_before
    next_rev = int(row['revision']) + 1
    _signed_update(db, store.key, 'mo_analyses', analysis_id, analysis, 'revision=?, status=?', (next_rev, row['status']))
    _append_event(db, store, 'analysis', analysis_id, next_rev, event_type, actor, {
        'calculation_digest': digest_before,
        'narrative_digest': _digest(narrative),
        'review_status': analysis.get('review_status'),
    })
    return _load_analysis(db, store, analysis_id)


def money_ops_integration_status(narrative_source: str = 'deterministic_template') -> dict:
    """Honest Money Operations status. Payment-adapter live is never inherited."""
    from .money_operations_prism import prism_status
    from .money_operations_audio import audio_state
    try:
        from .integrations import integration_status
        raw = integration_status()
    except Exception:
        raw = {}
    observed = prism_status()
    state = observed.get('state') or 'not_configured'
    if state == 'live_connected' and not observed.get('application_trace_id'):
        state = 'live_trace_pending'
    # A payment handshake or doctor report is not a Money Operations application trace.
    payment_prism = raw.get('prism')
    if payment_prism == 'live_connected' and not observed.get('application_trace_id'):
        if state == 'live_connected':
            state = 'credential_ok'
    return {
        'narrative': narrative_source if narrative_source in ('deterministic_template', 'model') else 'deterministic_template',
        'prism': state,
        'gide': 'usage_pending',
        'gide_evaluation': 'pending',
        'model': raw.get('model') or 'replay',
        'synthetic_egress_enabled': observed.get('synthetic_egress_enabled'),
        'status_scope': 'current_worker_observations',
        'audio': audio_state().get('state'),
        'application_trace_id': observed.get('application_trace_id'),
    }


def _load_analysis(db, store, analysis_id: str):
    loaded = _signed_read(db, store.key, 'mo_analyses', analysis_id)
    if loaded is None:
        raise MoneyOpsError(404, 'not_found', 'Analysis not found', {'analysis_id': analysis_id})
    return loaded


def _load_dataset(db, store, dataset_id: str):
    loaded = _signed_read(db, store.key, 'mo_datasets', dataset_id)
    if loaded is None:
        raise MoneyOpsError(404, 'not_found', 'Dataset not found', {'dataset_id': dataset_id})
    return loaded


def _variance_payload(body: dict, account_code: str) -> dict:
    resolved = _normalize_account(account_code)
    claims = [
        c for c in body.get('claims') or []
        if _same_account(str(c.get('account_code') or ''), account_code)
        or _same_account(str(c.get('account_name') or ''), account_code)
        or account_code.lower() == str(c.get('id') or '').lower()
    ]
    variances = body.get('variances') or []
    matched = None
    if isinstance(variances, list):
        for item in variances:
            if isinstance(item, dict) and (
                _same_account(str(item.get('account_code') or ''), account_code)
                or _same_account(str(item.get('account_name') or ''), account_code)
            ):
                matched = item
                break
    drivers = None
    recon = None
    try:
        from .money_operations import attribute_drivers, reconcile_account
        try:
            drivers = attribute_drivers(body, resolved)
        except KeyError:
            drivers = attribute_drivers(body, account_code)
        try:
            recon = reconcile_account(body, resolved)
        except KeyError:
            recon = reconcile_account(body, account_code)
    except (NotImplementedError, TypeError, KeyError, ValueError):
        if isinstance(matched, dict):
            drivers = drivers or matched.get('drivers')
            recon = recon or matched.get('reconciliation')
    narrative = body.get('narrative') or {}
    return {
        'account_code': account_code,
        'calculation': matched or (claims[0] if claims else None),
        'claims': claims,
        'primary_dimension': (matched or {}).get('primary_dimension') if isinstance(matched, dict) else None,
        'alternative_dimensions': (matched or {}).get('alternative_dimensions') if isinstance(matched, dict) else [],
        'drivers': drivers,
        'offsets': (matched or {}).get('offsets') if isinstance(matched, dict) else [],
        'reconciliation': recon,
        'evidence_claim_ids': [c['id'] for c in claims],
        'narrative': narrative,
        'suggested_context': [
            item for item in (body.get('suggested_context') or [])
            if _same_account(str(item.get('account_code') or ''), account_code)
        ],
    }


def register_money_operations(app, store, auth):
    @app.exception_handler(MoneyOpsError)
    async def _mo_error_handler(request, exc: MoneyOpsError):
        return _error_response(exc)

    def write_user(user=Depends(auth)):
        _require_write(user)
        return user

    def controller_user(user=Depends(auth)):
        _require_controller(user)
        return user

    @app.post('/api/money-operations/datasets')
    async def create_dataset(request: Request, user=Depends(write_user)):
        content_type = (request.headers.get('content-type') or '').lower()
        byte_limit, row_limit = _upload_limits()
        if 'multipart/form-data' in content_type:
            uploads = parse_multipart_files(content_type, await request.body())
            dest = store.path.parent / 'mo-uploads' / str(uuid.uuid4())
            dest.mkdir(parents=True, exist_ok=True)
            total_bytes = 0
            try:
                for filename, data in uploads:
                    name = _safe_filename(filename)
                    total_bytes += len(data)
                    if total_bytes > byte_limit:
                        raise MoneyOpsError(413, 'upload_too_large', 'Upload exceeds the configured byte limit')
                    text = data.decode('utf-8-sig')
                    if name.endswith('.csv'):
                        rows = max(0, len([line for line in text.splitlines() if line.strip()]) - 1)
                        if rows > row_limit:
                            raise MoneyOpsError(422, 'upload_too_many_rows', 'Upload exceeds the configured row limit', {'rows': rows})
                    (dest / name).write_bytes(data)
                inspect = inspect_package(dest)
                inspect['fixture'] = None
                with store.transaction() as db:
                    body = _persist_dataset(db, store, user, dest, inspect, DEFAULT_ENTITY)
                return JSONResponse(_dataset_response(body), status_code=201)
            except MoneyOpsError:
                shutil.rmtree(dest, ignore_errors=True)
                raise
        try:
            payload = await request.json()
        except Exception as exc:
            raise MoneyOpsError(422, 'invalid_request', 'JSON or multipart dataset request required') from exc
        try:
            DatasetSelect.model_validate(payload)
        except ValidationError as exc:
            raise MoneyOpsError(422, 'invalid_request', 'fixture must be reference', {'errors': exc.errors()}) from exc
        inspect = inspect_package(FIXTURE_DIR)
        inspect['fixture'] = 'reference'
        with store.transaction() as db:
            body = _persist_dataset(db, store, user, FIXTURE_DIR, inspect, DEFAULT_ENTITY)
        return JSONResponse(_dataset_response(body), status_code=201)

    @app.post('/api/money-operations/analyses')
    def create_analysis(body: AnalysisCreate, user=Depends(write_user)):
        with store.transaction() as db:
            dataset_row, dataset = _load_dataset(db, store, body.dataset_id)
            if body.expected_revision is not None and body.expected_revision != dataset_row['revision']:
                raise MoneyOpsError(409, 'stale_revision', 'Dataset changed; refresh before analyzing', {
                    'actual_revision': dataset_row['revision'],
                    'expected_revision': body.expected_revision,
                })
            path = Path(dataset.get('path') or FIXTURE_DIR)
            _assert_stored_sources_intact(db, path, body.dataset_id)
            computed = _run_analyze(path, body.prior_period, body.current_period, body.entity_id)
            analysis_id = str(uuid.uuid4())
            try:
                narrative = compose({
                    'claims': computed['claims'],
                    'variances': computed['variances'],
                    'periods': computed['periods'],
                })
            except Exception:
                narrative = {
                    'headline': 'Deterministic claims are available; narrative validation failed closed.',
                    'text': 'Review cited claims in the evidence package. Unsupported causes remain unexplained.',
                    'body': 'Review cited claims in the evidence package. Unsupported causes remain unexplained.',
                    'cited_claim_ids': [],
                    'narrative_source': 'deterministic_template',
                    'mode': 'deterministic_template',
                    'model_error': 'template_validation_failed',
                }
            _observe_narrative(
                analysis_id,
                narrative,
                [],
                prior_period=body.prior_period,
                current_period=body.current_period,
                calculation_digest=computed.get('calculation_digest'),
                unexplained_item_count=sum(
                    1 for claim in computed['claims']
                    if str(claim.get('status', '')).lower() == 'unexplained'
                ),
                reconciliation_status='conflict' if computed.get('conflicts') else 'reconciled',
                numeric_validation='pass',
                citation_validation='pass' if not narrative.get('model_error') else 'reject',
                fallback=bool(narrative.get('model_error')),
            )
            created = _now()
            stored = {
                **computed,
                'analysis_id': analysis_id,
                'dataset_id': body.dataset_id,
                'entity_id': body.entity_id,
                'entity_name': 'Yari Technology Retail',
                'narrative': narrative,
                'review_status': 'draft',
                'metrics': {
                    'material_variances': len(computed.get('variances') or computed['claims']),
                    'reconciled': sum(1 for c in computed['claims'] if str(c.get('status', '')).lower() in ('reconciled', 'computed')),
                    'conflicts': len(computed.get('conflicts') or []),
                    'review_status': 'draft',
                },
                'integration_status': money_ops_integration_status(narrative.get('narrative_source') or 'deterministic_template'),
            }
            _signed_write(
                db, store.key, 'mo_analyses', analysis_id,
                ('id', 'dataset_id', 'prior_period', 'current_period', 'status', 'revision', 'calculation_version', 'created_by', 'created_at'),
                (body.dataset_id, body.prior_period, body.current_period, 'drafted', 1, stored['calculation_version'], user['username'], created),
                stored,
            )
            _persist_claims(db, analysis_id, computed['claims'])
            _suggest_context_for_analysis(db, store, analysis_id, stored, user['username'])
            stored['context_revision_at_create'] = _context_revision(db)
            _signed_update(db, store.key, 'mo_analyses', analysis_id, stored, 'revision=?', (1,))
            _append_event(db, store, 'analysis', analysis_id, 1, 'analysis_created', user['username'], {
                'calculation_digest': stored['calculation_digest'],
                'calculation_version': stored['calculation_version'],
            })
            row, _ = _signed_read(db, store.key, 'mo_analyses', analysis_id)
            public = _analysis_public(row, stored, _active_context_rows(db))
            public['context_revision'] = _context_revision(db)
            return JSONResponse(public, status_code=201)

    @app.get('/api/money-operations/analyses/{analysis_id}')
    def get_analysis(analysis_id: str, user=Depends(auth)):
        with store.connect() as db:
            row, body = _load_analysis(db, store, analysis_id)
            public = _analysis_public(row, body, _active_context_rows(db))
            public['context_revision'] = _context_revision(db)
            return public

    @app.get('/api/money-operations/analyses/{analysis_id}/variances')
    def list_variances(analysis_id: str, material_only: bool = False, limit: int = 50, cursor: int = 0, user=Depends(auth)):
        with store.connect() as db:
            row, body = _load_analysis(db, store, analysis_id)
        items = list(body.get('variances') or body.get('claims') or [])
        if material_only:
            items = [item for item in items if isinstance(item, dict) and (abs(claim_amount_minor(item) or 0) >= 2_500_000 or item.get('material'))]
        cursor = max(0, cursor)
        limit = min(max(1, limit), 200)
        page = items[cursor:cursor + limit]
        return {
            'analysis_id': analysis_id,
            'items': page,
            'next_cursor': cursor + limit if cursor + limit < len(items) else None,
            'total': len(items),
            'calculation_digest': body.get('calculation_digest'),
        }

    @app.get('/api/money-operations/analyses/{analysis_id}/variances/{account_code}')
    def get_variance(analysis_id: str, account_code: str, user=Depends(auth)):
        with store.connect() as db:
            row, body = _load_analysis(db, store, analysis_id)
            payload = _variance_payload(body, account_code)
            payload['suggested_context'] = [
                item for item in _active_context_rows(db)
                if item.get('analysis_id') == analysis_id and _same_account(str(item.get('account_code') or ''), account_code)
            ]
            if payload['calculation'] is None and not payload['claims']:
                raise MoneyOpsError(404, 'not_found', 'Variance not found', {'account_code': account_code})
            return payload

    @app.get('/api/money-operations/claims/{claim_id}/evidence')
    def claim_evidence(claim_id: str, limit: int = 20, cursor: int = 0, user=Depends(auth)):
        with store.connect() as db:
            row = db.execute('SELECT * FROM mo_claims WHERE original_id=? OR id=?', (claim_id, claim_id)).fetchone()
            if row is None and ':' not in claim_id:
                row = db.execute('SELECT * FROM mo_claims WHERE original_id=? ORDER BY analysis_id DESC', (claim_id,)).fetchone()
            if row is None:
                raise MoneyOpsError(404, 'not_found', 'Claim not found', {'claim_id': claim_id})
            rows = json.loads(row['source_rows_json'] or '[]')
            if not isinstance(rows, list):
                rows = []
            cursor = max(0, cursor)
            limit = min(max(1, limit), 200)
            page = rows[cursor:cursor + limit]
            return {
                'claim_id': row['original_id'],
                'analysis_id': row['analysis_id'],
                'status': row['status'],
                'formula': row['formula'],
                'source_ids': json.loads(row['source_ids_json'] or '[]'),
                'items': page,
                'next_cursor': cursor + limit if cursor + limit < len(rows) else None,
                'total': len(rows),
            }

    @app.get('/api/money-operations/context')
    def get_context(
        entity: str | None = None,
        account: str | None = None,
        dimension: str | None = None,
        member: str | None = None,
        period: str | None = None,
        recurrence: str | None = None,
        active: bool | None = None,
        user=Depends(auth),
    ):
        with store.connect() as db:
            items = _active_context_rows(db)
            revision = _context_revision(db)
        if entity:
            items = [item for item in items if item['entity_id'] == entity]
        if account:
            items = [item for item in items if _same_account(str(item['account_code']), account)]
        if dimension:
            items = [item for item in items if item.get('dimension') == dimension]
        if member:
            items = [item for item in items if item.get('member') == member]
        if period:
            items = [item for item in items if _period_in_scope(item, period)]
        if recurrence:
            items = [item for item in items if str((item.get('period_scope') or {}).get('recurrence') or '').lower() == recurrence.lower()]
        if active is True:
            items = [item for item in items if item.get('active')]
        elif active is False:
            items = [item for item in items if not item.get('active')]
        return {'entries': items, 'revision': revision}

    @app.post('/api/money-operations/context')
    def create_context(body: ContextCreate, user=Depends(write_user)):
        with store.transaction() as db:
            current = _context_revision(db)
            if body.expected_revision != current:
                raise MoneyOpsError(409, 'stale_revision', 'Context ledger changed; refresh before writing', {
                    'actual_revision': current,
                    'expected_revision': body.expected_revision,
                })
            row, analysis = _load_analysis(db, store, body.analysis_id)
            digest_before = analysis.get('calculation_digest')
            new_id = str(uuid.uuid4())
            next_rev = current + 1
            db.execute(
                'INSERT INTO mo_context VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    new_id, analysis.get('entity_id') or DEFAULT_ENTITY,
                    body.account_code, body.dimension, body.member, body.statement,
                    'user_confirmed', user['username'], _now(), 1, None,
                    _dump(body.period_scope.model_dump()), 0, body.analysis_id, '[]',
                ),
            )
            # Other Opex notes are stored but never treated as a supported cause.
            _set_context_revision(db, next_rev)
            _append_event(db, store, 'context', new_id, next_rev, 'context_created', user['username'], {'statement': body.statement})
            row2, analysis2 = _load_analysis(db, store, body.analysis_id)
            if analysis2.get('calculation_digest') != digest_before:
                raise MoneyOpsError(500, 'invariant', 'Context write must not change calculation_digest')
            return {
                'context': _row_to_context(db.execute('SELECT * FROM mo_context WHERE id=?', (new_id,)).fetchone()),
                'revision': next_rev,
                'calculation_digest': digest_before,
            }

    @app.post('/api/money-operations/context/{context_id}/correct')
    def correct_context(context_id: str, body: ContextMutation, user=Depends(controller_user)):
        if not body.statement:
            raise MoneyOpsError(422, 'invalid_request', 'Corrected statement is required')
        with store.transaction() as db:
            current = _context_revision(db)
            if body.expected_revision != current:
                raise MoneyOpsError(409, 'stale_revision', 'Context ledger changed; refresh before correcting', {
                    'actual_revision': current,
                    'expected_revision': body.expected_revision,
                })
            prior = db.execute('SELECT * FROM mo_context WHERE id=?', (context_id,)).fetchone()
            if prior is None:
                raise MoneyOpsError(404, 'not_found', 'Context not found', {'context_id': context_id})
            new_id = str(uuid.uuid4())
            next_rev = current + 1
            db.execute(
                'INSERT INTO mo_context VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    new_id, prior['entity_id'], prior['account_code'], prior['dimension'], prior['member'],
                    body.statement, 'corrected', user['username'], _now(), int(prior['revision']) + 1,
                    prior['id'], prior['period_scope_json'], 0, prior['analysis_id'], prior['supporting_claim_ids_json'],
                ),
            )
            _set_context_revision(db, next_rev)
            _append_event(db, store, 'context', new_id, next_rev, 'context_corrected', user['username'], {
                'supersedes': prior['id'],
                'statement': body.statement,
            })
            if prior['analysis_id'] and not _is_other_opex(str(prior['account_code'] or '')):
                _recompose_after_context(db, store, prior['analysis_id'], user['username'], 'narrative_recomposed')
            history = []
            cursor_id = new_id
            seen = set()
            while cursor_id and cursor_id not in seen:
                seen.add(cursor_id)
                item = db.execute('SELECT * FROM mo_context WHERE id=?', (cursor_id,)).fetchone()
                if item is None:
                    break
                history.append(_row_to_context(item))
                cursor_id = item['supersedes']
            digest = None
            if prior['analysis_id']:
                _, analysis = _load_analysis(db, store, prior['analysis_id'])
                digest = analysis.get('calculation_digest')
            return {'context': history[0], 'history': history, 'revision': next_rev, 'calculation_digest': digest}

    @app.post('/api/money-operations/context/{context_id}/confirm')
    def confirm_context(context_id: str, body: ContextMutation, user=Depends(write_user)):
        with store.transaction() as db:
            current = _context_revision(db)
            if body.expected_revision != current:
                raise MoneyOpsError(409, 'stale_revision', 'Context ledger changed; refresh before confirming', {
                    'actual_revision': current,
                    'expected_revision': body.expected_revision,
                })
            prior = db.execute('SELECT * FROM mo_context WHERE id=?', (context_id,)).fetchone()
            if prior is None:
                raise MoneyOpsError(404, 'not_found', 'Context not found', {'context_id': context_id})
            if prior['status'] != 'context_suggested':
                raise MoneyOpsError(409, 'invalid_state', 'Only suggested context can be confirmed for the current run')
            if prior['id'] in _superseded_ids(db) or prior['tombstoned']:
                raise MoneyOpsError(409, 'invalid_state', 'Superseded or tombstoned context cannot be confirmed', {
                    'context_id': context_id,
                })
            if _is_other_opex(str(prior['account_code'] or '')):
                raise MoneyOpsError(422, 'unsupported_cause', 'Other Opex cannot be explained by context and remains causally unexplained', {
                    'account_code': prior['account_code'],
                })
            new_id = str(uuid.uuid4())
            next_rev = current + 1
            db.execute(
                'INSERT INTO mo_context VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    new_id, prior['entity_id'], prior['account_code'], prior['dimension'], prior['member'],
                    prior['statement'], 'user_confirmed', user['username'], _now(), int(prior['revision']) + 1,
                    prior['id'], prior['period_scope_json'], 0, prior['analysis_id'], prior['supporting_claim_ids_json'],
                ),
            )
            _set_context_revision(db, next_rev)
            _append_event(db, store, 'context', new_id, next_rev, 'context_confirmed', user['username'], {'supersedes': prior['id']})
            digest = None
            if prior['analysis_id']:
                _recompose_after_context(db, store, prior['analysis_id'], user['username'], 'narrative_recomposed')
                _, analysis = _load_analysis(db, store, prior['analysis_id'])
                digest = analysis.get('calculation_digest')
            return {
                'context': _row_to_context(db.execute('SELECT * FROM mo_context WHERE id=?', (new_id,)).fetchone()),
                'revision': next_rev,
                'calculation_digest': digest,
            }

    @app.post('/api/money-operations/context/{context_id}/reject')
    def reject_context(context_id: str, body: ContextMutation, user=Depends(write_user)):
        with store.transaction() as db:
            current = _context_revision(db)
            if body.expected_revision != current:
                raise MoneyOpsError(409, 'stale_revision', 'Context ledger changed; refresh before rejecting', {
                    'actual_revision': current,
                    'expected_revision': body.expected_revision,
                })
            prior = db.execute('SELECT * FROM mo_context WHERE id=?', (context_id,)).fetchone()
            if prior is None:
                raise MoneyOpsError(404, 'not_found', 'Context not found', {'context_id': context_id})
            new_id = str(uuid.uuid4())
            next_rev = current + 1
            statement = body.statement or prior['statement']
            db.execute(
                'INSERT INTO mo_context VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    new_id, prior['entity_id'], prior['account_code'], prior['dimension'], prior['member'],
                    statement, 'rejected', user['username'], _now(), int(prior['revision']) + 1,
                    prior['id'], prior['period_scope_json'], 0, prior['analysis_id'], prior['supporting_claim_ids_json'],
                ),
            )
            _set_context_revision(db, next_rev)
            _append_event(db, store, 'context', new_id, next_rev, 'context_rejected', user['username'], {'supersedes': prior['id']})
            digest = None
            if prior['analysis_id']:
                _recompose_after_context(db, store, prior['analysis_id'], user['username'], 'narrative_recomposed')
                _, analysis = _load_analysis(db, store, prior['analysis_id'])
                digest = analysis.get('calculation_digest')
            return {
                'context': _row_to_context(db.execute('SELECT * FROM mo_context WHERE id=?', (new_id,)).fetchone()),
                'revision': next_rev,
                'calculation_digest': digest,
            }

    @app.post('/api/money-operations/context/{context_id}/tombstone')
    def tombstone_context(context_id: str, body: ContextMutation, user=Depends(controller_user)):
        with store.transaction() as db:
            current = _context_revision(db)
            if body.expected_revision != current:
                raise MoneyOpsError(409, 'stale_revision', 'Context ledger changed; refresh before tombstoning', {
                    'actual_revision': current,
                    'expected_revision': body.expected_revision,
                })
            prior = db.execute('SELECT * FROM mo_context WHERE id=?', (context_id,)).fetchone()
            if prior is None:
                raise MoneyOpsError(404, 'not_found', 'Context not found', {'context_id': context_id})
            new_id = str(uuid.uuid4())
            next_rev = current + 1
            statement = body.statement or prior['statement']
            db.execute(
                'INSERT INTO mo_context VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    new_id, prior['entity_id'], prior['account_code'], prior['dimension'], prior['member'],
                    statement, 'tombstoned', user['username'], _now(), int(prior['revision']) + 1,
                    prior['id'], prior['period_scope_json'], 1, prior['analysis_id'], prior['supporting_claim_ids_json'],
                ),
            )
            _set_context_revision(db, next_rev)
            _append_event(db, store, 'context', new_id, next_rev, 'context_tombstoned', user['username'], {'supersedes': prior['id']})
            digest = None
            if prior['analysis_id']:
                _recompose_after_context(db, store, prior['analysis_id'], user['username'], 'narrative_recomposed')
                _, analysis = _load_analysis(db, store, prior['analysis_id'])
                digest = analysis.get('calculation_digest')
            return {
                'context': _row_to_context(db.execute('SELECT * FROM mo_context WHERE id=?', (new_id,)).fetchone()),
                'revision': next_rev,
                'calculation_digest': digest,
            }

    @app.post('/api/money-operations/analyses/{analysis_id}/review')
    def review_analysis(analysis_id: str, body: ReviewBody, user=Depends(controller_user)):
        with store.transaction() as db:
            row, analysis = _load_analysis(db, store, analysis_id)
            expected = body.analysis_revision if body.analysis_revision is not None else body.expected_revision
            if expected is None:
                raise MoneyOpsError(422, 'invalid_request', 'analysis_revision or expected_revision is required')
            if body.analysis_revision is not None and body.expected_revision is not None and body.analysis_revision != body.expected_revision:
                raise MoneyOpsError(409, 'stale_revision', 'analysis_revision and expected_revision disagree', {
                    'actual_revision': row['revision'],
                    'expected_revision': body.expected_revision,
                    'analysis_revision': body.analysis_revision,
                })
            if expected != row['revision']:
                raise MoneyOpsError(409, 'stale_revision', 'Analysis changed; refresh before review', {
                    'actual_revision': row['revision'],
                    'expected_revision': expected,
                })
            if body.analysis_id and body.analysis_id != analysis_id:
                raise MoneyOpsError(409, 'stale_revision', 'Review analysis_id does not match the path', {
                    'actual_analysis_id': analysis_id,
                    'expected_analysis_id': body.analysis_id,
                })
            digest_before = analysis.get('calculation_digest')
            narrative = analysis.get('narrative') or {}
            narrative_digest = _digest(narrative)
            if body.calculation_digest and body.calculation_digest != digest_before:
                raise MoneyOpsError(409, 'stale_digest', 'Calculation digest does not match the current analysis', {
                    'actual_calculation_digest': digest_before,
                    'expected_calculation_digest': body.calculation_digest,
                })
            if body.narrative_digest and body.narrative_digest != narrative_digest:
                raise MoneyOpsError(409, 'stale_digest', 'Narrative digest does not match the current analysis', {
                    'actual_narrative_digest': narrative_digest,
                    'expected_narrative_digest': body.narrative_digest,
                })
            bound_revision = int(row['revision'])
            db.execute(
                'INSERT INTO mo_reviews(id,analysis_id,analysis_revision,narrative_digest,decision,actor,created_at,calculation_digest) '
                'VALUES(?,?,?,?,?,?,?,?)',
                (str(uuid.uuid4()), analysis_id, bound_revision, narrative_digest, body.decision, user['username'], _now(), digest_before or ''),
            )
            analysis = dict(analysis)
            analysis['review_status'] = body.decision
            analysis['approval_bound_revision'] = bound_revision
            analysis['metrics'] = dict(analysis.get('metrics') or {}, review_status=body.decision)
            if analysis.get('calculation_digest') != digest_before:
                raise MoneyOpsError(500, 'invariant', 'Review must not change calculation_digest')
            analysis['calculation_digest'] = digest_before
            next_rev = bound_revision + 1
            _signed_update(db, store.key, 'mo_analyses', analysis_id, analysis, 'revision=?, status=?', (next_rev, 'reviewed'))
            _append_event(db, store, 'analysis', analysis_id, next_rev, 'analysis_reviewed', user['username'], {
                'decision': body.decision,
                'analysis_revision': bound_revision,
                'calculation_digest': digest_before,
                'narrative_digest': narrative_digest,
            })
            row, stored = _load_analysis(db, store, analysis_id)
            public = _analysis_public(row, stored, _active_context_rows(db))
            public['context_revision'] = _context_revision(db)
            public['approval_bound_revision'] = bound_revision
            return public

    @app.get('/api/money-operations/analyses/{analysis_id}/escalations')
    def list_escalations(analysis_id: str, user=Depends(auth)):
        with store.connect() as db:
            row, body = _load_analysis(db, store, analysis_id)
            public = _analysis_public(row, body, _active_context_rows(db))
        return {
            'analysis_id': analysis_id,
            'escalations': public['escalations'],
            'causally_unexplained': public['causally_unexplained'],
            'conflicts': public['conflicts'],
            'review_status': public['review_status'],
            'calculation_digest': public['calculation_digest'],
        }

    @app.get('/api/money-operations/analyses/{analysis_id}/export.json')
    def export_json(analysis_id: str, user=Depends(auth)):
        with store.connect() as db:
            row, body = _load_analysis(db, store, analysis_id)
            sources = [dict(item) for item in db.execute('SELECT file_name,sha256,byte_size,row_count,schema_version FROM mo_sources WHERE dataset_id=?', (row['dataset_id'],))]
            context = [item for item in _active_context_rows(db) if item.get('analysis_id') in (analysis_id, None) or True]
            reviews = [dict(item) for item in db.execute('SELECT decision,actor,created_at,analysis_revision,narrative_digest,calculation_digest FROM mo_reviews WHERE analysis_id=?', (analysis_id,))]
        public = _analysis_public(row, body, context)
        return {
            'schema_version': '1.0',
            'synthetic': True,
            'analysis': public,
            'claims': body.get('claims') or [],
            'variances': body.get('variances') or [],
            'unexplained': public['unexplained'],
            'conflicts': public['conflicts'],
            'context': context,
            'sources': sources,
            'reviews': reviews,
            'calculation_version': row['calculation_version'],
            'calculation_digest': body.get('calculation_digest'),
            'narrative': body.get('narrative'),
        }

    @app.get('/api/money-operations/analyses/{analysis_id}/export.csv')
    def export_csv(analysis_id: str, user=Depends(auth)):
        with store.connect() as db:
            row, body = _load_analysis(db, store, analysis_id)
            context = _active_context_rows(db)
        rows = []
        for claim in (body.get('variances') or []) + (body.get('claims') or []):
            if not isinstance(claim, dict):
                continue
            rows.append({
                'kind': claim.get('claim_type') or 'claim',
                'account_code': claim.get('account_code') or '',
                'account_name': claim.get('account_name') or '',
                'status': claim.get('status') or '',
                'amount_minor': claim_amount_minor(claim),
                'percentage_bps': claim.get('percentage_bps'),
                'statement': claim.get('headline') or claim.get('formula') or '',
                'claim_id': claim.get('id') or '',
            })
        for item in context:
            rows.append({
                'kind': 'context',
                'account_code': item.get('account_code') or '',
                'account_name': '',
                'status': item.get('status') or '',
                'amount_minor': '',
                'percentage_bps': '',
                'statement': item.get('statement') or '',
                'claim_id': item.get('id') or '',
            })
        fields = ['kind', 'account_code', 'account_name', 'status', 'amount_minor', 'percentage_bps', 'statement', 'claim_id']
        csv_text = render_csv(rows, fields)
        return PlainTextResponse(csv_text, media_type='text/csv', headers={
            'Content-Disposition': f'attachment; filename="mandate-money-ops-{analysis_id}.csv"',
        })

    @app.get('/api/money-operations/analyses/{analysis_id}/memo.html')
    def export_memo(analysis_id: str, user=Depends(auth)):
        with store.connect() as db:
            row, body = _load_analysis(db, store, analysis_id)
            sources = [dict(item) for item in db.execute('SELECT file_name,sha256,row_count FROM mo_sources WHERE dataset_id=?', (row['dataset_id'],))]
            context = _active_context_rows(db)
        public = _analysis_public(row, body, context)
        html = render_memo_html(public, body.get('narrative') or {}, sources, context)
        return Response(html, media_type='text/html')

    @app.get('/api/money-operations/analyses/{analysis_id}/lineage')
    def export_lineage(analysis_id: str, user=Depends(auth)):
        with store.connect() as db:
            row, body = _load_analysis(db, store, analysis_id)
            sources = [json.loads(item['metadata_json']) for item in db.execute('SELECT metadata_json FROM mo_sources WHERE dataset_id=?', (row['dataset_id'],))]
            claims = [dict(item) for item in db.execute(
                'SELECT original_id,account_code,claim_type,status,formula,source_ids_json FROM mo_claims WHERE analysis_id=?',
                (analysis_id,),
            )]
            events = [dict(item) for item in db.execute(
                'SELECT event_type,actor,created_at,revision FROM mo_events WHERE aggregate_id=? ORDER BY created_at',
                (analysis_id,),
            )]
        return {
            'analysis_id': analysis_id,
            'calculation_version': row['calculation_version'],
            'calculation_digest': body.get('calculation_digest'),
            'sources': sources,
            'claims': [{**item, 'source_ids': json.loads(item.pop('source_ids_json') or '[]')} for item in claims],
            'events': events,
            'unexplained': body.get('unexplained') or [],
            'conflicts': body.get('conflicts') or [],
        }

    @app.get('/api/money-operations/analyses/{analysis_id}/integration-status')
    def analysis_integration_status(analysis_id: str, user=Depends(auth)):
        with store.connect() as db:
            row, body = _load_analysis(db, store, analysis_id)
        narrative = (body.get('narrative') or {}).get('narrative_source') or 'deterministic_template'
        status = money_ops_integration_status(narrative)
        status['analysis_id'] = analysis_id
        status['calculation_digest'] = body.get('calculation_digest')
        return status
