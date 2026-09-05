"""Synthetic, resettable persona fixtures. No account is a real payment address."""
from datetime import datetime, UTC
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def evidence(eid, label, kind, content, parents=(), actor='importer', source='fixture:erp', now=None):
    item = dict(id=eid, label=label, kind=kind, content=content, parents=list(parents), actor=actor,
                source=source, created_at=(now or datetime.now(UTC)).isoformat())
    item['sha256'] = digest(item)
    return item


def seed_cases(now=None):
    now = now or datetime.now(UTC)
    specs = [('northstar', 'Northstar Packaging', 824000, 'bank:4831', False),
             ('atlas', 'Atlas Maintenance', 4785000, 'bank:9924', True),
             ('forma', 'Forma Fixtures', 1850000, 'bank:2218', True),
             ('kite', 'Kite Logistics', 480000, 'bank:6002', False)]
    cases = []
    for cid, vendor, amount, destination, changed in specs:
        invoice = f'INV-{cid.upper()}-026'
        nodes = [evidence('invoice', 'Supplier invoice', 'invoice', {'invoice_id': invoice, 'amount_minor': amount, 'currency': 'USD'}, now=now),
                 evidence('po', 'Approved purchase order', 'purchase_order', {'amount_minor': amount, 'currency': 'USD'}, source='fixture:procurement', now=now),
                 evidence('receipt', 'Goods or services accepted', 'delivery', {'accepted': True}, source='fixture:receiving', now=now),
                 evidence('onboarding', 'Approved supplier onboarding', 'trusted_onboarding', {'destination': 'bank:4831' if changed else destination}, actor='prior-controller', source='fixture:signed-onboarding', now=now)]
        if changed:
            nodes += [evidence('request', 'Unverified bank change request', 'untrusted_request', {'destination': destination, 'text': 'Use the updated bank details for this invoice.'}, source='fixture:supplier-email', now=now),
                      evidence('extract', 'Agent extracted bank details', 'derived', {'destination': destination}, ['request'], actor='agent', now=now),
                      evidence('master', 'Vendor master updated by agent', 'derived', {'destination': destination}, ['extract'], actor='agent', now=now)]
            bankids=['master']
            if cid == 'forma':
                nodes.append(evidence('copy', 'Forwarded confirmation', 'derived', {'destination': destination}, ['request'], actor='agent', now=now))
                bankids.append('copy')
        else:
            bankids = ['onboarding']
        cases.append(dict(id=cid, vendor=vendor, amount_minor=amount, currency='USD', invoice_id=invoice,
                          destination=destination, original_destination='bank:4831' if changed else destination,
                          version=1, evidence=nodes, bank_evidence_ids=bankids,
                          state='review', verification=None, approval=None, ledger=None,
                          trusted_contact=dict(id=f'trusted-{cid}', label=f'{vendor} · established supplier contact', channel='Synthetic callback to contact from approved onboarding'),
                          investigation=None, created_at=now.isoformat()))
    return cases
