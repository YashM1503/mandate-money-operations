"""UI-facing Money Operations serializers and extension routes.

Lead wires register_money_operations_extensions(app, store, auth). These
endpoints read HMAC-signed analyses; they do not recalculate money math.
"""
from __future__ import annotations

from fastapi import Depends
from fastapi.responses import Response
from pydantic import Field

from .money_operations_audio import (
    assert_approved_memo,
    audio_state,
    build_briefing,
    cached_audio,
    narrative_digest,
)
from .money_operations_narrative import (
    ACCOUNT_NAMES,
    claim_amount_minor,
    claim_bps,
    claim_value,
    display_pct,
    display_usd,
)
from .money_operations_prism import prism_status
from .money_operations_service import (
    MoneyOpsError,
    StrictBody,
    _active_context_rows,
    _load_analysis,
    _normalize_account,
    _same_account,
)

GRAPH_NODES = (
    ('compare', 'Compare'),
    ('detect', 'Detect'),
    ('attribute', 'Attribute'),
    ('reconcile', 'Reconcile'),
    ('retrieve_context', 'Retrieve context'),
    ('explain', 'Explain'),
    ('validate', 'Validate'),
    ('human_review', 'Human review'),
)
OTHER_OPEX_TOKENS = {'6900', 'other_opex', 'other opex'}
MUTATION_TERMS = (
    'approve', 'reject', 'release', 'submit', 'distribute', 'delete',
    'overwrite', 'edit the narrative', 'change the numbers', 'post the memo',
)


class ChatBody(StrictBody):
    question: str = Field(min_length=1, max_length=2000)


def _as_int(value) -> int | None:
    if type(value) is int:
        return value
    if type(value) is bool:
        return None
    return None


def _account_name(code: str, fallback: str | None = None) -> str:
    return ACCOUNT_NAMES.get(str(code), fallback or str(code))


def _is_other_opex(account: str) -> bool:
    raw = (account or '').strip().lower()
    return raw in OTHER_OPEX_TOKENS or 'other opex' in raw or raw == 'other_opex'


def _claim_account(claim: dict) -> str:
    return str(claim.get('account_code') or claim.get('account') or '')


def _unexplained_items(body: dict) -> list[dict]:
    items = []
    for claim in body.get('unexplained') or body.get('claims') or []:
        if not isinstance(claim, dict):
            continue
        status = str(claim.get('status') or claim_value(claim).get('status') or '').lower()
        ctype = str(claim.get('claim_type') or '').lower()
        if status == 'unexplained' or ctype == 'causal' and status == 'unexplained':
            items.append(claim)
        elif _is_other_opex(_claim_account(claim)) and ctype == 'causal':
            items.append(claim)
    if items:
        return items
    accounts = body.get('accounts') or {}
    if isinstance(accounts, dict):
        for code, block in accounts.items():
            if not isinstance(block, dict):
                continue
            causal = block.get('causal') or {}
            if str(causal.get('status', '')).lower() == 'unexplained' or _is_other_opex(str(code)):
                items.append({
                    'id': f'causal-{code}',
                    'account_code': code,
                    'account_name': block.get('account_name') or _account_name(str(code)),
                    'status': 'unexplained',
                    'amount_minor': _as_int(causal.get('unexplained_residual_minor'))
                    or _as_int((block.get('variance') or {}).get('absolute_variance_minor')),
                    'unexplained_cause': causal.get('note'),
                })
    return items


