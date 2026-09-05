"""Deterministic Money Operations narrative templates and citation validation.

A model may phrase validated claims. It cannot invent dollar amounts, change
claim status, or cite unknown IDs. Failed validation falls back to the template.
"""
from __future__ import annotations

import csv
import io
import re
from html import escape

FORMULA_PREFIXES = ('=', '+', '-', '@', '\t')
CURRENCY_RE = re.compile(r'\$\d{1,3}(?:,\d{3})*(?:\.\d+)?|\$\d+(?:\.\d+)?')
PERCENT_RE = re.compile(r'\d+(?:\.\d+)?%')


class NarrativeError(ValueError):
    def __init__(self, code: str, detail):
        super().__init__(code)
        self.code = code
        self.detail = detail


def display_usd(amount_minor: int) -> str:
    sign = '-' if amount_minor < 0 else ''
    dollars, cents = divmod(abs(int(amount_minor)), 100)
    whole = f'{dollars:,}'
    if cents:
        return f'{sign}${whole}.{cents:02d}'
    return f'{sign}${whole}'


def display_pct(bps: int | None) -> str | None:
    if bps is None:
        return None
    whole, frac = divmod(abs(int(bps)), 100)
    sign = '-' if bps < 0 else ''
    if frac % 10 == 0:
        frac = frac // 10
        return f'{sign}{whole}.{frac}%'
    return f'{sign}{whole}.{frac:02d}%'


ACCOUNT_NAMES = {
    '4000': 'Revenue',
    '4100': 'Refunds',
    '5000': 'COGS',
    '6200': 'Software',
    '6300': 'Logistics',
    '6400': 'Payroll',
    '6500': 'Marketing',
    '6900': 'Other Opex',
    'gross_revenue': 'Revenue',
    'software_expense': 'Software',
    'other_opex': 'Other Opex',
}


def claim_value(claim: dict) -> dict:
    value = claim.get('value_json')
    if isinstance(value, dict):
        return value
    value = claim.get('value')
    return value if isinstance(value, dict) else {}


def claim_amount_minor(claim: dict) -> int | None:
    value = claim_value(claim)
    for key in ('amount_minor', 'change_minor', 'absolute_variance_minor', 'delta_minor', 'unexplained_residual_minor'):
        if isinstance(claim.get(key), int):
            return claim[key]
        if isinstance(value.get(key), int):
            return value[key]
    for key in ('absolute_variance_usd', 'delta_usd', 'change_usd'):
        if isinstance(claim.get(key), int):
            return claim[key] * 100
        if isinstance(value.get(key), int):
            return value[key] * 100
    return None


def claim_bps(claim: dict) -> int | None:
    value = claim_value(claim)
    for key in ('percentage_bps', 'percentage_variance_bps', 'share_bps', 'change_bps'):
        if isinstance(claim.get(key), int):
            return claim[key]
        if isinstance(value.get(key), int):
            return value[key]
    pct = claim.get('change_pct', value.get('change_pct'))
    if isinstance(pct, int):
        return pct * 10000 if abs(pct) <= 10 else pct
    if isinstance(pct, float):
        return int(round(pct * 10000))
    return None


def claim_entities(claim: dict) -> list[str]:
    names: list[str] = []
    value = claim_value(claim)
    for key in ('entities', 'customer_ids', 'named_entities', 'member_labels'):
        items = claim.get(key) or value.get(key) or []
        if isinstance(items, list):
            names.extend(str(item) for item in items if isinstance(item, (str, int)))
    for key in ('account_name', 'member', 'member_label', 'dimension_member', 'headline'):
        item = claim.get(key, value.get(key) if key != 'account_name' else None)
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
    code = str(claim.get('account_code') or '')
    if ACCOUNT_NAMES.get(code):
        names.append(ACCOUNT_NAMES[code])
    if isinstance(claim.get('account_name'), str) and claim['account_name'].strip():
        names.append(claim['account_name'].strip())
    return list(dict.fromkeys(name for name in names if name))


def _number_tokens(claim: dict) -> set[str]:
    tokens: set[str] = set()
    amount = claim_amount_minor(claim)
    if amount is not None:
        tokens.add(display_usd(amount))
        tokens.add(display_usd(abs(amount)))
        dollars = abs(amount) // 100
        tokens.add(f'${dollars:,}')
        tokens.add(f'${dollars}')
        tokens.add(str(dollars))
        tokens.add(f'{dollars:,}')
    bps = claim_bps(claim)
    rendered = display_pct(bps) if bps is not None else None
    if rendered:
        tokens.add(rendered)
        tokens.add(rendered.lstrip('-'))
    for key in ('display_amount', 'display_pct', 'headline'):
        value = claim.get(key)
        if isinstance(value, str):
            tokens.update(CURRENCY_RE.findall(value))
            tokens.update(PERCENT_RE.findall(value))
    return tokens


