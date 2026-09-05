"""SQLite transaction boundary and HMAC journal. Single instance persistent volume only."""
from contextlib import contextmanager
from datetime import datetime, UTC
from pathlib import Path
import hmac
import json
import sqlite3
import uuid
from .fixtures import seed_cases,digest
from .core.journal import create_event,verify_chain,journal_event_from_dict

SCHEMA='''
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS cases(id TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(case_id TEXT NOT NULL, seq INTEGER NOT NULL, body TEXT NOT NULL, PRIMARY KEY(case_id,seq));
CREATE TABLE IF NOT EXISTS anchors(case_id TEXT PRIMARY KEY, seq INTEGER NOT NULL, mac TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ledger(id TEXT PRIMARY KEY, case_id TEXT UNIQUE NOT NULL, vendor TEXT NOT NULL, invoice_id TEXT NOT NULL, body TEXT NOT NULL, UNIQUE(vendor,invoice_id));
CREATE TABLE IF NOT EXISTS idempotency(key TEXT PRIMARY KEY, request_hash TEXT NOT NULL, ledger_id TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, username TEXT NOT NULL, role TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS login_attempts(client TEXT PRIMARY KEY, started REAL NOT NULL, count INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS mo_datasets(id TEXT PRIMARY KEY, status TEXT NOT NULL, revision INTEGER NOT NULL, entity_id TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL, body_json TEXT NOT NULL, mac TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mo_sources(id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES mo_datasets(id), file_name TEXT NOT NULL, sha256 TEXT NOT NULL, byte_size INTEGER NOT NULL, row_count INTEGER NOT NULL, schema_version TEXT NOT NULL, metadata_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mo_summary_rows(id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES mo_datasets(id), period TEXT NOT NULL, entity_id TEXT NOT NULL, account_code TEXT NOT NULL, account_name TEXT NOT NULL, account_type TEXT NOT NULL, currency TEXT NOT NULL, amount_minor INTEGER NOT NULL, source_row_id TEXT NOT NULL, source_file TEXT NOT NULL DEFAULT '', source_row INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS mo_transactions(id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES mo_datasets(id), transaction_id TEXT NOT NULL, posted_date TEXT NOT NULL, period TEXT NOT NULL, entity_id TEXT NOT NULL, account_code TEXT NOT NULL, amount_minor INTEGER NOT NULL, currency TEXT NOT NULL, dimensions_json TEXT NOT NULL, source_file TEXT NOT NULL, source_row_number INTEGER NOT NULL, customer_id TEXT, product_id TEXT, UNIQUE(dataset_id, transaction_id));
CREATE TABLE IF NOT EXISTS mo_analyses(id TEXT PRIMARY KEY, dataset_id TEXT NOT NULL REFERENCES mo_datasets(id), prior_period TEXT NOT NULL, current_period TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL, calculation_version TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL, body_json TEXT NOT NULL, mac TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mo_claims(id TEXT PRIMARY KEY, analysis_id TEXT NOT NULL REFERENCES mo_analyses(id), original_id TEXT NOT NULL, account_code TEXT NOT NULL, claim_type TEXT NOT NULL, status TEXT NOT NULL, value_json TEXT NOT NULL, formula TEXT NOT NULL, source_ids_json TEXT NOT NULL, source_rows_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS mo_context(id TEXT PRIMARY KEY, entity_id TEXT NOT NULL, account_code TEXT NOT NULL, dimension TEXT, member TEXT, statement TEXT NOT NULL, status TEXT NOT NULL, actor TEXT NOT NULL, recorded_at TEXT NOT NULL, revision INTEGER NOT NULL, supersedes TEXT, period_scope_json TEXT NOT NULL, tombstoned INTEGER NOT NULL DEFAULT 0, analysis_id TEXT, supporting_claim_ids_json TEXT);
CREATE TABLE IF NOT EXISTS mo_reviews(id TEXT PRIMARY KEY, analysis_id TEXT NOT NULL REFERENCES mo_analyses(id), analysis_revision INTEGER NOT NULL, narrative_digest TEXT NOT NULL, decision TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, calculation_digest TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS mo_events(id TEXT PRIMARY KEY, aggregate_type TEXT NOT NULL, aggregate_id TEXT NOT NULL, revision INTEGER NOT NULL, event_type TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, body_json TEXT NOT NULL, prev_digest TEXT NOT NULL, digest TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_mo_summary_period ON mo_summary_rows(dataset_id, period, account_code);
CREATE INDEX IF NOT EXISTS idx_mo_txn_period ON mo_transactions(dataset_id, period, account_code);
CREATE INDEX IF NOT EXISTS idx_mo_claims_analysis ON mo_claims(analysis_id, account_code);
CREATE INDEX IF NOT EXISTS idx_mo_claims_original ON mo_claims(original_id);
CREATE INDEX IF NOT EXISTS idx_mo_context_lookup ON mo_context(entity_id, account_code, tombstoned);
CREATE INDEX IF NOT EXISTS idx_mo_events_agg ON mo_events(aggregate_type, aggregate_id, revision);
'''


def _table_columns(db, table):
    return {row[1] for row in db.execute(f'PRAGMA table_info({table})')}