def _reconciliation_conflicts(body: dict) -> list[dict]:
    """Numeric source conflicts only. Other Opex is never counted here."""
    conflicts = []
    for claim in body.get('conflicts') or []:
        if not isinstance(claim, dict):
            continue
        if _is_other_opex(_claim_account(claim)) or _is_other_opex(str(claim.get('account_name') or '')):
            continue
        if str(claim.get('status', '')).lower() == 'conflict':
            conflicts.append(claim)
    for claim in body.get('claims') or []:
        if not isinstance(claim, dict):
            continue
        if _is_other_opex(_claim_account(claim)) or _is_other_opex(str(claim.get('account_name') or '')):
            continue
        if str(claim.get('status', '')).lower() == 'conflict' and str(claim.get('claim_type', '')).lower() in (
            'reconciliation', 'absolute_variance', 'variance', 'conflict',
        ):
            if claim not in conflicts:
                conflicts.append(claim)
    accounts = body.get('accounts') or {}
    if isinstance(accounts, dict):
        for code, block in accounts.items():
            if _is_other_opex(str(code)):
                continue
            recon = (block or {}).get('reconciliation') or {}
            if str(recon.get('status', '')).lower() == 'conflict':
                conflicts.append({
                    'account_code': code,
                    'account_name': (block or {}).get('account_name') or _account_name(str(code)),
                    'status': 'conflict',
                    'amount_minor': _as_int(recon.get('variance_reconciliation_difference_minor')),
                })
    return conflicts


def _serialize_conflict(item: dict) -> dict:
    return {
        'account_code': _claim_account(item) or item.get('account_code'),
        'account_name': item.get('account_name') or _account_name(str(_claim_account(item) or '')),
        'status': 'conflict',
        'amount_minor': claim_amount_minor(item),
        'claim_id': item.get('id'),
    }


def _serialize_unexplained(item: dict) -> dict:
    return {
        'account_code': _claim_account(item) or item.get('account_code'),
        'account_name': item.get('account_name') or _account_name(str(_claim_account(item) or ''), 'Other Opex'),
        'status': 'unexplained',
        'amount_minor': claim_amount_minor(item) if claim_amount_minor(item) is not None else _as_int(item.get('amount_minor')),
        'unexplained_cause': item.get('unexplained_cause') or claim_value(item).get('note') or (
            'Unmapped clearing batch reconciles numerically; business cause is unsupported.'
            if _is_other_opex(str(_claim_account(item) or item.get('account_name') or ''))
            else 'Business cause is unsupported.'
        ),
        'claim_id': item.get('id'),
        'owner': 'controller',
        'next_action': 'Finance review is required before causal attribution.',
    }


def _material_variances(body: dict) -> list[dict]:
    items = []
    variances = body.get('variances') or []
    if isinstance(variances, dict):
        variances = list(variances.values())
    if not isinstance(variances, list) or not variances:
        variances = [
            claim for claim in body.get('claims') or []
            if str(claim.get('claim_type', '')).lower() in ('variance', 'absolute_variance', '')
        ]
    for item in variances:
        if not isinstance(item, dict):
            continue
        amount = claim_amount_minor(item)
        if amount is None:
            amount = _as_int(item.get('absolute_variance_minor'))
        if amount is None:
            continue
        material = item.get('materiality') in ('threshold_material', 'rank_included') or abs(amount) >= 2_500_000
        if not material and item.get('material') is not True:
            continue
        code = str(item.get('account_code') or item.get('account') or '')
        items.append({
            'account_code': code,
            'account_name': item.get('account_name') or _account_name(code),
            'amount_minor': amount,
            'percentage_bps': claim_bps(item) if claim_bps(item) is not None else _as_int(item.get('percentage_variance_bps')),
            'direction': item.get('direction'),
        })
    return items


def _reconciled_count(body: dict) -> int:
    claims = body.get('claims') or []
    return sum(
        1
        for claim in claims
        if isinstance(claim, dict) and str(claim.get('status', '')).lower() in ('reconciled', 'computed')
    )


def _approval_state(row, body: dict, review=None) -> dict:
    return {
        'review_status': body.get('review_status') or 'draft',
        'analysis_revision': row['revision'],
        'narrative_digest': narrative_digest(body.get('narrative') or {}),
        'review': None
        if review is None
        else {
            'decision': review['decision'],
            'actor': review['actor'],
            'created_at': review['created_at'],
            'analysis_revision': review['analysis_revision'],
            'narrative_digest': review['narrative_digest'],
        },
    }


