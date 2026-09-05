from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,UTC,timedelta
import hashlib,json,secrets,sqlite3,time
import pytest
from fastapi.testclient import TestClient
from mandate.api import create_app
from mandate.store import Store
from mandate.fixtures import digest,evidence,seed_cases
from mandate.controls import evaluate,lineage
from mandate.core.approval import approval_from_dict,create_approval_for_decision

@pytest.fixture
def setup(tmp_path):
    key=b'k'*64
    store=Store(tmp_path/'test.sqlite3',key)
    users={r:{'role':r,'salt':'ab'*16,'hash':hashlib.pbkdf2_hmac('sha256',b'test-only-password',bytes.fromhex('ab'*16),600000).hex()} for r in ['analyst','controller','auditor']}
    app=create_app(store,users);client=TestClient(app)
    headers={r:{'Authorization':'Bearer '+r+'-test'} for r in users}
    with store.transaction() as db:
        for r in users:db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256((r+'-test').encode()).hexdigest(),r,r,time.time()+3600))
    return client,store,headers

def case(s,cid='northstar'):
    c,_,h=s;res=c.get('/api/cases/'+cid,headers=h['analyst']);assert res.status_code==200,res.text;return res.json()
def post(s,cid,action,body,role='controller',status=200):
    c,_,h=s
    if action=='approve' and 'decision_fingerprint' not in body:body={**body,'decision_fingerprint':case(s,cid)['decision']['fingerprints']['decision_fingerprint']}
    r=c.post(f'/api/cases/{cid}/{action}',json=body,headers=h[role]);assert r.status_code==status,r.text;return r.json()
def approve(s,cid='northstar'):return post(s,cid,'approve',{'version':case(s,cid)['version']})
def execute(s,cid='northstar',key='test-idempotency-0001',version=None,status=200):return post(s,cid,'execute',{'version':version or case(s,cid)['version'],'idempotency_key':key},status=status)
def change(s,cid,fn):
    _,st,_=s
    with st.transaction() as db:
        c=st.get(db,cid);fn(c);st.save(db,c);st.event(db,c,'test_fixture_changed','test',{})


def test_persona_and_roots(setup):
    assert case(setup)['amount_minor']==824000
    a=case(setup,'atlas');assert a['amount_minor']==4785000
    assert a['decision']['status']=='MORE_EVIDENCE_REQUIRED'
    assert a['decision']['root_count']==1
    assert case(setup,'forma')['decision']['root_count']==1
    assert case(setup)['decision']['status']=='WAITING_HUMAN'

def test_authentication_and_roles(setup):
    c,_,h=setup
    assert c.get('/api/cases').status_code==401
    assert c.get('/api/cases',headers={'Authorization':'Bearer invalid'}).status_code==401
    post(setup,'northstar','approve',{'version':1},'analyst',403)
    post(setup,'northstar','execute',{'version':1,'idempotency_key':'test-000000000000'},'auditor',403)
    r=c.post('/api/login',json={'username':'analyst','password':'test-only-password'})
    assert r.status_code==200 and r.json()['user']['role']=='analyst'
    token={'Authorization':'Bearer '+r.json()['token']}
    assert c.post('/api/logout',headers=token).status_code==200
    assert c.get('/api/cases',headers=token).status_code==401

def test_login_bad_credentials_and_throttle(setup):
    c,_,_=setup
    for i in range(10):assert c.post('/api/login',json={'username':'nobody','password':'wrong'}).status_code==401
    assert c.post('/api/login',json={'username':'nobody','password':'wrong'}).status_code==429
    # One username cannot lock every user sharing the same client address.
    assert c.post('/api/login',json={'username':'analyst','password':'test-only-password'}).status_code==200

def test_northstar_execution_exact_and_retry(setup):
    approve(setup)
    result=execute(setup,version=1)
    assert result['ledger']['amount_minor']==824000
    assert result['ledger']['destination']=='bank:4831'
    assert result['case']['state']=='released'
    again=execute(setup,version=1)
    assert again['replayed'] and again['ledger']['id']==result['ledger']['id']
    _,st,_=setup
    with st.connect() as db:
        assert db.execute('SELECT count(*) FROM ledger').fetchone()[0]==1
        assert st.cash(db)['balance_minor']==8176000
        assert st.audit(db,st.get(db,'northstar'))['valid']
    execute(setup,key='test-other-key-0001',status=409)

def test_atlas_requires_independent_verification(setup):
    post(setup,'atlas','approve',{'version':1},status=409)
    execute(setup,'atlas',status=409)
    body=dict(version=1,destination='bank:9924',contact_id='trusted-atlas',note='Synthetic trusted callback completed with supplier contact')
    post(setup,'atlas','verify',body,'controller',403)
    post(setup,'atlas','verify',{**body,'contact_id':'from-incoming-email'},'analyst',422)
    verified=post(setup,'atlas','verify',body,'analyst')
    assert verified['decision']['independent_verified']
    assert verified['decision']['root_count']==2
    approve(setup,'atlas');r=execute(setup,'atlas')
    assert r['ledger']['amount_minor']==4785000

