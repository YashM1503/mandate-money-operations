"""Authenticated synthetic AP API. No route can initiate a real bank payment."""
from datetime import datetime,UTC,timedelta
from pathlib import Path
import base64,hashlib,hmac,json,os,re,secrets,time,uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI,HTTPException,Depends,Request
from fastapi.responses import FileResponse,JSONResponse
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel,ConfigDict,Field
from .store import Store
from .fixtures import digest,evidence
from .controls import evaluate
from .core.approval import create_approval_for_decision,approval_from_dict,validate_approval,consume_approval
from .env import load_runtime_env

ROOT=Path(__file__).resolve().parent.parent
load_runtime_env()

def _script_csp(path:Path)->str:
    """Allow only the exact inline scripts shipped in a static page."""
    text=path.read_text(encoding='utf-8')
    hashes=[]
    for script in re.findall(r'<script(?:\s[^>]*)?>(.*?)</script>',text,flags=re.I|re.S):
        digest=base64.b64encode(hashlib.sha256(script.encode()).digest()).decode()
        hashes.append(f"'sha256-{digest}'")
    return ' '.join(hashes) or "'none'"

class StrictBody(BaseModel): model_config=ConfigDict(extra='forbid',strict=True)
class Login(StrictBody):
    username:str=Field(min_length=1,max_length=32)
    password:str=Field(min_length=1,max_length=128)
class SecurityRevision(StrictBody): expected_revision:int=Field(ge=1)
class SecurityMessage(SecurityRevision): message:str=Field(min_length=1,max_length=4000)
class Version(StrictBody): version:int=Field(ge=1)
class ApprovalRequest(Version):
    decision_fingerprint:str=Field(pattern=r'^[a-f0-9]{64}$')
class Verification(Version):
    destination:str=Field(min_length=1,max_length=80)
    contact_id:str=Field(min_length=1,max_length=80)
    note:str=Field(min_length=12,max_length=1000)
class Mutation(Version): destination:str=Field(pattern=r'^bank:[0-9]{4}$')
class Reason(Version): reason:str=Field(min_length=8,max_length=1000)
class Execution(Version): idempotency_key:str=Field(min_length=16,max_length=80,pattern=r'^[a-zA-Z0-9_-]+$')

def load_config():
    data=Path(os.getenv('MANDATE_DATA_DIR',str(ROOT/'data')))
    config_path=data/'config.json'
    if config_path.exists(): config=json.loads(config_path.read_text())
    else: config={}
    key=os.getenv('MANDATE_SIGNING_KEY',config.get('signing_key',''))
    users_json=os.getenv('MANDATE_USERS_JSON')
    users=json.loads(users_json) if users_json else config.get('users',{})
    if len(key)<64 or not users: raise RuntimeError('Run python scripts/bootstrap.py or configure signing key and users; no default password exists.')
    # PBKDF2 credentials are provisioned offline; no account registration endpoint.
    if set(users)!={'analyst','controller','auditor'} or any(set(u)!={'role','salt','hash'} or u['role']!=name for name,u in users.items()): raise RuntimeError('Invalid user configuration')
    return data,key.encode(),users

def allowed_hosts():
    raw=os.getenv('MANDATE_ALLOWED_HOSTS','localhost,127.0.0.1,testserver')
    hosts=[h.strip() for h in raw.split(',') if h.strip()]
    if '*' in hosts:
        return ['*']
    extras=[]
    for key in ('RENDER_EXTERNAL_HOSTNAME','RAILWAY_PUBLIC_DOMAIN','WEBSITE_HOSTNAME'):
        value=os.getenv(key,'').strip()
        if value: extras.append(value)
    fly=os.getenv('FLY_APP_NAME','').strip()
    if fly: extras.append(f'{fly}.fly.dev')
    for loop in ('127.0.0.1','localhost'):
        if loop not in hosts:
            hosts.append(loop)
    return list(dict.fromkeys(hosts+extras))