def _latest_review(db, analysis_id: str):
    return db.execute(
        'SELECT analysis_revision, narrative_digest, decision, actor, created_at '
        'FROM mo_reviews WHERE analysis_id=? ORDER BY created_at DESC',
        (analysis_id,),
    ).fetchone()


def serialize_overview(row, body: dict, context_rows: list[dict], review=None) -> dict:
    unexplained = [_serialize_unexplained(item) for item in _unexplained_items(body)]
    conflicts = [_serialize_conflict(item) for item in _reconciliation_conflicts(body)]
    return {
        'analysis_id': row['id'],
        'analysis_revision': row['revision'],
        'periods': body.get('periods') or {'prior': row['prior_period'], 'current': row['current_period']},
        'currency': body.get('currency') or 'USD',
        'material_variances': _material_variances(body),
        'reconciled_count': _reconciled_count(body),
        'reconciliation_conflicts': conflicts,
        'causally_unexplained': unexplained,
        'approval_state': _approval_state(row, body, review),
        'prism': prism_status(),
        'audio': audio_state() if body.get('synthetic') is True else {
            'enabled': False, 'configured': False, 'provider': 'none', 'state': 'audio_unavailable',
        },
        'calculation_digest': body.get('calculation_digest'),
        'calculation_version': row['calculation_version'],
        'suggested_context_count': sum(
            1 for item in context_rows if item.get('analysis_id') == row['id'] and item.get('status') == 'context_suggested' and item.get('active')
        ),
        'synthetic': body.get('synthetic') is True,
    }


def serialize_graph(row, body: dict, context_rows: list[dict]) -> dict:
    claims = body.get('claims') or []
    narrative = body.get('narrative') or {}
    conflicts = _reconciliation_conflicts(body)
    unexplained = _unexplained_items(body)
    suggested = [
        item for item in context_rows
        if item.get('analysis_id') == row['id'] and item.get('status') == 'context_suggested' and item.get('active')
    ]
    confirmed = [
        item for item in context_rows
        if item.get('analysis_id') == row['id'] and item.get('status') == 'user_confirmed' and item.get('active')
    ]
    statuses = {
        'compare': 'complete',
        'detect': 'complete' if _material_variances(body) else 'pending',
        'attribute': 'complete' if any(str(c.get('claim_type', '')).lower() in ('driver', 'driver_delta', 'driver_group') for c in claims) else 'pending',
        'reconcile': 'attention' if conflicts else 'complete',
        'retrieve_context': 'complete' if suggested or confirmed else 'pending',
        'explain': 'complete' if narrative.get('text') or narrative.get('body') else 'pending',
        'validate': 'attention' if narrative.get('model_error') else 'complete',
        'human_review': (
            'complete' if body.get('review_status') == 'approved' else (
                'attention' if body.get('review_status') in ('changes_requested', 'rejected') else 'pending'
            )
        ),
    }
    notes = {
        'compare': f"{(body.get('periods') or {}).get('prior')} → {(body.get('periods') or {}).get('current')}",
        'detect': f"{len(_material_variances(body))} material variances",
        'attribute': 'Selected drivers are claim-backed',
        'reconcile': 'Source conflicts remain' if conflicts else 'Numeric reconciliation complete; causal residuals stay separate',
        'retrieve_context': f'{len(suggested)} suggested / {len(confirmed)} confirmed',
        'explain': narrative.get('narrative_source') or 'deterministic_template',
        'validate': narrative.get('model_error') or 'cited claims only',
        'human_review': body.get('review_status') or 'draft',
    }
    if unexplained:
        notes['validate'] = 'Causally unexplained items remain visible'
    nodes = [
        {'id': node_id, 'label': label, 'status': statuses[node_id], 'note': notes[node_id]}
        for node_id, label in GRAPH_NODES
    ]
    edges = [
        {'from': GRAPH_NODES[index][0], 'to': GRAPH_NODES[index + 1][0]}
        for index in range(len(GRAPH_NODES) - 1)
    ]
    return {
        'analysis_id': row['id'],
        'nodes': nodes,
        'edges': edges,
        'synthetic': body.get('synthetic') is True,
    }