def test_destination_change_invalidates_approval(setup):
    approve(setup)
    x=post(setup,'northstar','mutate',{'version':1,'destination':'bank:7777'},'analyst')
    assert not x['approval']['valid']
    execute(setup,version=1,status=409)
    execute(setup,version=2,status=409)

def test_revocation(setup):
    approve(setup)
    post(setup,'northstar','revoke',{'version':1,'reason':'Recheck supplier authorization'})
    execute(setup,status=409)

def test_expired_grant(setup):
    _,st,_=setup
    with st.transaction() as db:
        c=st.get(db,'northstar');d,_,_=evaluate(c,st.cash(db),st.paid(db))
        now=datetime.now(UTC)
        g=create_approval_for_decision(d,approver='controller',issued_at=now-timedelta(minutes=10),expires_at=now-timedelta(minutes=5),secret_key=st.key)
        c['approval']={'id':'expired','expires_at':g.expires_at.isoformat(),'revoked':False,'approver':'controller','grant':g.to_dict()}
        st.save(db,c);st.event(db,c,'test_expired','test',{})
    execute(setup,status=409)

def test_cash_change_invalidates_pending_grant(setup):
    approve(setup);approve(setup,'kite')
    execute(setup,'kite',key='kite-idempotency-0001')
    execute(setup,status=409)
    approve(setup);execute(setup)

def test_cash_floor_blocks(setup):
    _,st,_=setup
    with st.transaction() as db:
        cash=st.cash(db);cash['balance_minor']=4000000;st.set_cash(db,cash)
    assert 'CASH_FLOOR_BREACH' in case(setup)['decision']['reasons']
    approve_result=post(setup,'northstar','approve',{'version':1},status=409)

def test_stale_cash_blocks(setup):
    _,st,_=setup
    with st.transaction() as db:
        cash=st.cash(db);cash['as_of']=(datetime.now(UTC)-timedelta(days=2)).isoformat();st.set_cash(db,cash)
    assert 'STALE_CASH_SNAPSHOT' in case(setup)['decision']['reasons']
    post(setup,'northstar','approve',{'version':1},status=409)

def test_cash_after_atlas_does_not_afford_northstar(setup):
    post(setup,'atlas','verify',dict(version=1,destination='bank:9924',contact_id='trusted-atlas',note='Verified through established supplier contact'),'analyst')
    approve(setup,'atlas');execute(setup,'atlas')
    assert 'CASH_FLOOR_BREACH' in case(setup)['decision']['reasons']

def test_atomic_concurrent_execution(setup):
    approve(setup)
    c,_,h=setup
    def run(_):return c.post('/api/cases/northstar/execute',json={'version':1,'idempotency_key':'concurrent-key-0001'},headers=h['controller'])
    with ThreadPoolExecutor(max_workers=4) as pool:r=list(pool.map(run,range(4)))
    assert all(x.status_code==200 for x in r),[x.text for x in r]
    assert len({x.json()['ledger']['id'] for x in r})==1

def test_same_key_different_case_conflicts(setup):
    approve(setup);execute(setup,version=1)
    approve(setup,'kite');execute(setup,'kite',version=1,status=409)

def test_compensation_is_once_and_recorded(setup):
    approve(setup);execute(setup,version=1)
    r=post(setup,'northstar','compensate',{'version':2,'reason':'Reverse the simulated debit for demo'})
    assert r['state']=='compensated'
    post(setup,'northstar','compensate',{'version':3,'reason':'Attempt second reversal'},status=409)
    execute(setup,key='new-idempotency-002',status=409)
    _,st,_=setup
    with st.connect() as db:assert st.cash(db)['balance_minor']==9000000

@pytest.mark.parametrize('part',['case','event','tail'])
def test_record_tampering_locks_effects(setup,part):
    approve(setup);c,st,h=setup
    with st.transaction() as db:
        if part=='case':
            x=st.get(db,'northstar');x['amount_minor']=1;st.save(db,x)
        elif part=='event':db.execute("UPDATE events SET body=replace(body,'approval_granted','approval_hacked') WHERE case_id='northstar'")
        else:db.execute("DELETE FROM events WHERE case_id='northstar' AND seq=(SELECT max(seq) FROM events WHERE case_id='northstar')")
    assert c.get('/api/cases/northstar',headers=h['analyst']).status_code==409
    execute(setup,version=1,status=409)

@pytest.mark.parametrize('problem',['cycle','missing','tamper','duplicate'])
def test_lineage_invalid_fails_closed(setup,problem):
    def alter(c):
        n=c['evidence'][-1]
        if problem=='cycle':n['parents']=['master']
        if problem=='missing':n['parents']=['absent']
        if problem=='tamper':n['content']['destination']='bank:1111'
        if problem=='duplicate':c['evidence'].append(dict(n))
        if problem!='tamper':n['sha256']=digest({k:v for k,v in n.items() if k!='sha256'})
    change(setup,'atlas',alter)
    assert case(setup,'atlas')['decision']['status']=='BLOCKED'
    post(setup,'atlas','approve',{'version':1},status=409)

