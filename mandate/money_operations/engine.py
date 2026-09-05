"""Deterministic Money Operations calculation and evidence engine."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .config import LABEL_FIELDS, UNCLASSIFIED
from .ingest import DatasetValidationError, LoadedDataset, load_dataset
from .integer import minor_to_usd, percentage_variance_bps, share_bps

CALCULATION_VERSION = 'mo-calc-1.0'

_SLUG_RE = re.compile(r'[^A-Za-z0-9]+')
FAVORABILITY = {
    'revenue': {'increase': 'favorable', 'decrease': 'unfavorable', 'flat': 'neutral'},
    'contra_revenue': {'increase': 'unfavorable', 'decrease': 'favorable', 'flat': 'neutral'},
    'expense': {'increase': 'unfavorable', 'decrease': 'favorable', 'flat': 'neutral'},
}


def validate_dataset(path: str | Path) -> dict:
    """Validate packaged CSVs/JSON. Returns sources, findings, available_periods."""
    dataset = load_dataset(path, enforce_manifest_hashes=True)
    return {
        'status': 'validated' if dataset.valid else 'invalid',
        'sources': dataset.sources,
        'findings': dataset.findings,
        'available_periods': dataset.available_periods,
    }


def analyze(path: str | Path, prior_period: str, current_period: str,
            entity_id: str = 'yari-retail-us') -> dict:
    """Run the full deterministic comparison. JSON-serializable analysis dict."""
    dataset = load_dataset(path, enforce_manifest_hashes=False)
    if not dataset.valid:
        raise DatasetValidationError('dataset failed closed validation', dataset.findings)
    if prior_period not in dataset.summaries or current_period not in dataset.summaries:
        raise DatasetValidationError(
            f'periods {prior_period!r} and {current_period!r} must exist in monthly summaries',
            [_period_finding(dataset, prior_period, current_period)],
        )
    if prior_period >= current_period:
        raise DatasetValidationError(
            'prior_period must be earlier than current_period',
            [{
                'code': 'invalid_period_order',
                'severity': 'error',
                'message': 'prior_period must be earlier than current_period',
                'details': {'prior_period': prior_period, 'current_period': current_period},
            }],
        )

    accounts: dict[str, dict] = {}
    claims: list[dict] = []
    for account_cfg in dataset.config['accounts']:
        built = _analyze_account(dataset, account_cfg, prior_period, current_period, entity_id)
        accounts[account_cfg['account_code']] = built
        claims.extend(built['claims'])

    variances = [accounts[code]['variance'] for code in accounts]
    _rank_variances(variances, dataset.config['materiality'])
    for variance in variances:
        accounts[variance['account_code']]['variance'] = variance

    claims.sort(key=lambda item: (item['account_code'], item['id']))
    analysis = {
        'calculation_version': CALCULATION_VERSION,
        'calculation_digest': _calculation_digest(claims),
        'entity_id': entity_id,
        'prior_period': prior_period,
        'current_period': current_period,
        'currency': dataset.config.get('currency', 'USD'),
        'variances': variances,
        'accounts': accounts,
        'claims': claims,
        'sources': dataset.sources,
        'findings': dataset.findings,
    }
    return analysis


def compare_periods(path: str | Path, prior_period: str, current_period: str,
                    entity_id: str = 'yari-retail-us') -> dict:
    """Account-level variances only."""
    analysis = analyze(path, prior_period, current_period, entity_id)
    return {
        'calculation_version': analysis['calculation_version'],
        'calculation_digest': analysis['calculation_digest'],
        'entity_id': analysis['entity_id'],
        'prior_period': analysis['prior_period'],
        'current_period': analysis['current_period'],
        'currency': analysis['currency'],
        'variances': analysis['variances'],
    }


def attribute_drivers(analysis: dict, account_code: str) -> dict:
    """Primary/alternative dimension drivers for one account."""
    return _account(analysis, account_code)['drivers']


def reconcile_account(analysis: dict, account_code: str) -> dict:
    """Per-period and cross-period reconciliation for one account."""
    return _account(analysis, account_code)['reconciliation']


def _account(analysis: dict, account_code: str) -> dict:
    accounts = analysis['accounts']
    if isinstance(accounts, dict):
        if account_code not in accounts:
            raise KeyError(account_code)
        return accounts[account_code]
    for item in accounts:
        if item['account_code'] == account_code:
            return item
    raise KeyError(account_code)


def _period_finding(dataset: LoadedDataset, prior_period: str, current_period: str) -> dict:
    return {
        'code': 'invalid_period',
        'severity': 'error',
        'message': f'requested periods not available: {prior_period}, {current_period}',
        'details': {'available_periods': dataset.available_periods},
    }


def _analyze_account(dataset: LoadedDataset, account_cfg: dict, prior_period: str,
                     current_period: str, entity_id: str) -> dict:
    code = account_cfg['account_code']
    column = account_cfg['summary_column']
    prior_summary = dataset.summaries[prior_period]
    current_summary = dataset.summaries[current_period]
    prior_minor = prior_summary['amounts_minor'][column]
    current_minor = current_summary['amounts_minor'][column]
    absolute_variance = current_minor - prior_minor
    pct_bps, pct_state = percentage_variance_bps(absolute_variance, prior_minor)
    direction = _direction(absolute_variance)
    account_type = account_cfg['account_type']
    favorability = FAVORABILITY.get(account_type, {}).get(direction, 'context_required')

    prior_txns = dataset.transactions_for(code, prior_period)
    current_txns = dataset.transactions_for(code, current_period)
    prior_detail = sum(txn['amount_minor'] for txn in prior_txns)
    current_detail = sum(txn['amount_minor'] for txn in current_txns)
    detail_variance = current_detail - prior_detail
    tolerance = int(dataset.config.get('reconciliation_tolerance_minor', 1))
    reconciliation = _reconcile(
        prior_minor, current_minor, prior_detail, current_detail,
        absolute_variance, detail_variance, tolerance, prior_txns, current_txns,
    )

    dimensions = _attribute_all_dimensions(
        account_cfg, dataset.config.get('driver_selection') or {},
        prior_txns, current_txns, absolute_variance, detail_variance,
    )
    primary = dimensions[0] if dimensions else _empty_dimension(account_cfg['analysis_dimensions'][0])
    alternatives = dimensions[1:]
    causal = _causal_block(account_cfg, primary, reconciliation, absolute_variance)

    variance = {
        'account_code': code,
        'account_name': account_cfg['account_name'],
        'account_type': account_type,
        'prior_minor': prior_minor,
        'current_minor': current_minor,
        'absolute_variance_minor': absolute_variance,
        'absolute_variance_usd': minor_to_usd(absolute_variance),
        'percentage_variance_bps': pct_bps,
        'percentage_state': pct_state,
        'direction': direction,
        'favorability': favorability,
        'materiality': 'threshold_material',
        'rank': 0,
        'currency': dataset.config.get('currency', 'USD'),
    }
    if code == '6400':
        variance['headcount_prior'] = prior_summary['headcount']
        variance['headcount_current'] = current_summary['headcount']
        variance['headcount_change'] = current_summary['headcount'] - prior_summary['headcount']

    context = [
        entry for entry in dataset.context_entries
        if entry.get('account_code') == code
        and (entry.get('effective_period') in {None, current_period} or not entry.get('effective_period'))
    ]
    claims = _build_claims(
        dataset, account_cfg, variance, primary, alternatives, reconciliation, causal,
        prior_txns, current_txns, prior_period, current_period, context,
    )
    drivers = {
        'primary_dimension': primary['dimension'],
        'primary': primary,
        'alternatives': alternatives,
    }
    built = {
        'account_code': code,
        'account_name': account_cfg['account_name'],
        'account_type': account_type,
        'entity_id': entity_id,
        'variance': variance,
        'detail': {
            'prior_minor': prior_detail,
            'current_minor': current_detail,
            'variance_minor': detail_variance,
        },
        'drivers': drivers,
        'reconciliation': reconciliation,
        'causal': causal,
        'context': context,
        'claims': claims,
    }
    if code == '6400':
        built['headcount'] = {
            'prior': prior_summary['headcount'],
            'current': current_summary['headcount'],
            'change': current_summary['headcount'] - prior_summary['headcount'],
        }
    return built


def _direction(absolute_variance: int) -> str:
    if absolute_variance > 0:
        return 'increase'
    if absolute_variance < 0:
        return 'decrease'
    return 'flat'


def _reconcile(prior_summary: int, current_summary: int, prior_detail: int, current_detail: int,
               absolute_variance: int, detail_variance: int, tolerance: int,
               prior_txns: list[dict], current_txns: list[dict]) -> dict:
    prior_diff = prior_summary - prior_detail
    current_diff = current_summary - current_detail
    variance_diff = absolute_variance - detail_variance
    prior_ok = abs(prior_diff) <= tolerance
    current_ok = abs(current_diff) <= tolerance
    variance_ok = abs(variance_diff) <= tolerance
    has_prior = bool(prior_txns)
    has_current = bool(current_txns)
    if not has_prior and not has_current:
        if prior_summary == 0 and current_summary == 0:
            status = 'reconciled'
        else:
            status = 'unavailable'
    elif (not has_prior or not has_current) and (prior_ok if has_prior else True) and (current_ok if has_current else True):
        status = 'partial'
    elif prior_ok and current_ok and variance_ok:
        status = 'reconciled'
    else:
        status = 'conflict'
    unexplained = 0 if status == 'reconciled' else variance_diff
    coverage = share_bps(abs(detail_variance), max(1, abs(absolute_variance)))
    if coverage is not None and coverage > 10_000:
        coverage = 10_000
    return {
        'status': status,
        'tolerance_minor': tolerance,
        'prior': {
            'summary_minor': prior_summary,
            'detail_minor': prior_detail,
            'difference_minor': prior_diff,
            'reconciled': prior_ok,
            'row_count': len(prior_txns),
        },
        'current': {
            'summary_minor': current_summary,
            'detail_minor': current_detail,
            'difference_minor': current_diff,
            'reconciled': current_ok,
            'row_count': len(current_txns),
        },
        'detail_variance_minor': detail_variance,
        'absolute_variance_minor': absolute_variance,
        'variance_reconciliation_difference_minor': variance_diff,
        'unexplained_residual_minor': unexplained,
        'data_coverage_bps': coverage if absolute_variance != 0 else (0 if detail_variance == 0 else None),
    }


def _empty_dimension(name: str) -> dict:
    return {
        'dimension': name,
        'score': 0,
        'directional_coverage_bps': 0,
        'concentration_bps': 0,
        'unclassified_penalty_bps': 0,
        'members': [],
        'selected_drivers': [],
        'offsets': [],
        'selected_directional_coverage_bps': 0,
    }


def _attribute_all_dimensions(account_cfg: dict, selection: dict, prior_txns: list[dict],
                              current_txns: list[dict], absolute_variance: int,
                              detail_variance: int) -> list[dict]:
    scored = []
    for dimension in account_cfg['analysis_dimensions']:
        scored.append(_attribute_dimension(
            account_cfg, dimension, selection, prior_txns, current_txns,
            absolute_variance, detail_variance,
        ))
    scored.sort(key=lambda item: (-item['score'], account_cfg['analysis_dimensions'].index(item['dimension'])))
    return scored


def _attribute_dimension(account_cfg: dict, dimension: str, selection: dict,
                         prior_txns: list[dict], current_txns: list[dict],
                         absolute_variance: int, detail_variance: int) -> dict:
    members: dict[str, dict] = {}
    label_field = LABEL_FIELDS.get(dimension)

    def add(txns: list[dict], side: str) -> None:
        for txn in txns:
            dims = txn['dimensions']
            member = dims.get(dimension, UNCLASSIFIED)
            label = dims.get(label_field, member) if label_field else member
            bucket = members.setdefault(member, {
                'member': member,
                'member_label': label,
                'prior_minor': 0,
                'current_minor': 0,
                'source_rows': [],
            })
            bucket[f'{side}_minor'] += txn['amount_minor']
            bucket['source_rows'].append({
                'source_id': txn['source_id'],
                'transaction_id': txn['transaction_id'],
                'period': txn['period'],
            })

    add(prior_txns, 'prior')
    add(current_txns, 'current')

    unexplained_members = set((account_cfg.get('causal_unexplained_members') or {}).get(dimension, []))
    rows = []
    abs_member_sum = 0
    for member, bucket in members.items():
        delta = bucket['current_minor'] - bucket['prior_minor']
        abs_member_sum += abs(delta)
        classification = _classification(delta, detail_variance if detail_variance != 0 else absolute_variance)
        share = share_bps(delta, absolute_variance)
        member_pct, member_state = percentage_variance_bps(delta, bucket['prior_minor'])
        source_rows = sorted(bucket['source_rows'], key=lambda item: (item['period'], item['transaction_id']))
        rows.append({
            'member': member,
            'member_label': bucket['member_label'],
            'prior_minor': bucket['prior_minor'],
            'current_minor': bucket['current_minor'],
            'delta_minor': delta,
            'delta_usd': minor_to_usd(delta),
            'share_bps': share,
            'percentage_variance_bps': member_pct,
            'percentage_state': member_state,
            'classification': classification,
            'causal_unexplained': member in unexplained_members,
            'selected': False,
            'source_rows': source_rows,
        })
    rows.sort(key=lambda item: (-abs(item['delta_minor']), item['member']))

    same_dir = [row for row in rows if row['classification'] == 'contributor' and not row['causal_unexplained']]
    coverage_num = sum(abs(row['delta_minor']) for row in same_dir)
    directional_coverage = _capped_share(coverage_num, abs(absolute_variance) if absolute_variance else abs(detail_variance))
    largest = max((abs(row['delta_minor']) for row in rows), default=0)
    concentration = _capped_share(largest, abs_member_sum)
    unclassified = next((abs(row['delta_minor']) for row in rows if row['member'] == UNCLASSIFIED), 0)
    penalty = _capped_share(unclassified, max(1, abs_member_sum))
    score = directional_coverage + concentration // 4 - penalty // 2

    selected, offsets, selected_coverage = _select_drivers(rows, selection, absolute_variance)
    return {
        'dimension': dimension,
        'score': score,
        'directional_coverage_bps': directional_coverage,
        'concentration_bps': concentration,
        'unclassified_penalty_bps': penalty,
        'members': rows,
        'selected_drivers': selected,
        'offsets': offsets,
        'selected_directional_coverage_bps': selected_coverage,
    }


def _classification(delta: int, account_variance: int) -> str:
    if delta == 0:
        return 'neutral'
    if account_variance == 0:
        return 'contributor' if delta != 0 else 'neutral'
    if (delta > 0) == (account_variance > 0):
        return 'contributor'
    return 'offset'


def _capped_share(part: int, whole: int) -> int:
    if whole == 0:
        return 0
    value = share_bps(part, whole) or 0
    return 10_000 if value > 10_000 else value


def _select_drivers(rows: list[dict], selection: dict, absolute_variance: int) -> tuple[list[dict], list[dict], int]:
    min_minor = int(selection.get('minimum_contribution_minor', 1_000_000))
    min_share = int(selection.get('minimum_share_bps', 1000))
    target = int(selection.get('target_directional_coverage_bps', 8000))
    maximum = int(selection.get('maximum_drivers', 5))
    contributors = [
        row for row in rows
        if row['classification'] == 'contributor' and not row['causal_unexplained']
    ]
    selected: list[dict] = []
    covered = 0
    for row in contributors:
        share_abs = abs(row['share_bps'] or 0)
        if abs(row['delta_minor']) < min_minor and share_abs < min_share:
            continue
        row['selected'] = True
        selected.append(row)
        covered = _capped_share(sum(abs(item['delta_minor']) for item in selected), max(1, abs(absolute_variance)))
        if covered >= target or len(selected) >= maximum:
            break
    offset_rows = [
        row for row in rows
        if row['classification'] == 'offset' and not row['causal_unexplained']
    ]
    offsets = offset_rows[:2]
    for row in offsets:
        row['selected'] = True
    return selected, offsets, covered


def _causal_block(account_cfg: dict, primary: dict, reconciliation: dict, absolute_variance: int) -> dict:
    unexplained_members = [
        row for row in primary['members']
        if row.get('causal_unexplained')
    ]
    unexplained_minor = sum(row['delta_minor'] for row in unexplained_members)
    if account_cfg['account_code'] == '6900':
        return {
            'status': 'unexplained',
            'explained_minor': 0,
            'unexplained_residual_minor': absolute_variance,
            'note': 'Unmapped clearing batch reconciles numerically; business cause is unsupported.',
        }
    if reconciliation['status'] == 'conflict':
        return {
            'status': 'conflict',
            'explained_minor': absolute_variance - reconciliation['unexplained_residual_minor'],
            'unexplained_residual_minor': reconciliation['unexplained_residual_minor'],
            'note': 'Summary and detail disagree; drivers do not fully explain the summary change.',
        }
    if unexplained_minor != 0 and abs(unexplained_minor) == abs(absolute_variance):
        return {
            'status': 'unexplained',
            'explained_minor': 0,
            'unexplained_residual_minor': unexplained_minor,
            'note': 'Measured change has no supported business cause.',
        }
    return {
        'status': 'reconciled' if reconciliation['status'] == 'reconciled' else reconciliation['status'],
        'explained_minor': absolute_variance - reconciliation['unexplained_residual_minor'],
        'unexplained_residual_minor': reconciliation['unexplained_residual_minor'],
        'note': None,
    }


def _rank_variances(variances: list[dict], materiality: dict) -> None:
    abs_threshold = int(materiality.get('absolute_minor', 2_500_000))
    pct_threshold = int(materiality.get('percentage_bps', 500))
    top_n = int(materiality.get('always_include_top_n', 5))
    for item in variances:
        prior = item['prior_minor']
        pct = item['percentage_variance_bps']
        abs_var = abs(item['absolute_variance_minor'])
        threshold = abs_var >= abs_threshold or (prior != 0 and pct is not None and abs(pct) >= pct_threshold)
        item['materiality'] = 'threshold_material' if threshold else 'excluded'
    nonzero = [item for item in variances if item['absolute_variance_minor'] != 0]
    nonzero.sort(key=lambda item: -abs(item['absolute_variance_minor']))
    for item in nonzero[:top_n]:
        if item['materiality'] == 'excluded':
            item['materiality'] = 'rank_included'

    def sort_key(item: dict) -> tuple:
        material_rank = 0 if item['materiality'] == 'threshold_material' else (1 if item['materiality'] == 'rank_included' else 2)
        pct = item['percentage_variance_bps']
        if pct is None and item['absolute_variance_minor'] != 0:
            pct_key = -10**12
        else:
            pct_key = -(abs(pct) if pct is not None else 0)
        return (material_rank, -abs(item['absolute_variance_minor']), pct_key, item['account_code'])

    variances.sort(key=sort_key)
    for index, item in enumerate(variances, start=1):
        item['rank'] = index


def _slug(value: str) -> str:
    return _SLUG_RE.sub('-', value).strip('-') or 'blank'


def _source_rows(txns: list[dict]) -> list[dict]:
    return sorted(
        (
            {
                'source_id': txn['source_id'],
                'transaction_id': txn['transaction_id'],
                'period': txn['period'],
            }
            for txn in txns
        ),
        key=lambda item: (item['period'], item['transaction_id']),
    )


def _claim(claim_id: str, account_code: str, claim_type: str, status: str, value_json: dict,
           formula: str, source_ids: list[str], source_rows: list[dict]) -> dict:
    return {
        'id': claim_id,
        'account_code': account_code,
        'claim_type': claim_type,
        'status': status,
        'value_json': value_json,
        'formula': formula,
        'source_ids': sorted(set(source_ids)),
        'source_rows': source_rows,
    }


def _build_claims(dataset: LoadedDataset, account_cfg: dict, variance: dict, primary: dict,
                  alternatives: list[dict], reconciliation: dict, causal: dict,
                  prior_txns: list[dict], current_txns: list[dict],
                  prior_period: str, current_period: str, context: list[dict]) -> list[dict]:
    code = account_cfg['account_code']
    summary_source = dataset.summaries[current_period]['source_id']
    txn_sources = sorted({txn['source_id'] for txn in prior_txns + current_txns})
    all_sources = [summary_source, *txn_sources]
    all_rows = _source_rows(prior_txns + current_txns)
    variance_status = 'reconciled' if reconciliation['status'] == 'reconciled' else (
        'conflict' if reconciliation['status'] == 'conflict' else 'computed'
    )
    claims = [
        _claim(
            f'claim-{code}-absolute-variance', code, 'absolute_variance', variance_status,
            {
                'prior_minor': variance['prior_minor'],
                'current_minor': variance['current_minor'],
                'absolute_variance_minor': variance['absolute_variance_minor'],
                'absolute_variance_usd': variance['absolute_variance_usd'],
            },
            'absolute_variance = current_minor - prior_minor',
            all_sources, all_rows,
        ),
        _claim(
            f'claim-{code}-percentage-variance', code, 'percentage_variance',
            'computed' if variance['percentage_state'] == 'new_activity' else variance_status,
            {
                'percentage_variance_bps': variance['percentage_variance_bps'],
                'percentage_state': variance['percentage_state'],
                'prior_minor': variance['prior_minor'],
                'absolute_variance_minor': variance['absolute_variance_minor'],
            },
            'percentage_variance_bps = round_half_away_from_zero(absolute_variance * 10000 / abs(prior_minor))',
            all_sources, all_rows,
        ),
        _claim(
            f'claim-{code}-reconciliation', code, 'reconciliation',
            reconciliation['status'] if reconciliation['status'] in {'reconciled', 'conflict'} else 'computed',
            {
                'status': reconciliation['status'],
                'prior_difference_minor': reconciliation['prior']['difference_minor'],
                'current_difference_minor': reconciliation['current']['difference_minor'],
                'variance_reconciliation_difference_minor': reconciliation['variance_reconciliation_difference_minor'],
                'unexplained_residual_minor': reconciliation['unexplained_residual_minor'],
                'detail_variance_minor': reconciliation['detail_variance_minor'],
            },
            'reconciliation_difference = summary_total - detail_total; variance_reconciliation_difference = absolute_variance - detail_variance',
            all_sources, all_rows,
        ),
        _claim(
            f'claim-{code}-causal', code, 'causal', causal['status'],
            {
                'status': causal['status'],
                'explained_minor': causal['explained_minor'],
                'unexplained_residual_minor': causal['unexplained_residual_minor'],
            },
            'causal residual is independent of numeric reconciliation for unsupported business cause',
            all_sources, all_rows,
        ),
    ]
    for block in [primary, *alternatives]:
        for row in block['members']:
            if row['delta_minor'] == 0 and row['classification'] == 'neutral':
                continue
            claim_status = 'unexplained' if row.get('causal_unexplained') else (
                'computed' if reconciliation['status'] == 'conflict' else variance_status
            )
            claims.append(_claim(
                f"claim-{code}-driver-{_slug(block['dimension'])}-{_slug(row['member'])}",
                code, 'driver_delta', claim_status,
                {
                    'dimension': block['dimension'],
                    'member': row['member'],
                    'member_label': row['member_label'],
                    'prior_minor': row['prior_minor'],
                    'current_minor': row['current_minor'],
                    'delta_minor': row['delta_minor'],
                    'delta_usd': row['delta_usd'],
                    'share_bps': row['share_bps'],
                    'percentage_variance_bps': row['percentage_variance_bps'],
                    'percentage_state': row['percentage_state'],
                    'classification': row['classification'],
                    'primary': block['dimension'] == primary['dimension'],
                },
                'driver_delta = current_driver_amount - prior_driver_amount; driver_share_bps = driver_delta * 10000 / account_absolute_variance',
                txn_sources or all_sources,
                row['source_rows'],
            ))
    if code == '4000':
        customer_dim = next((block for block in [primary, *alternatives] if block['dimension'] == 'customer_id'), None)
        if customer_dim:
            direction = 1 if variance['absolute_variance_minor'] >= 0 else -1
            chosen = sorted(
                (
                    row for row in customer_dim['members']
                    if row['member'] != UNCLASSIFIED and row['delta_minor'] * direction > 0
                ),
                key=lambda item: (-item['delta_minor'] * direction, item['member']),
            )[:3]
            delta = sum(row['delta_minor'] for row in chosen)
            customer_ids = [row['member'] for row in chosen]
            claims.append(_claim(
                'claim-4000-top3-customers', code, 'driver_group', variance_status,
                {
                    'customer_ids': customer_ids,
                    'member_labels': [row['member_label'] for row in chosen],
                    'delta_minor': delta,
                    'delta_usd': minor_to_usd(delta),
                    'share_bps': share_bps(delta, variance['absolute_variance_minor']),
                },
                'top3_delta = sum(three largest customer deltas in the direction of net revenue variance); share_bps = top3_delta * 10000 / revenue_absolute_variance',
                txn_sources,
                sorted((row for member in chosen for row in member['source_rows']),
                       key=lambda item: (item['period'], item['transaction_id'])),
            ))
    if code == '6400':
        claims.append(_claim(
            'claim-6400-headcount', code, 'headcount', 'computed',
            {
                'headcount_prior': variance.get('headcount_prior'),
                'headcount_current': variance.get('headcount_current'),
                'headcount_change': variance.get('headcount_change'),
            },
            'headcount_change = current_headcount - prior_headcount',
            [summary_source],
            [],
        ))
    for entry in context:
        claims.append(_claim(
            f"claim-{code}-context-{entry.get('context_id')}", code, 'context', 'context_suggested',
            {
                'context_id': entry.get('context_id'),
                'statement': entry.get('statement'),
                'seed_status': entry.get('seed_status'),
            },
            'prior-run context is suggested only; it does not change computed amounts',
            [_source_id_from_name('business_context_history.json')],
            [],
        ))
    return claims


def _source_id_from_name(file_name: str) -> str:
    return f'src-{Path(file_name).stem}'


def _calculation_digest(claims: list[dict]) -> str:
    payload = []
    for claim in claims:
        payload.append({
            'id': claim['id'],
            'account_code': claim['account_code'],
            'claim_type': claim['claim_type'],
            'status': claim['status'],
            'value_json': claim['value_json'],
            'formula': claim['formula'],
        })
    payload.sort(key=lambda item: item['id'])
    blob = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()