def _account_block(body: dict, account: str) -> dict | None:
    resolved = _normalize_account(account)
    accounts = body.get('accounts') or {}
    if isinstance(accounts, dict):
        for key in (resolved, account, str(account)):
            if key in accounts and isinstance(accounts[key], dict):
                return accounts[key]
        for key, block in accounts.items():
            if _same_account(str(key), account) and isinstance(block, dict):
                return block
    return None


def _id_only_rows(rows) -> list[dict]:
    out = []
    if not isinstance(rows, list):
        return out
    for row in rows[:40]:
        if not isinstance(row, dict):
            continue
        item = {}
        for key in ('source_id', 'transaction_id', 'source_file', 'period'):
            value = row.get(key)
            if isinstance(value, str) and value.strip() and len(value) <= 120:
                item[key] = value.strip()
        if item.get('transaction_id') or item.get('source_id'):
            out.append(item)
    return out


def _driver_payload(row: dict) -> dict:
    value = claim_value(row) if row.get('value_json') or row.get('value') else row
    return {
        'member': value.get('member') or row.get('member') or row.get('member_label'),
        'member_label': value.get('member_label') or row.get('member_label'),
        'dimension': value.get('dimension') or row.get('dimension'),
        'delta_minor': _as_int(value.get('delta_minor')) if _as_int(value.get('delta_minor')) is not None else claim_amount_minor(row),
        'share_bps': _as_int(value.get('share_bps')) if _as_int(value.get('share_bps')) is not None else claim_bps(row),
        'classification': value.get('classification') or row.get('classification'),
        'status': row.get('status') or 'computed',
    }