def collect_allowed_numbers(claims: list[dict]) -> set[str]:
    allowed: set[str] = set()
    for claim in claims:
        allowed.update(_number_tokens(claim))
    return allowed


def validate_narrative(text: str, claims: list[dict], cited_ids: list[str]) -> dict:
    """Every currency/percentage in prose must map to a cited claim; unknown IDs fail."""
    by_id = {claim['id']: claim for claim in claims if isinstance(claim.get('id'), str)}
    unknown = [cid for cid in cited_ids if cid not in by_id]
    if unknown:
        raise NarrativeError('unknown_claim_ids', unknown)
    cited = [by_id[cid] for cid in cited_ids]
    allowed = collect_allowed_numbers(cited)
    for token in CURRENCY_RE.findall(text) + PERCENT_RE.findall(text):
        if token not in allowed and token.lstrip('-') not in allowed:
            raise NarrativeError('uncited_number', token)
    catalog: list[str] = []
    for claim in claims:
        catalog.extend(claim_entities(claim))
    catalog = sorted({name for name in catalog if len(name) > 2}, key=len, reverse=True)
    cited_names = {name.lower() for claim in cited for name in claim_entities(claim)}
    haystack = text.lower()
    for name in catalog:
        needle = name.lower()
        if needle not in haystack or needle in cited_names:
            continue
        if any(needle != cited and needle in cited for cited in cited_names):
            continue
        if re.search(r'(?<![A-Za-z0-9])' + re.escape(name) + r'(?![A-Za-z0-9])', text, re.I):
            raise NarrativeError('uncited_entity', name)
    return {'valid': True, 'cited_claim_ids': list(cited_ids)}


def _match_claim(claims: list[dict], *, ids=(), accounts=(), statuses=(), types=(), entities=()) -> dict | None:
    for claim in claims:
        cid = str(claim.get('id', ''))
        account = str(claim.get('account_code') or claim.get('account_name') or '').lower()
        status = str(claim.get('status') or '').lower()
        ctype = str(claim.get('claim_type') or '').lower()
        names = {name.lower() for name in claim_entities(claim)}
        if ids and cid not in ids and not any(cid.endswith(item) for item in ids):
            continue
        if accounts and not any(token in account for token in accounts):
            continue
        if statuses and status not in statuses:
            continue
        if types and ctype not in types:
            continue
        if entities and not any(token.lower() in names for token in entities):
            continue
        return claim
    return None


