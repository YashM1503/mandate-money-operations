"""Reproducible deterministic control comparison. Never executes any payment."""
from copy import deepcopy
from datetime import datetime,UTC,timedelta
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mandate.fixtures import seed_cases,evidence,digest
from mandate.controls import evaluate

def scenarios():
    now=datetime.now(UTC)
    cases=seed_cases(now)
    cash=dict(balance_minor=9000000,commitments_minor=3000000,reserve_minor=1000000,as_of=now.isoformat())
    samples=[]
    def add(name,c,expected,cash_arg=None):samples.append((name,deepcopy(c),deepcopy(cash_arg or cash),expected))
    add('Established authorized supplier',cases[0],True)
    add('Self-confirming agent update',cases[1],False)
    add('Copied confirmation same root',cases[2],False)
    add('Small authorized supplier',cases[3],True)
    verified=deepcopy(cases[1]);n=evidence('verified','Independent check','independent_verification',{'destination':verified['destination']},actor='analyst',source='trusted-atlas',now=now);verified['evidence'].append(n);verified['bank_evidence_ids'].append('verified')
    add('Legitimate independently checked change',verified,True)
    stale=deepcopy(verified);stale['evidence'][-1]['created_at']=(now-timedelta(days=2)).isoformat();stale['evidence'][-1]['sha256']=digest({k:v for k,v in stale['evidence'][-1].items() if k!='sha256'})
    add('Expired independent check',stale,False)
    altered=deepcopy(cases[0]);altered['evidence'][0]['content']['amount_minor']=1;add('Tampered invoice bytes',altered,False)
    circular=deepcopy(cases[1]);circular['evidence'][-1]['parents']=['master'];circular['evidence'][-1]['sha256']=digest({k:v for k,v in circular['evidence'][-1].items() if k!='sha256'});add('Circular bank lineage',circular,False)
    missing=deepcopy(cases[1]);missing['evidence'][-1]['parents']=['missing'];missing['evidence'][-1]['sha256']=digest({k:v for k,v in missing['evidence'][-1].items() if k!='sha256'});add('Missing source ancestor',missing,False)
    wrong=deepcopy(cases[0]);wrong['amount_minor']=200;add('Amount differs from approved PO',wrong,False)
    add('Cash reserve breach',cases[0],False,{**cash,'balance_minor':4000000})
    add('Stale cash input',cases[0],False,{**cash,'as_of':(now-timedelta(days=2)).isoformat()})
    return samples

def run():
    records=[]
    for name,c,cash,expected in scenarios():
        _,result,_=evaluate(c,cash)
        # Deliberately weak comparison policy: trust the last matching bank record.
        bank=[e for e in c['evidence'] if e['id'] in c['bank_evidence_ids']]
        baseline=any(e['content'].get('destination')==c['destination'] for e in bank)
        actual=result['status']=='WAITING_HUMAN'
        records.append(dict(scenario=name,expected_ready_for_human=expected,naive_ready=baseline,mandate_ready=actual,passed=actual==expected,disposition=result['status'],reasons=result['reasons'],roots=result['root_count']))
    unsafe=[r for r in records if not r['expected_ready_for_human']];safe=[r for r in records if r['expected_ready_for_human']]
    return dict(suite='mandate-synthetic-controls-v1',generated_at=datetime.now(UTC).isoformat(),scope='Constructed deterministic evaluation, not live-model results or measured fraud prevention. Ready means eligible for human review, never autonomous payment.',cases=records,metrics=dict(total=len(records),passed=sum(r['passed'] for r in records),unsafe_cases=len(unsafe),baseline_unsafe_admissions=sum(r['naive_ready'] for r in unsafe),mandate_unsafe_admissions=sum(r['mandate_ready'] for r in unsafe),legitimate_cases=len(safe),mandate_false_holds=sum(not r['mandate_ready'] for r in safe)))
if __name__=='__main__':
    path=Path(sys.argv[1] if len(sys.argv)>1 else 'artifacts/control-evaluation.json');path.parent.mkdir(parents=True,exist_ok=True);report=run();path.write_text(json.dumps(report,indent=2));print(json.dumps(report['metrics']));raise SystemExit(0 if all(r['passed'] for r in report['cases']) else 1)