def migrate_money_ops_schema(db):
    """Add Money Operations columns on existing HMAC databases without rewriting rows."""
    summary_cols = _table_columns(db, 'mo_summary_rows')
    if summary_cols:
        if 'source_file' not in summary_cols:
            db.execute("ALTER TABLE mo_summary_rows ADD COLUMN source_file TEXT NOT NULL DEFAULT ''")
        if 'source_row' not in summary_cols:
            db.execute('ALTER TABLE mo_summary_rows ADD COLUMN source_row INTEGER NOT NULL DEFAULT 0')
    txn_cols = _table_columns(db, 'mo_transactions')
    if txn_cols:
        if 'customer_id' not in txn_cols:
            db.execute('ALTER TABLE mo_transactions ADD COLUMN customer_id TEXT')
        if 'product_id' not in txn_cols:
            db.execute('ALTER TABLE mo_transactions ADD COLUMN product_id TEXT')
    review_cols = _table_columns(db, 'mo_reviews')
    if review_cols and 'calculation_digest' not in review_cols:
        db.execute("ALTER TABLE mo_reviews ADD COLUMN calculation_digest TEXT NOT NULL DEFAULT ''")


class Store:
    def __init__(self,path,key):
        self.path=Path(path); self.key=key
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)
            migrate_money_ops_schema(db)
        self.path.chmod(0o600)
        with self.transaction() as db:
            if not db.execute('SELECT 1 FROM settings WHERE key=?',('cash',)).fetchone():
                self.set_cash(db,dict(balance_minor=9000000,commitments_minor=3000000,reserve_minor=1000000,as_of=datetime.now(UTC).isoformat(),horizon_days=7,commitments=[{'label':'Payroll','amount_minor':2000000},{'label':'Rent and utilities','amount_minor':1000000}]))
            if not db.execute('SELECT 1 FROM cases LIMIT 1').fetchone():
                for c in seed_cases():
                    self.save(db,c)
                    self.event(db,c,'case_imported','fixture-loader',{'synthetic':True})
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10); db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON'); db.execute('PRAGMA busy_timeout=10000')
        try: yield db
        finally: db.close()
    @contextmanager
    def transaction(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
                db.commit()
            except Exception:
                db.rollback(); raise
    def get(self,db,cid):
        r=db.execute('SELECT body FROM cases WHERE id=?',(cid,)).fetchone()
        return json.loads(r['body']) if r else None
    def save(self,db,c):
        db.execute('INSERT INTO cases VALUES(?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body',(c['id'],json.dumps(c)))
    def cash(self,db):
        body=db.execute("SELECT body FROM settings WHERE key='cash'").fetchone()['body']
        mac=db.execute("SELECT body FROM settings WHERE key='cash_mac'").fetchone()
        if not mac or not hmac.compare_digest(mac['body'],hmac.digest(self.key,body.encode(),'sha256').hex()):
            raise ValueError('Cash snapshot integrity failed')
        return json.loads(body)
    def set_cash(self,db,cash):
        db.execute("INSERT INTO settings VALUES('cash',?) ON CONFLICT(key) DO UPDATE SET body=excluded.body",(json.dumps(cash),))
        mac=hmac.digest(self.key,json.dumps(cash).encode(),'sha256').hex()
        db.execute("INSERT INTO settings VALUES('cash_mac',?) ON CONFLICT(key) DO UPDATE SET body=excluded.body",(mac,))
    def paid(self,db): return {(r['vendor'],r['invoice_id']) for r in db.execute('SELECT vendor,invoice_id FROM ledger')}
    def events(self,db,cid): return [json.loads(r['body']) for r in db.execute('SELECT body FROM events WHERE case_id=? ORDER BY seq',(cid,))]
    def event(self,db,c,kind,actor,payload):
        anchor=db.execute('SELECT * FROM anchors WHERE case_id=?',(c['id'],)).fetchone()
        e=create_event(event_id=str(uuid.uuid4()),case_id=c['id'],run_id=c['id'],sequence=anchor['seq']+1 if anchor else 1,timestamp=datetime.now(UTC),event_type=kind,payload=dict(actor=actor,snapshot_hash=digest(c),**payload),prev_hash=anchor['mac'] if anchor else '0'*64,secret_key=self.key).to_dict()
        db.execute('INSERT INTO events VALUES(?,?,?)',(c['id'],e['sequence'],json.dumps(e)))
        db.execute('INSERT INTO anchors VALUES(?,?,?) ON CONFLICT(case_id) DO UPDATE SET seq=excluded.seq,mac=excluded.mac',(c['id'],e['sequence'],e['event_hash_or_mac']))
    def audit(self,db,c):
        rows=self.events(db,c['id']); anchor=db.execute('SELECT * FROM anchors WHERE case_id=?',(c['id'],)).fetchone()
        try:
            result=verify_chain([journal_event_from_dict(e) for e in rows],secret_key=self.key,expected_final_sequence=anchor['seq'] if anchor else None,expected_final_hash=anchor['mac'] if anchor else None)
            valid=result.valid and bool(rows) and bool(anchor) and rows[-1]['payload']['snapshot_hash']==digest(c)
            self.cash(db)
            persisted=db.execute('SELECT * FROM ledger WHERE case_id=?',(c['id'],)).fetchone()
            if c['ledger']:
                valid = valid and bool(persisted) and json.loads(persisted['body'])==c['ledger'] and persisted['id']==c['ledger']['id'] and persisted['vendor']==c['vendor'] and persisted['invoice_id']==c['invoice_id']
            elif persisted:
                valid=False
            return dict(valid=valid,count=len(rows),status=result.status.value if valid else 'INTEGRITY_FAILURE',anchor_scope='Same database; export to an independent trusted store to detect whole-database rollback',anchor=dict(anchor) if anchor else None)
        except (ValueError,KeyError,TypeError): return dict(valid=False,count=len(rows),status='INTEGRITY_FAILURE')