def serialize_variance(row, body: dict, account: str, context_rows: list[dict]) -> dict:
    resolved = _normalize_account(account)
    block = _account_block(body, account)
    claims = [
        claim for claim in body.get('claims') or []
        if isinstance(claim, dict) and (
            _same_account(str(claim.get('account_code') or ''), account)
            or _same_account(str(claim.get('account_name') or ''), account)
        )
    ]
    variance = None
    if block and isinstance(block.get('variance'), dict):
        variance = block['variance']
    else:
        for item in body.get('variances') or []:
            if isinstance(item, dict) and (
                _same_account(str(item.get('account_code') or ''), account)
                or _same_account(str(item.get('account_name') or ''), account)
            ):
                variance = item
                break
    amount = None
    pct = None
    if isinstance(variance, dict):
        amount = _as_int(variance.get('absolute_variance_minor'))
        if amount is None:
            amount = claim_amount_minor(variance)
        pct = _as_int(variance.get('percentage_variance_bps'))
        if pct is None:
            pct = claim_bps(variance)
    if amount is None and claims:
        amount = claim_amount_minor(claims[0])
        pct = claim_bps(claims[0]) if pct is None else pct
    drivers = []
    offsets = []
    if block and isinstance(block.get('drivers'), dict):
        primary = block['drivers'].get('primary') or {}
        for item in primary.get('selected_drivers') or []:
            drivers.append(_driver_payload(item))
        for item in primary.get('offsets') or []:
            offsets.append(_driver_payload(item))
    if not drivers:
        for claim in claims:
            ctype = str(claim.get('claim_type', '')).lower()
            classification = str(claim_value(claim).get('classification') or claim.get('classification') or '')
            if ctype in ('driver', 'driver_delta', 'driver_group') or classification in ('contributor', 'offset'):
                payload = _driver_payload(claim)
                if classification == 'offset':
                    offsets.append(payload)
                else:
                    drivers.append(payload)
    recon = (block or {}).get('reconciliation') if block else None
    causal = (block or {}).get('causal') if block else None
    unexplained = None
    if _is_other_opex(resolved) or _is_other_opex(account) or (isinstance(causal, dict) and causal.get('status') == 'unexplained'):
        unexplained = (causal or {}).get('note') or 'Unmapped clearing batch reconciles numerically; business cause is unsupported.'
    elif any(str(claim.get('status', '')).lower() == 'unexplained' for claim in claims):
        unexplained = 'Business cause is unsupported.'
    source_ids: list[str] = []
    transaction_ids: list[str] = []
    evidence_statuses = []
    for claim in claims:
        evidence_statuses.append({'claim_id': claim.get('id'), 'status': claim.get('status'), 'claim_type': claim.get('claim_type')})
        for sid in claim.get('source_ids') or []:
            if isinstance(sid, str) and sid not in source_ids:
                source_ids.append(sid)
        for item in _id_only_rows(claim.get('source_rows') or []):
            tid = item.get('transaction_id')
            if tid and tid not in transaction_ids:
                transaction_ids.append(tid)
            sid = item.get('source_id')
            if sid and sid not in source_ids:
                source_ids.append(sid)
    suggested = [
        {
            'context_id': item.get('id') or item.get('context_id'),
            'status': item.get('status'),
            'statement': item.get('statement'),
            'revision': item.get('revision'),
        }
        for item in context_rows
        if item.get('analysis_id') == row['id'] and _same_account(str(item.get('account_code') or ''), account)
    ]
    owner = 'controller' if unexplained else 'analyst'
    next_action = (
        'Finance review is required before causal attribution.'
        if unexplained
        else ('Confirm current-run context before treating prior notes as evidence.' if suggested else 'Review selected drivers and offsets.')
    )
    prior_minor = _as_int((variance or {}).get('prior_minor'))
    current_minor = _as_int((variance or {}).get('current_minor'))
    if prior_minor is None and block and isinstance(block.get('variance'), dict):
        prior_minor = _as_int(block['variance'].get('prior_minor'))
        current_minor = _as_int(block['variance'].get('current_minor'))
    return {
        'analysis_id': row['id'],
        'account_code': resolved or account,
        'account_name': (variance or {}).get('account_name') or (block or {}).get('account_name') or _account_name(resolved or account),
        'amount_minor': amount,
        'percentage_bps': pct,
        'prior_minor': prior_minor,
        'current_minor': current_minor,
        'direction': (variance or {}).get('direction'),
        'selected_drivers': drivers,
        'contribution_shares': [
            {'member': item.get('member') or item.get('member_label'), 'share_bps': item.get('share_bps'), 'delta_minor': item.get('delta_minor')}
            for item in drivers
        ],
        'offsets': offsets,
        'evidence_statuses': evidence_statuses,
        'source_ids': source_ids,
        'transaction_ids': transaction_ids,
        'suggested_context': suggested,
        'unexplained_cause': unexplained,
        'owner': owner,
        'next_action': next_action,
        'reconciliation_status': (recon or {}).get('status') if isinstance(recon, dict) else None,
        'calculation_digest': body.get('calculation_digest'),
        'synthetic': body.get('synthetic') is True,
    }


def serialize_variance_list(row, body: dict, context_rows: list[dict]) -> dict:
    codes = []
    for item in body.get('variances') or []:
        if isinstance(item, dict) and item.get('account_code'):
            codes.append(str(item['account_code']))
    if not codes:
        for claim in body.get('claims') or []:
            code = str(claim.get('account_code') or '')
            if code and code not in codes:
                codes.append(code)
    items = [serialize_variance(row, body, code, context_rows) for code in codes]
    return {
        'analysis_id': row['id'],
        'items': items,
        'calculation_digest': body.get('calculation_digest'),
        'synthetic': body.get('synthetic') is True,
    }


