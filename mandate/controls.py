"""Mandate domain checks feeding the Resolve permission kernel; no model authority."""
from datetime import datetime, UTC
from .fixtures import digest
from .core.contract import (build_evidence_receipt, build_objective_receipt, build_constraint_validation_receipt,
    build_rehearsal_receipt, build_verification_receipt, build_decision_input, evaluate_decision)

POLICY_VERSION = 'mandate-ap-v1'
EVIDENCE_TTL_SECONDS = 86400


def lineage(case, now=None):
    now = now or datetime.now(UTC)
    nodes = {e['id']: e for e in case['evidence']}
    issues = []
    if len(nodes) != len(case['evidence']): issues.append('DUPLICATE_EVIDENCE_ID')
    cache = {}
    def roots(eid, stack=()):
        if eid in stack:
            issues.append('LINEAGE_CYCLE'); return set()
        if eid not in nodes:
            issues.append('MISSING_PARENT'); return set()
        if eid in cache: return cache[eid]
        e=nodes[eid]
        if digest({k:v for k,v in e.items() if k!='sha256'}) != e['sha256']: issues.append('CONTENT_HASH_MISMATCH')
        answer = set().union(*(roots(p, stack+(eid,)) for p in e['parents'])) if e['parents'] else {eid}
        cache[eid] = answer
        return answer
    for eid in nodes: roots(eid)
    bankroots = set().union(*(roots(eid) for eid in case['bank_evidence_ids']))
    independent=[]
    for eid in bankroots:
        e=nodes[eid]
        if e['content'].get('destination') != case['destination']: continue
        if e['kind']=='trusted_onboarding' and e['source']=='fixture:signed-onboarding' and e['actor']=='prior-controller':
            independent.append(eid)
        if e['kind']=='independent_verification' and e['source']==case['trusted_contact']['id'] and e['actor']=='analyst':
            try:
                age=(now-datetime.fromisoformat(e['created_at'])).total_seconds()
                if 0 <= age <= EVIDENCE_TTL_SECONDS: independent.append(eid)
            except (ValueError,TypeError): issues.append('INVALID_EVIDENCE_TIME')
    return dict(roots=sorted(bankroots),root_count=len(bankroots),independent_ids=independent,
                independent_verified=bool(independent) and not issues,issues=sorted(set(issues)))


def evaluate(case, cash, paid_invoices=(), now=None):
    """Fresh evaluation, including cash state. C2 reversal refers ONLY to our simulated ledger."""
    lineage_result = lineage(case, now)
    nodes={e['id']:e for e in case['evidence']}
    available=cash['balance_minor']-cash['commitments_minor']-cash['reserve_minor']
    failures=list(lineage_result['issues'])
    if case['currency'] != 'USD': failures.append('UNSUPPORTED_CURRENCY')
    if type(case['amount_minor']) is not int or case['amount_minor'] <= 0: failures.append('INVALID_AMOUNT')
    invoice=nodes.get('invoice',{}).get('content',{})
    po=nodes.get('po',{}).get('content',{})
    if invoice.get('amount_minor') != case['amount_minor'] or invoice.get('invoice_id') != case['invoice_id'] or invoice.get('currency') != case['currency']:
        failures.append('INVOICE_MISMATCH')
    if po.get('amount_minor') != case['amount_minor'] or po.get('currency') != case['currency']: failures.append('PO_MISMATCH')
    if nodes.get('receipt',{}).get('content',{}).get('accepted') is not True: failures.append('DELIVERY_UNCONFIRMED')
    if (case['vendor'],case['invoice_id']) in paid_invoices: failures.append('DUPLICATE_PAYMENT')
    if available < case['amount_minor']: failures.append('CASH_FLOOR_BREACH')
    # Validate dated cash snapshot. Fixture commitments are a conservative aggregate for 7 days.
    try:
        age=((now or datetime.now(UTC))-datetime.fromisoformat(cash['as_of'])).total_seconds()
        if age<0 or age>86400: failures.append('STALE_CASH_SNAPSHOT')
    except (ValueError, KeyError): failures.append('CASH_DATE_UNKNOWN')
    required={'invoice','po','receipt','onboarding'}
    registry={e['id']:digest(e) for e in case['evidence']}
    if lineage_result['independent_verified']:
        registry['beneficiary_authorization']=digest([nodes[x] for x in lineage_result['independent_ids']])
    required.add('beneficiary_authorization')
    objective='Pay this approved supplier invoice to an independently authorized beneficiary within cash policy'
    raw=dict(name=case['id'],policy_version=POLICY_VERSION,
             objective=dict(primary=objective,protected_outcomes=['Cash reserve','Authorized beneficiary'],anti_objectives=['Duplicate or unauthorized payment']),
             evidence_roots=sorted(required),constraints=['ap_baseline'],
             actions=[dict(id='payments.simulate_transfer',consequence='C2',reversible=True,authority='controller',allowed_targets=[case['vendor']],
                           allowed_parameters=dict(invoice_id=[case['invoice_id']],destination_token=[case['destination']],amount_minor=dict(minimum=1,maximum=5000000),currency=['USD']),
                           human_approval_required=True,rehearsal_required=True)],
             verification=dict(success_conditions=['Exact authorized transfer exists once in simulated ledger']),watch=dict(reopen_conditions=['Evidence, policy, destination or cash changed']))
    candidate=dict(action_type='payments.simulate_transfer',target=case['vendor'],parameters=dict(invoice_id=case['invoice_id'],destination_token=case['destination'],amount_minor=case['amount_minor'],currency=case['currency']))
    state=digest(dict(version=case['version'],cash=cash,policy=POLICY_VERSION,verification=case['verification']))
    er=build_evidence_receipt(evidence_registry=registry,required_evidence_ids=frozenset(required),candidate_evidence_ids=frozenset(registry))
    ob=build_objective_receipt(raw_case=raw,evidence_receipt=er,candidate_objective=objective,validator=lambda _c,_e:objective)
    cr=build_constraint_validation_receipt(raw_case=raw,candidate=candidate,validators={'ap_baseline':lambda _c,_a:tuple(failures)})
    rehearsal=build_rehearsal_receipt(candidate=candidate,state_fingerprint=state,passed=not failures)
    vr=build_verification_receipt(candidate=candidate,state_fingerprint=state,possible=True)
    inp=build_decision_input(raw_case=raw,candidate=candidate,objective_receipt=ob,evidence_receipt=er,constraint_receipt=cr,state_fingerprint=state,consequence_assessed=True,reversibility_confirmed=True,rehearsal_receipt=rehearsal,requested_approver_role='controller',verification_receipt=vr)
    decision=evaluate_decision(inp)
    reasons=failures+([] if lineage_result['independent_verified'] else ['INDEPENDENT_BENEFICIARY_VERIFICATION_REQUIRED'])
    result=dict(status=decision.result.disposition.value,gates=[dict(name=k,value=v.value,reason='; '.join(reasons) if k in ('evidence','constraints') else k.replace('_',' ').title()) for k,v in decision.result.gates.items()],reasons=reasons,root_count=lineage_result['root_count'],independent_verified=lineage_result['independent_verified'],cash_available_minor=available,lineage=lineage_result,fingerprints=decision.to_dict(),policy_version=POLICY_VERSION)
    return decision,result,candidate