def create_app(store=None,users=None):
    if store is None:
        data,key,users=load_config(); store=Store(data/'mandate.sqlite3',key)
    app=FastAPI(title='Mandate Trust and Risk API',version='1.0.0',docs_url='/docs',redoc_url=None)
    app.state.store=store; app.state.users=users
    page_script_csp={
        '/':_script_csp(ROOT/'static/index.html'),
        '/money-operations':_script_csp(ROOT/'static/money-operations.html'),
        '/demo.html':_script_csp(ROOT/'static/money-operations.html'),
    }
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=allowed_hosts())
    @app.middleware('http')
    async def headers(request,call_next):
        # Incremental ASGI body cap prevents unbounded JSON even without Content-Length.
        size=0; receive=request._receive
        path=request.url.path
        max_body=16384
        if path=='/api/money-operations/datasets':
            try: max_body=max(16384,int(os.getenv('MANDATE_MAX_UPLOAD_BYTES','2000000')))
            except ValueError: max_body=2000000
        async def limited_receive():
            nonlocal size
            message=await receive();size+=len(message.get('body',b''))
            if size>max_body: raise HTTPException(413,'Request too large')
            return message
        request._receive=limited_receive
        if not (request.headers.get('content-length','0') or '0').isdigit(): return JSONResponse({'detail':'Invalid content length'},400)
        if int(request.headers.get('content-length','0') or 0)>max_body: return JSONResponse({'detail':'Request too large'},413)
        response=await call_next(request)
        response.headers.update({'X-Content-Type-Options':'nosniff','X-Frame-Options':'DENY','Referrer-Policy':'no-referrer','Cache-Control':'no-store','Permissions-Policy':'camera=(), microphone=(), geolocation=()'})
        if request.url.path in ('/','/money-operations','/demo.html'):
            response.headers['Content-Security-Policy']=f"default-src 'none'; script-src {page_script_csp[request.url.path]}; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; media-src 'self' blob:; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        return response
    security=HTTPBearer(auto_error=False)
    def auth(credentials:HTTPAuthorizationCredentials|None=Depends(security)):
        if not credentials: raise HTTPException(401,'Sign in to continue')
        with store.connect() as db:
            row=db.execute('SELECT * FROM sessions WHERE token_hash=? AND expires>?',(hashlib.sha256(credentials.credentials.encode()).hexdigest(),time.time())).fetchone()
        if not row: raise HTTPException(401,'Session expired; sign in again')
        return dict(row)
    def role(user,needed):
        if user['role']!=needed: raise HTTPException(403,f'{needed.title()} role required')
    def getcase(db,cid,version=None):
        c=store.get(db,cid)
        if c is None: raise HTTPException(404,'Payment case not found')
        if not store.audit(db,c)['valid']: raise HTTPException(409,'Audit or state integrity failed; execution is locked')
        if version is not None and version!=c['version']: raise HTTPException(409,'Case changed; refresh before continuing')
        return c
    def view(db,c):
        _,decision,_=evaluate(c,store.cash(db),store.paid(db))
        public=dict(c); public['decision']=decision
        if c['approval']:
            a=c['approval']; public['approval']={k:a[k] for k in ('id','expires_at','revoked','approver')}
            public['approval']['valid']=approval_check(c,db)[0]
        public['events']=store.events(db,c['id']); public['journal']=store.audit(db,c)
        return public
    def approval_check(c,db):
        decision,_,_=evaluate(c,store.cash(db),store.paid(db))
        a=c['approval']
        if not a or a['revoked']: return False,'Approval missing or revoked',decision,None
        grant=approval_from_dict(a['grant'])
        kwargs={f'expected_{k}':getattr(decision,k) for k in ('candidate_fingerprint','case_fingerprint','evidence_fingerprint','state_fingerprint','decision_fingerprint')}
        kwargs.update(expected_authority='controller',expected_consequence_class='C2',now=datetime.now(UTC),secret_key=store.key)
        check=validate_approval(grant,**kwargs)
        return check.valid,check.status.value,decision,(grant,kwargs)
    @app.get('/healthz')
    def health(): return {'status':'ok','payment_mode':'synthetic_ledger'}
    @app.get('/')
    def index(): return FileResponse(ROOT/'static/index.html')
    @app.get('/money-operations')
    def money_operations_index(): return FileResponse(ROOT/'static/money-operations.html')
    @app.get('/demo.html')
    def money_operations_demo(): return FileResponse(ROOT/'static/money-operations.html')
    @app.post('/api/login')
    def login(body:Login,request:Request):
        client=request.client.host if request.client else 'unknown'
        limiter_key=f'{client}:{body.username.casefold()}'
        with store.transaction() as db:
            row=db.execute('SELECT * FROM login_attempts WHERE client=?',(limiter_key,)).fetchone();now=time.time()
            count=row['count'] if row and now-row['started']<60 else 0
            if count>=10: raise HTTPException(429,'Too many attempts; retry in one minute')
        u=users.get(body.username)
        # Constant-work dummy credential for unknown usernames.
        salt=u['salt'] if u else '0'*32
        actual=hashlib.pbkdf2_hmac('sha256',body.password.encode(),bytes.fromhex(salt),600000).hex()
        if not u or not hmac.compare_digest(actual,u['hash']):
            with store.transaction() as db:
                row=db.execute('SELECT * FROM login_attempts WHERE client=?',(limiter_key,)).fetchone();now=time.time()
                count=row['count'] if row and now-row['started']<60 else 0
                started=row['started'] if count else now
                db.execute('INSERT INTO login_attempts VALUES(?,?,?) ON CONFLICT(client) DO UPDATE SET count=excluded.count,started=excluded.started',(limiter_key,started,count+1))
            raise HTTPException(401,'Invalid credentials')
        token=secrets.token_urlsafe(32)
        with store.transaction() as db:
            db.execute('DELETE FROM login_attempts WHERE client=?',(limiter_key,))
            db.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
            db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),body.username,u['role'],time.time()+3600))
        return dict(token=token,user=dict(username=body.username,role=u['role']))
    @app.post('/api/logout')
    def logout(user=Depends(auth)):
        with store.transaction() as db: db.execute('DELETE FROM sessions WHERE token_hash=?',(user['token_hash'],))
        return {'status':'signed_out'}
    @app.get('/api/cases')
    def cases(user=Depends(auth)):
        from .integrations import integration_status
        with store.connect() as db:
            cs=[view(db,json.loads(r['body'])) for r in db.execute('SELECT body FROM cases ORDER BY id')]
            return dict(cases=cs,cash=store.cash(db),integrations=integration_status())
    @app.get('/api/cases/{cid}')
    def case(cid:str,user=Depends(auth)):
        with store.connect() as db:return view(db,getcase(db,cid))
    @app.post('/api/cases/{cid}/investigate')
    def investigate_case(cid:str,user=Depends(auth)):
        if user['role'] not in ('analyst','controller'):raise HTTPException(403,'Reviewer role required')
        from .integrations import investigate
        with store.connect() as db:
            c=getcase(db,cid); _,decision,_=evaluate(c,store.cash(db),store.paid(db))
        result=investigate(c,decision)
        with store.transaction() as db:
            fresh=getcase(db,cid,c['version'])
            fresh['investigation']=result;store.save(db,fresh);store.event(db,fresh,'investigation_completed',user['username'],{'mode':result['mode'],'trace_id':result.get('trace_id')})
            return view(db,fresh)
    @app.post('/api/cases/{cid}/verify')
    def verify(cid:str,body:Verification,user=Depends(auth)):
        role(user,'analyst')
        with store.transaction() as db:
            c=getcase(db,cid,body.version)
            if c['state']!='review':raise HTTPException(409,'Released cases cannot be verified again')
            if body.contact_id!=c['trusted_contact']['id'] or body.destination!=c['destination']:raise HTTPException(422,'Use the established contact and exact current destination')
            c['version']+=1;c['approval']=None
            c['verification']=dict(actor=user['username'],contact_id=body.contact_id,destination=body.destination,note=body.note,created_at=datetime.now(UTC).isoformat())
            eid='verify-'+str(uuid.uuid4())
            c['evidence'].append(evidence(eid,'Independent beneficiary verification','independent_verification',dict(destination=body.destination,note=body.note),actor=user['username'],source=body.contact_id))
            c['bank_evidence_ids'].append(eid)
            store.save(db,c);store.event(db,c,'beneficiary_verified',user['username'],{'evidence_id':eid})
            return view(db,c)
    @app.post('/api/cases/{cid}/approve')
    def approve(cid:str,body:ApprovalRequest,user=Depends(auth)):
        role(user,'controller')
        with store.transaction() as db:
            c=getcase(db,cid,body.version)
            if c['state']!='review':raise HTTPException(409,'Case has already been released')
            decision,result,_=evaluate(c,store.cash(db),store.paid(db))
            if body.decision_fingerprint!=decision.decision_fingerprint:raise HTTPException(409,'Decision context changed; refresh and review the new cash and evidence state')
            if result['status']!='WAITING_HUMAN':raise HTTPException(409,'Controls have not passed: '+', '.join(result['reasons']))
            if c['verification'] and c['verification']['actor']==user['username']:raise HTTPException(403,'Verifier cannot approve the same payment')
            now=datetime.now(UTC)
            grant=create_approval_for_decision(decision,approver=user['username'],issued_at=now,expires_at=now+timedelta(minutes=5),secret_key=store.key)
            c['approval']=dict(id=str(uuid.uuid4()),expires_at=grant.expires_at.isoformat(),revoked=False,approver=user['username'],grant=grant.to_dict())
            # Approval does not change the version of the evidence it authorizes.
            store.save(db,c);store.event(db,c,'approval_granted',user['username'],{'approval_id':c['approval']['id'],'binding':decision.to_dict()})
            return view(db,c)
    @app.post('/api/cases/{cid}/revoke')
    def revoke(cid:str,body:Reason,user=Depends(auth)):
        role(user,'controller')
        with store.transaction() as db:
            c=getcase(db,cid,body.version)
            if c['state']!='review' or not c['approval']:raise HTTPException(409,'No pending approval to revoke')
            c['approval']['revoked']=True;store.save(db,c);store.event(db,c,'approval_revoked',user['username'],{'reason':body.reason})
            return view(db,c)
    @app.post('/api/cases/{cid}/mutate')
    def mutate(cid:str,body:Mutation,user=Depends(auth)):
        role(user,'analyst')
        with store.transaction() as db:
            c=getcase(db,cid,body.version)
            if c['state']!='review':raise HTTPException(409,'Released cases cannot be mutated')
            if body.destination==c['destination']:raise HTTPException(422,'Choose a different synthetic destination')
            c['destination']=body.destination;c['version']+=1
            eid='changed-'+str(uuid.uuid4());c['evidence'].append(evidence(eid,'New unverified change request','untrusted_request',{'destination':body.destination},source='fixture:stress-test'))
            c['bank_evidence_ids']=[eid]
            store.save(db,c);store.event(db,c,'destination_changed',user['username'],{'destination':body.destination})
            return view(db,c)
    @app.post('/api/cases/{cid}/execute')
    def execute(cid:str,body:Execution,user=Depends(auth)):
        role(user,'controller')
        request_hash=digest({'case_id':cid,'version':body.version})
        with store.transaction() as db:
            previous=db.execute('SELECT * FROM idempotency WHERE key=?',(body.idempotency_key,)).fetchone()
            if previous:
                if previous['request_hash']!=request_hash:raise HTTPException(409,'Idempotency key belongs to a different request')
                c=getcase(db,cid)
                stored=db.execute('SELECT body FROM ledger WHERE id=?',(previous['ledger_id'],)).fetchone()
                if not stored or not c['ledger'] or previous['ledger_id']!=c['ledger']['id']:raise HTTPException(409,'Idempotency receipt integrity failed')
                ledger=json.loads(stored['body'])
                if ledger!=c['ledger']:raise HTTPException(409,'Persisted effect integrity failed')
                return dict(case=view(db,c),ledger=ledger,replayed=True)
            c=getcase(db,cid,body.version)
            if c['state']!='review':raise HTTPException(409,'Payment already released')
            valid,reason,decision,bound=approval_check(c,db)
            if not valid:raise HTTPException(409,'Approval invalid: '+reason)
            if decision.result.disposition.value!='WAITING_HUMAN':raise HTTPException(409,'Fresh controls did not pass')
            grant,kwargs=bound
            used=consume_approval(grant,**kwargs)
            ledger=dict(id=str(uuid.uuid4()),case_id=cid,vendor=c['vendor'],invoice_id=c['invoice_id'],amount_minor=c['amount_minor'],currency=c['currency'],destination=c['destination'],candidate_fingerprint=decision.candidate_fingerprint,created_at=datetime.now(UTC).isoformat(),mode='synthetic_ledger',compensated=False)
            db.execute('INSERT INTO ledger VALUES(?,?,?,?,?)',(ledger['id'],cid,c['vendor'],c['invoice_id'],json.dumps(ledger)))
            db.execute('INSERT INTO idempotency VALUES(?,?,?)',(body.idempotency_key,request_hash,ledger['id']))
            # Read back the persisted effect before committing; unexpected differences roll back all writes.
            stored=json.loads(db.execute('SELECT body FROM ledger WHERE id=?',(ledger['id'],)).fetchone()['body'])
            if stored!=ledger:raise RuntimeError('Ledger verification failed')
            cash=store.cash(db);cash['balance_minor']-=c['amount_minor'];store.set_cash(db,cash)
            c['approval']['grant']=used.to_dict();c['ledger']=ledger;c['state']='released';c['version']+=1
            store.save(db,c);store.event(db,c,'simulated_payment_verified',user['username'],{'ledger_id':ledger['id'],'effect_verified':True,'candidate_fingerprint':decision.candidate_fingerprint})
            return dict(case=view(db,c),ledger=ledger,replayed=False)
    @app.post('/api/cases/{cid}/compensate')
    def compensate(cid:str,body:Reason,user=Depends(auth)):
        role(user,'controller')
        with store.transaction() as db:
            c=getcase(db,cid,body.version)
            if c['state']!='released':raise HTTPException(409,'Only an uncompensated simulated payment can be reversed')
            # Immutable compensating event. Original debit remains in ledger for audit and deduplication.
            c['state']='compensated';c['version']+=1
            c['compensation']=dict(id=str(uuid.uuid4()),amount_minor=c['amount_minor'],original_ledger_id=c['ledger']['id'],reason=body.reason)
            cash=store.cash(db);cash['balance_minor']+=c['amount_minor'];store.set_cash(db,cash)
            store.save(db,c);store.event(db,c,'simulation_compensated',user['username'],c['compensation'])
            return view(db,c)
    @app.get('/api/export/{cid}')
    def export(cid:str,user=Depends(auth)):
        with store.connect() as db:
            c=getcase(db,cid)
            return JSONResponse(dict(schema_version='1.0',synthetic=True,case=view(db,c),cash=store.cash(db),journal=store.audit(db,c),verification_note='HMAC requires the protected server key; hashes do not prove supplier truth. Exported anchor should be retained independently.'),headers={'Content-Disposition':f'attachment; filename="mandate-{c["id"]}-audit.json"'})
    @app.get('/api/metrics')
    def metrics(user=Depends(auth)):
        from .integrations import integration_status
        with store.connect() as db:
            cs=[json.loads(r['body']) for r in db.execute('SELECT body FROM cases')]
            vs=[view(db,c) for c in cs];events=[e for c in cs for e in store.events(db,c['id'])]
            n=len(cs); released=sum(c['state'] in ('released','compensated') for c in cs)
            def m(name,value,unit,denominator,description):return dict(name=name,value=value,unit=unit,denominator=denominator,description=description)
            ms=[m('Cases loaded',n,'count',None,'Synthetic payment cases in this database'),m('Independent beneficiary evidence',sum(v['decision']['independent_verified'] for v in vs),'cases',n,'At least one authorized source root for current destination'),m('Verified simulated effects',sum(e['event_type']=='simulated_payment_verified' for e in events),'count',released,'Recorded only after exact ledger readback'),m('Audit integrity',sum(v['journal']['valid'] for v in vs),'cases',n,'HMAC linkage plus current snapshot; same-database anchors'),m('Pending independent verification',sum(not v['decision']['independent_verified'] for v in vs),'cases',n,'Does not equate to fraud'),m('Approvals revoked',sum(e['event_type']=='approval_revoked' for e in events),'count',None,'Observed revocation events'),m('Bank source roots',sum(v['decision']['root_count'] for v in vs),'count',n,'Deduplicated root count, not a confidence score')]
            return dict(metrics=ms,journal=dict(valid=all(v['journal']['valid'] for v in vs),count=len(events)),integrations=integration_status(),admit_coverage='Unassessed: separate ADMIT definition not supplied',fraud_prevention_rate=None)
    from .security import init_profile,respond,add_resolution,export_questionnaire
    with store.transaction() as db:
        db.execute('CREATE TABLE IF NOT EXISTS security_profiles (id INTEGER PRIMARY KEY, body TEXT NOT NULL, mac TEXT NOT NULL)')
    def security_read(db):
        row=db.execute('SELECT body,mac FROM security_profiles WHERE id=1').fetchone()
        if not row: return init_profile()
        expected=hmac.new(store.key,row['body'].encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected,row['mac']): raise HTTPException(409,'Security profile integrity failed')
        return json.loads(row['body'])
    def security_write(db,profile):
        body=json.dumps(profile,sort_keys=True,separators=(',',':'))
        mac=hmac.new(store.key,body.encode(),hashlib.sha256).hexdigest()
        db.execute('INSERT INTO security_profiles VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body,mac=excluded.mac',(body,mac))
    @app.get('/security')
    def security_index(): return FileResponse(ROOT/'static/security.html')
    @app.get('/api/security/profile')
    def security_profile(user=Depends(auth)):
        with store.connect() as db:
            return security_read(db)
    @app.post('/api/security/chat')
    def security_chat(body:SecurityMessage,user=Depends(auth)):
        if user['role'] not in ('analyst','controller'): raise HTTPException(403,'Reviewer role required')
        with store.transaction() as db:
            profile=security_read(db)
            if profile['revision']!=body.expected_revision: raise HTTPException(409,'Profile changed; reload before replying')
            profile,reply=respond(profile,body.message,user['username'])
            security_write(db,profile)
            return dict(profile=profile,reply=reply,mode='deterministic-local')
    @app.post('/api/security/resolution-fixture')
    def security_resolution(body:SecurityRevision,user=Depends(auth)):
        if user['role'] not in ('analyst','controller'): raise HTTPException(403,'Reviewer role required')
        with store.transaction() as db:
            profile=security_read(db)
            if profile['revision']!=body.expected_revision: raise HTTPException(409,'Profile changed; reload before continuing')
            profile=add_resolution(profile,user['username']);security_write(db,profile)
            return profile
    @app.get('/api/security/questionnaire')
    def security_export(user=Depends(auth)):
        with store.connect() as db: return export_questionnaire(security_read(db))
    from .money_operations_service import init_money_operations,register_money_operations
    from .money_operations_contracts import register_money_operations_extensions
    init_money_operations(store)
    register_money_operations(app,store,auth)
    register_money_operations_extensions(app,store,auth)
    return app