def serialize_memo(row, body: dict, context_rows: list[dict], review=None) -> dict:
    narrative = body.get('narrative') or {}
    periods = body.get('periods') or {'prior': row['prior_period'], 'current': row['current_period']}
    material = _material_variances(body)
    unexplained = [_serialize_unexplained(item) for item in _unexplained_items(body)]
    why = []
    for item in narrative.get('why') or []:
        if isinstance(item, dict) and item.get('text'):
            why.append({'text': item['text'], 'claim_ids': item.get('claim_ids') or []})
    if not why and narrative.get('text'):
        why.append({'text': narrative['text'], 'claim_ids': narrative.get('cited_claim_ids') or []})
    owners = sorted({
        *('controller' for _ in unexplained),
        'analyst',
    })
    actions = []
    if unexplained:
        actions.append('Do not attribute a business cause to Other Opex until Finance review.')
    if any(item.get('status') == 'context_suggested' and item.get('active') for item in context_rows if item.get('analysis_id') == row['id']):
        actions.append('Confirm suggested context on the current run before treating it as evidence.')
    if body.get('review_status') != 'approved':
        actions.append('Controller review is required before distribution or voice briefing.')
    return {
        'analysis_id': row['id'],
        'headline': narrative.get('headline') or 'Period comparison drafted from deterministic claims.',
        'what_changed': [
            {
                'account_code': item['account_code'],
                'account_name': item['account_name'],
                'amount_minor': item['amount_minor'],
                'percentage_bps': item['percentage_bps'],
            }
            for item in material
        ],
        'why_it_changed': why,
        'unresolved_items': unexplained,
        'decision_requested': (
            'Approve the memo with unexplained Other Opex still visible, or request changes.'
            if body.get('review_status') != 'approved'
            else 'Memo is approved. Voice briefing cannot change this decision.'
        ),
        'owners': owners,
        'recommended_actions': actions,
        'review': _approval_state(row, body, review),
        'calculation_digest': body.get('calculation_digest'),
        'narrative_digest': narrative_digest(narrative),
        'periods': periods,
        'synthetic': body.get('synthetic') is True,
    }


def _wants_mutation(question: str) -> bool:
    lowered = question.lower()
    return any(term in lowered for term in MUTATION_TERMS)


def _claim_by_id(claims: list[dict], *suffixes: str) -> dict | None:
    for claim in claims:
        cid = str(claim.get('id') or '')
        if any(cid == suffix or cid.endswith(suffix) for suffix in suffixes):
            return claim
    return None


def _maximor_revenue_sentence(claims: list[dict]) -> str | None:
    """Phrase the 18 / 32 / 64 close from stored claims only."""
    revenue = _claim_by_id(claims, 'claim-4000-absolute-variance', 'VAR-REV')
    revenue_pct = _claim_by_id(claims, 'claim-4000-percentage-variance')
    enterprise = _claim_by_id(claims, 'claim-4000-driver-segment-Enterprise', 'DRV-ENT')
    top3 = _claim_by_id(claims, 'claim-4000-top3-customers', 'DRV-TOP3')
    if not (revenue and enterprise and top3):
        return None
    rev_amt = display_usd(abs(claim_amount_minor(revenue) or 0))
    rev_pct = display_pct(claim_bps(revenue_pct or revenue))
    ent_amt = display_usd(abs(claim_amount_minor(enterprise) or 0))
    ent_pct = display_pct(claim_bps(enterprise))
    top_amt = display_usd(abs(claim_amount_minor(top3) or 0))
    top_bps = claim_value(top3).get('share_bps')
    if not isinstance(top_bps, int):
        top_bps = claim_bps(top3)
    top_share = display_pct(top_bps)
    if not (rev_pct and ent_pct and top_share):
        return None
    return (
        f'Gross revenue increased {rev_pct}, or {rev_amt}, primarily driven by a {ent_pct} '
        f'increase in enterprise accounts ({ent_amt}), with three customers accounting for '
        f'{top_share} of the increase ({top_amt}).'
    )