def test_derived_copies_do_not_increase_independence():
    c=seed_cases()[1]
    for i in range(50):
        eid='copy-'+str(i);c['evidence'].append(evidence(eid,'Copy','derived',{'destination':c['destination']},['master'],actor='agent'))
        c['bank_evidence_ids'].append(eid)
    x=lineage(c);assert x['root_count']==1 and not x['independent_verified']

def test_expired_verification_no_authority(setup):
    post(setup,'atlas','verify',dict(version=1,destination='bank:9924',contact_id='trusted-atlas',note='Verified through established supplier contact'),'analyst')
    def old(c):
        n=c['evidence'][-1];n['created_at']=(datetime.now(UTC)-timedelta(days=2)).isoformat();n['sha256']=digest({k:v for k,v in n.items() if k!='sha256'})
    change(setup,'atlas',old)
    assert not case(setup,'atlas')['decision']['independent_verified']

def test_po_mismatch(setup):
    change(setup,'northstar',lambda c:c.update(amount_minor=100))
    assert 'PO_MISMATCH' in case(setup)['decision']['reasons']
    post(setup,'northstar','approve',{'version':1},status=409)

def test_body_validation_no_extra_authority(setup):
    post(setup,'northstar','approve',{'version':1,'role':'controller','status':'PASS'},status=422)
    post(setup,'northstar','approve',{'version':True},status=422)
    post(setup,'northstar','mutate',{'version':1,'destination':'https://evil.example'},'analyst',422)

def test_metrics_export_and_replay_investigation(setup):
    c,_,h=setup
    x=post(setup,'atlas','investigate',{},'analyst')
    assert x['decision']['status']=='MORE_EVIDENCE_REQUIRED'
    assert x['investigation']['mode'] in ('deterministic_replay','replay')
    exported=c.get('/api/export/atlas',headers=h['auditor']);assert exported.status_code==200 and exported.json()['synthetic']
    assert 'grant' not in (exported.json()['case']['approval'] or {})
    metrics=c.get('/api/metrics',headers=h['auditor']).json()
    assert metrics['journal']['valid']
    assert metrics['fraud_prevention_rate'] is None

def test_restarts_preserve_audit_and_ledger(setup):
    approve(setup);execute(setup,version=1)
    _,st,_=setup;new=Store(st.path,st.key)
    with new.connect() as db:
        c=new.get(db,'northstar');assert c['state']=='released' and new.audit(db,c)['valid']

def test_security_headers(setup):
    c,_,h=setup
    r=c.get('/api/cases',headers=h['auditor']);assert r.headers['x-content-type-options']=='nosniff'
    assert r.headers['cache-control']=='no-store'
    assert c.get('/healthz',headers={'host':'evil.example'}).status_code==400
    assert c.post('/api/login',content=b'x'*17000,headers={'content-type':'application/json'}).status_code==413


def test_stale_displayed_decision_cannot_approve(setup):
    prior=case(setup)['decision']['fingerprints']['decision_fingerprint']
    approve(setup,'kite');execute(setup,'kite',key='kite-context-000001')
    post(setup,'northstar','approve',{'version':1,'decision_fingerprint':prior},status=409)

@pytest.mark.parametrize('target',['ledger_change','ledger_delete','cash','anchor'])
def test_integrity_covers_persisted_effect_cash_anchor(setup,target):
    approve(setup);execute(setup,version=1)
    c,st,h=setup
    with st.transaction() as db:
        if target=='ledger_change':db.execute("UPDATE ledger SET body=replace(body,'bank:4831','bank:7777')")
        elif target=='ledger_delete':db.execute("DELETE FROM ledger")
        elif target=='cash':db.execute("UPDATE settings SET body=replace(body,'8176000','9176000') WHERE key='cash'")
        else:db.execute("DELETE FROM anchors WHERE case_id='northstar'")
    assert c.get('/api/cases/northstar',headers=h['analyst']).status_code==409
    execute(setup,version=1,status=409)
    post(setup,'northstar','compensate',{'version':2,'reason':'Attempt a compensating credit'},status=409)


def test_idempotency_receipt_cannot_point_to_another_effect(setup):
    approve(setup);execute(setup,version=1)
    approve(setup,'kite');execute(setup,'kite',key='kite-separate-key-0001',version=1)
    _,st,_=setup
    with st.transaction() as db:
        lid=st.get(db,'kite')['ledger']['id']
        db.execute('UPDATE idempotency SET ledger_id=? WHERE key=?',(lid,'test-idempotency-0001'))
    execute(setup,version=1,status=409)