def deterministic_template(claims: list[dict]) -> dict:
    """Controller-grade prose built only from structured claims. Never guesses Other Opex."""
    revenue = (
        _match_claim(claims, ids=('VAR-REV', 'claim-revenue-change', 'claim-4000-absolute-variance'))
        or _match_claim(claims, accounts=('4000', 'gross_revenue', 'revenue'), types=('absolute_variance', 'variance'))
        or _match_claim(claims, accounts=('4000', 'gross_revenue', 'revenue'))
    )
    revenue_pct = (
        _match_claim(claims, ids=('claim-4000-percentage-variance',))
        or _match_claim(claims, accounts=('4000',), types=('percentage_variance',))
    )
    enterprise = (
        _match_claim(claims, ids=('DRV-ENT', 'claim-enterprise-delta', 'claim-4000-driver-segment-Enterprise'))
        or _match_claim(claims, entities=('Enterprise',), types=('driver_delta', 'driver'))
        or _match_claim(claims, entities=('Enterprise',))
    )
    top3 = (
        _match_claim(claims, ids=('DRV-TOP3', 'claim-top3', 'claim-4000-top3-customers'))
        or _match_claim(claims, entities=('Northstar Commerce',))
    )
    opex = (
        _match_claim(claims, ids=('VAR-UNK', 'claim-other-opex', 'claim-6900-absolute-variance'))
        or _match_claim(claims, accounts=('6900', 'other_opex', 'other opex'), types=('absolute_variance', 'variance'))
        or _match_claim(claims, statuses=('unexplained',), accounts=('6900', 'other_opex', 'other opex'))
        or _match_claim(claims, statuses=('unexplained',))
    )
    software = (
        _match_claim(claims, ids=('VAR-SW', 'claim-6200-absolute-variance'))
        or _match_claim(claims, accounts=('6200', 'software'), types=('absolute_variance', 'variance'))
        or _match_claim(claims, accounts=('6200', 'software'))
    )
    sentences: list[str] = []
    cited: list[str] = []
    headline = 'Period comparison drafted from deterministic claims.'

    def add(claim: dict | None, text: str, extra: list[dict] | None = None):
        if claim is None and not extra:
            return
        sentences.append(text)
        for item in [claim, *(extra or [])]:
            if item is not None and item.get('id'):
                cited.append(item['id'])

    if revenue is not None:
        amount = display_usd(abs(claim_amount_minor(revenue) or 0))
        pct = display_pct(claim_bps(revenue_pct or revenue))
        direction = str(revenue.get('direction') or claim_value(revenue).get('direction') or 'increase')
        if pct and direction == 'increase':
            headline = f'Gross revenue increased {pct} ({amount}).'
            add(revenue, f'Gross revenue increased {pct}, or {amount}.', [revenue_pct] if revenue_pct else [])
        elif pct and direction == 'decrease':
            headline = f'Gross revenue decreased {pct} ({amount}).'
            add(revenue, f'Gross revenue decreased {pct}, or {amount}.', [revenue_pct] if revenue_pct else [])
        else:
            headline = f'Gross revenue changed {amount}.'
            add(revenue, f'Gross revenue changed {amount}.', [revenue_pct] if revenue_pct else [])
    offsets = [
        claim for claim in claims
        if str(claim_value(claim).get('classification') or claim.get('classification') or '').lower() == 'offset'
    ]
    if enterprise is not None:
        ent_share = claim_value(enterprise).get('share_bps')
        ent_amt = display_usd(abs(claim_amount_minor(enterprise) or 0))
        if offsets or (isinstance(ent_share, int) and abs(ent_share) > 10_000):
            add(enterprise, f'Enterprise customers contributed {ent_amt} of the net account variance.')
        else:
            add(enterprise, f'Enterprise customers contributed {ent_amt} of the increase.')
        for off in offsets:
            member = (
                claim_value(off).get('member')
                or next((name for name in claim_entities(off) if name not in ('Revenue', 'Enterprise')), None)
                or 'an offsetting segment'
            )
            add(off, f'That contribution was partially offset by {member} ({display_usd(abs(claim_amount_minor(off) or 0))}).')
    if top3 is not None:
        names = [name for name in claim_entities(top3) if name not in ('Revenue', 'Enterprise') and not re.fullmatch(r'C\d+', name)]
        if len(names) >= 3:
            who = f'{names[0]}, {names[1]}, and {names[2]}'
        elif names:
            who = ', '.join(names)
        else:
            who = 'Three named customers'
        value = claim_value(top3)
        share_bps = value.get('share_bps') if isinstance(value.get('share_bps'), int) else claim_bps(top3)
        share = display_pct(share_bps) if share_bps is not None else None
        contrib = display_usd(abs(claim_amount_minor(top3) or 0))
        if share and isinstance(share_bps, int) and abs(share_bps) > 10_000:
            add(top3, f'{who} contributed {contrib}, equal to {share} of net account variance.')
        elif share:
            add(top3, f'{who} contributed {contrib}, equal to {share} of total growth.')
        else:
            add(top3, f'{who} contributed {contrib} of total growth.')
    if software is not None:
        add(software, f'Software expense changed {display_usd(abs(claim_amount_minor(software) or 0))}. Prior approved ERP context may apply after current-run confirmation.')
    if opex is not None:
        amount = display_usd(abs(claim_amount_minor(opex) or 0))
        extras = [claim for claim in claims if str(claim.get('status', '')).lower() == 'unexplained']
        add(
            opex,
            f'Other Opex increased {amount} through an unmapped clearing batch. '
            'The amount reconciles to the summary, but the source data does not establish its business cause. '
            'Finance review is required before causal attribution.',
            extras,
        )
        if 'unexplained' not in headline.lower() and 'other opex' not in headline.lower():
            headline = headline.rstrip('.') + f'; Other Opex {amount} remains unexplained.'
    conflicts = [claim for claim in claims if str(claim.get('status', '')).lower() == 'conflict']
    for claim in conflicts:
        add(claim, f"Conflict recorded for {claim.get('account_name') or claim.get('account_code')}: source totals disagree.")
        if 'conflict' not in headline.lower():
            headline = headline.rstrip('.') + '; conflicts remain visible.'

    unique_cited = list(dict.fromkeys(cited))
    body = ' '.join(sentences) if sentences else 'No material claims were available to phrase.'
    package = {
        'headline': headline,
        'text': body,
        'body': body,
        'cited_claim_ids': unique_cited,
        'why': [{'text': sentences[i], 'claim_ids': [unique_cited[i]]} for i in range(min(len(sentences), len(unique_cited)))] if unique_cited else [],
        'offsets': [],
        'context': [],
        'unexplained_residual_minor': claim_amount_minor(opex) if opex is not None else 0,
        'review_status': 'draft',
        'mode': 'deterministic_template',
        'narrative_source': 'deterministic_template',
    }
    validate_narrative(body, claims, unique_cited)
    return package