def answer_chat(row, body: dict, question: str) -> dict:
    claims = [claim for claim in body.get('claims') or [] if isinstance(claim, dict)]
    if _wants_mutation(question):
        return {
            'analysis_id': row['id'],
            'answer': (
                'This chat is read-only. Approval, edits, submission, and distribution '
                'require the review API and a controller. The analysis was not changed.'
            ),
            'claim_ids': [],
            'citations': [],
            'limitations': ['Ordinary questions cannot mutate Money Operations state.'],
            'suggested_follow_up': 'Ask what changed in revenue, Other Opex, or a named driver.',
            'escalation_action': 'POST /api/money-operations/analyses/{id}/review as controller to record a decision.',
            'mutated': False,
            'read_only': True,
        }
    lowered = question.lower()
    selected = []
    maximor = _maximor_revenue_sentence(claims)
    if 'other opex' in lowered or '6900' in lowered or 'unexplain' in lowered:
        selected = [c for c in claims if _is_other_opex(_claim_account(c)) or str(c.get('status', '')).lower() == 'unexplained']
        answer = (
            'Other Opex increased by a reconciled amount whose business cause is unsupported. '
            'It is causally unexplained, not a reconciliation conflict.'
        )
        follow = 'Ask who owns the unexplained residual and what review is required.'
        escalate = 'Controller review before any causal attribution.'
        limits = ['No source row establishes a business cause for Other Opex.']
    elif 'enterprise' in lowered:
        selected = [c for c in claims if 'enterprise' in ' '.join(str(x).lower() for x in (c.get('entities') or []) + [claim_value(c).get('member') or ''])]
        if not selected:
            selected = [c for c in claims if str(c.get('id', '')).endswith('driver-segment-Enterprise')]
        answer = maximor or 'Enterprise is a selected revenue driver. Figures come from cited claims only.'
        if maximor:
            selected = [c for c in (
                _claim_by_id(claims, 'claim-4000-absolute-variance'),
                _claim_by_id(claims, 'claim-4000-percentage-variance'),
                _claim_by_id(claims, 'claim-4000-driver-segment-Enterprise'),
                _claim_by_id(claims, 'claim-4000-top3-customers'),
            ) if c]
        follow = 'Ask how concentrated the increase was among named customers.'
        escalate = None
        limits = ['Chat does not recompute driver shares.']
    elif 'c001' in lowered or 'northstar' in lowered or 'top' in lowered or 'concentrat' in lowered:
        selected = [c for c in claims if str(c.get('id', '')).endswith('top3-customers') or 'top3' in str(c.get('id', '')).lower()]
        answer = maximor or 'Three named customers contributed a documented share of total growth. IDs stay on the claims.'
        follow = 'Ask whether any offset reduced the net account variance.'
        escalate = None
        limits = ['Customer names in prose are claim-backed labels, not a new calculation.']
    elif 'software' in lowered or '6200' in lowered or 'novaerp' in lowered:
        selected = [c for c in claims if _same_account(str(c.get('account_code') or ''), '6200')]
        answer = 'Software expense changed. Prior ERP context is suggested only until confirmed on this run.'
        follow = 'Ask which context entries remain unconfirmed.'
        escalate = 'Confirm suggested software context before treating it as current-run evidence.'
        limits = ['Prior-run notes do not change calculated amounts.']
    elif 'revenue' in lowered or '4000' in lowered or 'gross' in lowered or 'headline' in lowered or 'draft' in lowered:
        selected = [c for c in claims if _same_account(str(c.get('account_code') or ''), '4000') and str(c.get('claim_type', '')).lower() in ('variance', 'absolute_variance', 'percentage_variance', 'driver_delta', 'driver_group', '')]
        answer = maximor or 'Gross revenue changed between the selected periods. Amounts and percentages are claim-backed.'
        if maximor:
            selected = [c for c in (
                _claim_by_id(claims, 'claim-4000-absolute-variance'),
                _claim_by_id(claims, 'claim-4000-percentage-variance'),
                _claim_by_id(claims, 'claim-4000-driver-segment-Enterprise'),
                _claim_by_id(claims, 'claim-4000-top3-customers'),
            ) if c]
        follow = 'Ask which segment contributed the increase.'
        escalate = None
        limits = ['Chat reports stored claims; it does not recalculate the engine.']
    else:
        selected = [c for c in claims if str(c.get('claim_type', '')).lower() in ('absolute_variance', 'variance')][:3]
        answer = maximor or (
            body.get('narrative') or {}
        ).get('headline') or 'Ask about a specific account, driver, or unexplained item.'
        follow = 'Ask about Gross revenue, Enterprise, the top customers, or Other Opex.'
        escalate = 'Controller review for unresolved causal items.'
        limits = ['Answers are limited to structured claims on this analysis.']
    claim_ids = [c['id'] for c in selected if c.get('id')]
    citations = [
        {
            'claim_id': c.get('id'),
            'account_code': c.get('account_code'),
            'amount_minor': claim_amount_minor(c),
            'status': c.get('status'),
        }
        for c in selected
    ]
    return {
        'analysis_id': row['id'],
        'answer': answer,
        'claim_ids': claim_ids,
        'citations': citations,
        'limitations': limits,
        'suggested_follow_up': follow,
        'escalation_action': escalate,
        'mutated': False,
        'read_only': True,
    }


def _read_analysis(store, analysis_id: str):
    with store.connect() as db:
        row, body = _load_analysis(db, store, analysis_id)
        context = _active_context_rows(db)
        review = _latest_review(db, analysis_id)
        return row, body, context, review


def register_money_operations_extensions(app, store, auth):
    """Lead-wired UI contracts: overview, graph, variances, chat, memo, briefing."""
    if getattr(app.state, 'mo_extensions_registered', False):
        return
    app.state.mo_extensions_registered = True

    def load(analysis_id: str):
        return _read_analysis(store, analysis_id)

    @app.get('/api/money-operations/analyses/{analysis_id}/overview')
    def analysis_overview(analysis_id: str, user=Depends(auth)):
        row, body, context, review = load(analysis_id)
        return serialize_overview(row, body, context, review)

    @app.get('/api/money-operations/analyses/{analysis_id}/graph')
    def analysis_graph(analysis_id: str, user=Depends(auth)):
        row, body, context, _review = load(analysis_id)
        return serialize_graph(row, body, context)

    @app.get('/api/money-operations/analyses/{analysis_id}/account-variances')
    def analysis_variance_list(analysis_id: str, user=Depends(auth)):
        row, body, context, _review = load(analysis_id)
        return serialize_variance_list(row, body, context)

    @app.get('/api/money-operations/analyses/{analysis_id}/account-variances/{account}')
    def analysis_variance_detail(analysis_id: str, account: str, user=Depends(auth)):
        row, body, context, _review = load(analysis_id)
        payload = serialize_variance(row, body, account, context)
        if payload['amount_minor'] is None and not payload['selected_drivers'] and not payload['evidence_statuses']:
            raise MoneyOpsError(404, 'not_found', 'Variance not found', {'account': account})
        return payload

    @app.post('/api/money-operations/analyses/{analysis_id}/chat')
    def analysis_chat(analysis_id: str, body: ChatBody, user=Depends(auth)):
        row, stored, _context, _review = load(analysis_id)
        return answer_chat(row, stored, body.question)

    @app.get('/api/money-operations/analyses/{analysis_id}/memo')
    def analysis_memo(analysis_id: str, user=Depends(auth)):
        row, stored, context, review = load(analysis_id)
        return serialize_memo(row, stored, context, review)

    @app.post('/api/money-operations/analyses/{analysis_id}/briefing')
    def analysis_briefing(analysis_id: str, user=Depends(auth)):
        with store.connect() as db:
            row, stored = _load_analysis(db, store, analysis_id)
            return build_briefing(db, row, stored)

    @app.get('/api/money-operations/analyses/{analysis_id}/briefing/audio')
    def analysis_briefing_audio(analysis_id: str, user=Depends(auth)):
        with store.connect() as db:
            row, stored = _load_analysis(db, store, analysis_id)
            review = db.execute(
                'SELECT analysis_revision, narrative_digest, decision, actor, created_at '
                'FROM mo_reviews WHERE analysis_id=? AND decision=? ORDER BY created_at DESC',
                (analysis_id, 'approved'),
            ).fetchone()
            approved = assert_approved_memo(row, stored, review)
        audio = cached_audio(analysis_id, int(row['revision']), approved['narrative_digest'])
        if not audio:
            raise MoneyOpsError(409, 'audio_unavailable', 'No synthesized briefing is cached for this approved revision')
        return Response(audio, media_type='audio/mpeg')