def try_model_compose(package: dict) -> dict | None:
    """Optional hook for a thin composer. Default: do not call a model."""
    return None


def compose(package: dict) -> dict:
    """Phrase a structured evidence package. Never send raw dollar invention to a model."""
    claims = list(package.get('claims') or [])
    template = deterministic_template(claims)
    try:
        draft = try_model_compose(package)
        if draft is None:
            return template
        text = draft.get('text') or draft.get('body') or draft.get('headline') or ''
        cited = list(draft.get('cited_claim_ids') or [])
        validate_narrative(text, claims, cited)
        return {
            **template,
            **draft,
            'text': text,
            'body': text,
            'cited_claim_ids': cited,
            'mode': draft.get('mode', 'model'),
            'narrative_source': 'model',
        }
    except (NarrativeError, TypeError, KeyError, ValueError, RuntimeError):
        return dict(template, model_error='validation_or_provider_failed', narrative_source='deterministic_template')


def neutralize_csv_cell(value) -> str:
    text = '' if value is None else str(value)
    if text.startswith(FORMULA_PREFIXES):
        text = "'" + text
    return text


def render_csv(rows: list[dict], fieldnames: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction='ignore', lineterminator='\n')
    writer.writeheader()
    for row in rows:
        writer.writerow({key: neutralize_csv_cell(row.get(key, '')) for key in fieldnames})
    return buffer.getvalue()


def render_memo_html(analysis: dict, narrative: dict, sources: list[dict], context: list[dict]) -> str:
    periods = analysis.get('periods') or {}
    metrics = analysis.get('metrics') or {}
    unexplained = analysis.get('unexplained') or []
    conflicts = analysis.get('conflicts') or []

    def li(items):
        if not items:
            return '<li>None</li>'
        return ''.join(f'<li>{escape(str(item))}</li>' for item in items)

    source_lines = [
        f"{item.get('file_name', '')} sha256={item.get('sha256', '')[:16]}… rows={item.get('row_count', '')}"
        for item in sources
    ]
    context_lines = [
        f"{item.get('account_code')} [{item.get('status')}] rev={item.get('revision')} — {item.get('statement')}"
        for item in context
    ]
    unexplained_lines = [
        f"{item.get('account_name') or item.get('account_code')}: {display_usd(abs(claim_amount_minor(item) or 0))} unexplained"
        for item in unexplained
    ]
    conflict_lines = [
        f"{item.get('account_name') or item.get('account_code')}: conflict"
        for item in conflicts
    ]
    decision_lines = [
        f"Review status: {metrics.get('review_status', 'draft')}",
        f"Material variances: {metrics.get('material_variances', 0)}",
    ]
    return (
        '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
        '<title>Mandate Money Operations memo</title></head><body>'
        f'<h1>{escape(str(analysis.get("entity_name") or "Yari Technology Retail"))}</h1>'
        f'<p>Periods {escape(str(periods.get("prior", "")))} → {escape(str(periods.get("current", "")))}. '
        f'Calculation {escape(str(analysis.get("calculation_version", "")))}.</p>'
        f'<h2>{escape(str(narrative.get("headline") or ""))}</h2>'
        f'<p>{escape(str(narrative.get("text") or narrative.get("body") or ""))}</p>'
        f'<h3>Decision points</h3><ul>{li(decision_lines)}</ul>'
        f'<h3>Unresolved / unexplained</h3><ul>{li(unexplained_lines)}</ul>'
        f'<h3>Conflicts</h3><ul>{li(conflict_lines)}</ul>'
        f'<h3>Context</h3><ul>{li(context_lines)}</ul>'
        f'<h3>Source manifest</h3><ul>{li(source_lines)}</ul>'
        f'<p>Digest {escape(str(analysis.get("calculation_digest") or ""))}. Synthetic data only.</p>'
        '</body></html>'
    )
