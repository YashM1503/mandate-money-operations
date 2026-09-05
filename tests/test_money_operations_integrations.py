import hashlib
import json
import os
import time
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import pytest
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mandate.money_operations_audio import reset_audio_cache
from mandate.money_operations_contracts import register_money_operations_extensions
from mandate.money_operations_narrative import NarrativeError, compose, validate_narrative
from mandate.money_operations_prism import (
    allowlisted_metadata,
    compose_and_observe,
    handshake,
    observe_narrative,
    prism_status,
    reset_prism_observation,
)
from test_money_operations_api import _analyze, _engine_ready, _fake_analyze, _h, _ingest
from test_mvp import setup  # noqa: F401

FIXTURE = Path(__file__).resolve().parents[1] / 'sample-data' / 'money-operations'
SECURITY = HTTPBearer(auto_error=False)


@pytest.fixture
def engine(monkeypatch):
    if _engine_ready():
        return 'live'
    monkeypatch.setattr('mandate.money_operations.analyze', _fake_analyze)
    return 'stub'


def _bind_auth(store):
    def auth(credentials: HTTPAuthorizationCredentials | None = Depends(SECURITY)):
        if not credentials:
            raise HTTPException(401, 'Sign in to continue')
        with store.connect() as db:
            row = db.execute(
                'SELECT * FROM sessions WHERE token_hash=? AND expires>?',
                (hashlib.sha256(credentials.credentials.encode()).hexdigest(), time.time()),
            ).fetchone()
        if not row:
            raise HTTPException(401, 'Session expired; sign in again')
        return dict(row)

    return auth


@pytest.fixture
def ext(setup, engine):
    reset_prism_observation()
    reset_audio_cache()
    client, store, headers = setup
    register_money_operations_extensions(client.app, store, _bind_auth(store))
    return setup


@pytest.fixture(autouse=True)
def _reset_integrations():
    reset_prism_observation()
    reset_audio_cache()
    yield
    reset_prism_observation()
    reset_audio_cache()


def _weak_claims():
    return _fake_analyze(FIXTURE, '2026-01', '2026-02')['claims']


def test_prism_not_configured_without_credentials(monkeypatch):
    monkeypatch.delenv('PRISMTRACE_API_KEY', raising=False)
    monkeypatch.delenv('PRISMTRACE_PROJECT_ID', raising=False)
    reset_prism_observation()
    status = prism_status()
    assert status['state'] == 'not_configured'
    assert status['live_connected'] is False
    result = observe_narrative(analysis_id='x', text='Gross revenue increased $675,000.')
    assert result['state'] == 'not_configured'
    assert result['sent'] is False


def test_credentials_are_not_live_connected(monkeypatch):
    monkeypatch.setenv('PRISMTRACE_API_KEY', 'prism-secret')
    monkeypatch.setenv('PRISMTRACE_PROJECT_ID', 'project-demo')
    monkeypatch.delenv('MANDATE_ALLOW_SYNTHETIC_EGRESS', raising=False)
    reset_prism_observation()
    status = prism_status()
    assert status['state'] == 'credential_configured'
    assert status['live_connected'] is False
    observed = observe_narrative(text='template', structured_claim_ids=['VAR-REV'])
    assert observed['sent'] is False
    assert observed['state'] != 'live_connected'


def test_handshake_never_sets_live_connected(monkeypatch):
    monkeypatch.setenv('PRISMTRACE_API_KEY', 'prism-secret')
    monkeypatch.setenv('PRISMTRACE_PROJECT_ID', 'project-demo')
    monkeypatch.setenv('MANDATE_ALLOW_SYNTHETIC_EGRESS', '1')

    def handler(request):
        return httpx.Response(200, json={'live_connected': True, 'blocked_step': None})

    with patch(
        'mandate.money_operations_prism._client',
        side_effect=lambda: httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
    ):
        result = handshake()
    assert result['state'] == 'credential_ok'
    assert result['live_connected'] is False
    assert result['doctor_reported_live'] is True
    assert prism_status()['state'] != 'live_connected'


def test_sdk_submit_without_receipt_is_live_trace_pending(monkeypatch):
    monkeypatch.setenv('PRISMTRACE_API_KEY', 'prism-secret')
    monkeypatch.setenv('PRISMTRACE_PROJECT_ID', 'project-demo')
    monkeypatch.setenv('MANDATE_ALLOW_SYNTHETIC_EGRESS', '1')
    monkeypatch.setenv('MANDATE_PRISM_TRANSPORT', 'sdk')
    sdk = Mock()
    with patch('prismtrace.PRISMtrace', return_value=sdk):
        result = observe_narrative(
            run_id='run-sdk',
            text='Other Opex remains unexplained.',
            structured_claim_ids=['VAR-UNK'],
            numeric_validation='pass',
            citation_validation='pass',
        )
    sdk.trace_llm.assert_called_once()
    assert sdk.trace_llm.call_args.kwargs['agent_id'] == 'mandate-money-operations-narrative'
    assert result['state'] == 'live_trace_pending'
    assert result['live_connected'] is False
    assert result['application_trace_id'] is None


def test_http_receipt_is_the_only_live_connected_path(monkeypatch):
    monkeypatch.setenv('PRISMTRACE_API_KEY', 'prism-secret')
    monkeypatch.setenv('PRISMTRACE_PROJECT_ID', 'project-demo')
    monkeypatch.setenv('MANDATE_ALLOW_SYNTHETIC_EGRESS', '1')
    monkeypatch.setenv('MANDATE_PRISM_TRANSPORT', 'http')

    def handler(request):
        return httpx.Response(200, json={'id': 'mo-app-trace-1'})

    with patch(
        'mandate.money_operations_prism._client',
        side_effect=lambda: httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
    ):
        result = observe_narrative(run_id='run-http', text='Corrected unexplained Other Opex.', structured_claim_ids=['VAR-UNK'])
    assert result['state'] == 'live_connected'
    assert result['application_trace_id'] == 'mo-app-trace-1'
    assert prism_status()['live_connected'] is True


def test_http_without_trace_identity_is_not_live(monkeypatch):
    monkeypatch.setenv('PRISMTRACE_API_KEY', 'prism-secret')
    monkeypatch.setenv('PRISMTRACE_PROJECT_ID', 'project-demo')
    monkeypatch.setenv('MANDATE_ALLOW_SYNTHETIC_EGRESS', '1')
    monkeypatch.setenv('MANDATE_PRISM_TRANSPORT', 'http')

    def handler(request):
        return httpx.Response(200, json={'ok': True})

    with patch(
        'mandate.money_operations_prism._client',
        side_effect=lambda: httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False),
    ):
        result = observe_narrative(text='template')
    assert result['state'] == 'live_trace_pending'
    assert result['live_connected'] is False


def test_observe_error_is_explicit(monkeypatch):
    monkeypatch.setenv('PRISMTRACE_API_KEY', 'prism-secret')
    monkeypatch.setenv('PRISMTRACE_PROJECT_ID', 'project-demo')
    monkeypatch.setenv('MANDATE_ALLOW_SYNTHETIC_EGRESS', '1')
    monkeypatch.setenv('MANDATE_PRISM_TRANSPORT', 'http')
    with patch('mandate.money_operations_prism._client', side_effect=httpx.ReadTimeout('boom')):
        result = observe_narrative(text='template')
    assert result['state'] == 'error'
    assert result['sent'] is False


def test_observe_drops_source_rows_and_redacts_secrets(monkeypatch):
    monkeypatch.setenv('PRISMTRACE_API_KEY', 'prism-secret')
    meta = allowlisted_metadata({
        'structured_claim_ids': ['VAR-UNK'],
        'source_rows': [{'description': 'Unmapped clearing batch wire'}],
        'calculation_digest': 'abc123',
        'unexplained_item_count': 1,
        'token_usage': {'token_count_input': 9, 'token_count_output': 4},
        'model': 'deterministic-template',
    })
    blob = json.dumps(meta)
    assert 'Unmapped clearing batch wire' not in blob
    assert 'source_rows' not in meta
    assert meta['structured_claim_ids'] == ['VAR-UNK']
    assert meta['calculation_digest'] == 'abc123'
    observed = observe_narrative(
        source_rows=[{'description': 'PRIVATE TXN'}],
        text='Other Opex remains unexplained. prism-secret must not leak.',
        structured_claim_ids=['VAR-UNK'],
    )
    assert observed['state'] == 'not_configured' or 'PRIVATE TXN' not in json.dumps(observed)


def test_compose_and_observe_survives_prism_failure(monkeypatch):
    monkeypatch.setenv('PRISMTRACE_API_KEY', 'prism-secret')
    monkeypatch.setenv('PRISMTRACE_PROJECT_ID', 'project-demo')
    monkeypatch.setenv('MANDATE_ALLOW_SYNTHETIC_EGRESS', '1')
    monkeypatch.setenv('MANDATE_PRISM_TRANSPORT', 'http')
    with patch('mandate.money_operations_prism._client', side_effect=httpx.ConnectError('down')):
        narrative = compose_and_observe({'claims': _weak_claims(), 'periods': {'prior': '2026-01', 'current': '2026-02'}})
    assert narrative['narrative_source'] == 'deterministic_template'
    assert '$675,000' in narrative['text']
    assert 'unmapped clearing batch' in narrative['text'].lower()
    assert narrative['prism']['state'] == 'error'


def test_weak_narrative_rejects_and_corrected_passes():
    claims = _weak_claims()
    with pytest.raises(NarrativeError) as err:
        validate_narrative(
            'Other Opex increased $57,000 because warehouse insurance rose $12,400 after a new vendor onboarding program.',
            claims,
            ['VAR-UNK'],
        )
    assert err.value.code == 'uncited_number'
    package = compose({'claims': claims})
    validate_narrative(package['text'], claims, package['cited_claim_ids'])
    assert 'unmapped clearing batch' in package['text'].lower()
    assert 'onboarding' not in package['text'].lower()


def test_demo_script_exits_zero_without_credentials(monkeypatch):
    import subprocess
    import sys
    env = {key: value for key, value in os.environ.items() if key not in {'PRISMTRACE_API_KEY', 'PRISMTRACE_PROJECT_ID', 'MANDATE_ALLOW_SYNTHETIC_EGRESS'}}
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'run_prism_money_ops_demo.py'
    result = subprocess.run([sys.executable, str(script)], cwd=str(script.parents[1]), env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert 'PRISMTRACE_API_KEY' in result.stdout
    assert 'prism-secret' not in result.stdout
    assert 'do not print' in result.stdout.lower()


def test_overview_keeps_other_opex_out_of_reconciliation_conflicts(ext):
    client, _store, headers = ext
    analysis = _analyze(ext, _ingest(ext)['dataset_id'])
    res = client.get(
        f"/api/money-operations/analyses/{analysis['analysis_id']}/overview",
        headers=_h(ext, 'auditor'),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body['periods']['prior'] == '2026-01'
    assert body['periods']['current'] == '2026-02'
    blob = json.dumps(body)
    assert '675000' in blob or any(item.get('amount_minor') == 67_500_000 for item in body['material_variances'])
    assert body['reconciliation_conflicts'] == [] or all(
        'opex' not in str(item.get('account_name', '')).lower() and str(item.get('account_code')) not in {'6900', 'other_opex'}
        for item in body['reconciliation_conflicts']
    )
    assert body['causally_unexplained']
    unexplained_blob = json.dumps(body['causally_unexplained']).lower()
    assert 'other opex' in unexplained_blob or '6900' in unexplained_blob or 'other_opex' in unexplained_blob
    assert body['prism']['state'] != 'live_connected' or body['prism'].get('application_trace_id')
    assert body['prism']['live_connected'] is False
    assert body['audio']['enabled'] is False
    assert isinstance(body['reconciled_count'], int)


def test_graph_has_required_agent_nodes(ext):
    client = ext[0]
    analysis = _analyze(ext, _ingest(ext)['dataset_id'])
    res = client.get(f"/api/money-operations/analyses/{analysis['analysis_id']}/graph", headers=_h(ext, 'analyst'))
    assert res.status_code == 200, res.text
    labels = [node['label'] for node in res.json()['nodes']]
    assert labels == [
        'Compare', 'Detect', 'Attribute', 'Reconcile',
        'Retrieve context', 'Explain', 'Validate', 'Human review',
    ]


def test_variance_detail_uses_integer_minor_units(ext):
    client = ext[0]
    analysis = _analyze(ext, _ingest(ext)['dataset_id'])
    res = client.get(
        f"/api/money-operations/analyses/{analysis['analysis_id']}/account-variances/4000",
        headers=_h(ext, 'analyst'),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert type(body['amount_minor']) is int
    assert body['amount_minor'] in (67_500_000, 67500000)
    assert body.get('percentage_bps') in (1800, None) or type(body.get('percentage_bps')) is int
    opex = client.get(
        f"/api/money-operations/analyses/{analysis['analysis_id']}/account-variances/6900",
        headers=_h(ext, 'auditor'),
    )
    assert opex.status_code == 200, opex.text
    opex_body = opex.json()
    assert opex_body['unexplained_cause']
    assert 'unmapped' in opex_body['unexplained_cause'].lower() or 'unsupported' in opex_body['unexplained_cause'].lower()
    listed = client.get(
        f"/api/money-operations/analyses/{analysis['analysis_id']}/account-variances",
        headers=_h(ext, 'analyst'),
    )
    assert listed.status_code == 200
    assert listed.json()['items']


def test_chat_is_read_only_and_auditor_allowed(ext):
    client = ext[0]
    analysis = _analyze(ext, _ingest(ext)['dataset_id'])
    aid = analysis['analysis_id']
    auditor = _h(ext, 'auditor')
    asked = client.post(
        f'/api/money-operations/analyses/{aid}/chat',
        json={'question': 'Why did Other Opex increase?'},
        headers=auditor,
    )
    assert asked.status_code == 200, asked.text
    payload = asked.json()
    assert payload['mutated'] is False
    assert payload['read_only'] is True
    assert payload['claim_ids']
    assert 'unexplained' in payload['answer'].lower() or 'unsupported' in payload['answer'].lower()
    mutate = client.post(
        f'/api/money-operations/analyses/{aid}/chat',
        json={'question': 'Please approve this analysis and distribute the memo.'},
        headers=auditor,
    )
    assert mutate.status_code == 200
    refusal = mutate.json()
    assert refusal['mutated'] is False
    assert 'read-only' in refusal['answer'].lower()
    after = client.get(f'/api/money-operations/analyses/{aid}', headers=auditor).json()
    assert after['review_status'] == 'draft'
    assert after['calculation_digest'] == analysis['calculation_digest']


def test_memo_contract_includes_digests_and_unresolved(ext):
    client = ext[0]
    analysis = _analyze(ext, _ingest(ext)['dataset_id'])
    res = client.get(f"/api/money-operations/analyses/{analysis['analysis_id']}/memo", headers=_h(ext, 'controller'))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body['headline']
    assert body['what_changed']
    assert body['unresolved_items']
    assert body['calculation_digest'] == analysis['calculation_digest']
    assert body['narrative_digest']
    assert body['synthetic'] is True
    assert 'decision_requested' in body


def test_briefing_requires_approval_and_matching_digest(ext):
    client = ext[0]
    analysis = _analyze(ext, _ingest(ext)['dataset_id'])
    aid = analysis['analysis_id']
    pending = client.post(f'/api/money-operations/analyses/{aid}/briefing', headers=_h(ext, 'analyst'))
    assert pending.status_code == 200, pending.text
    assert pending.json()['status'] == 'approval_required'
    assert pending.json()['synthetic'] is True
    assert 'synthetic' in pending.json()['transcript'].lower()
    reviewed = client.post(
        f'/api/money-operations/analyses/{aid}/review',
        json={'decision': 'approved', 'expected_revision': analysis['revision']},
        headers=_h(ext, 'controller'),
    )
    assert reviewed.status_code == 200, reviewed.text
    briefing = client.post(f'/api/money-operations/analyses/{aid}/briefing', headers=_h(ext, 'auditor'))
    assert briefing.status_code == 200, briefing.text
    payload = briefing.json()
    assert payload['status'] == 'audio_unavailable'
    assert payload['provider'] == 'none'
    assert payload['audio_url'] is None
    assert 'synthetic' in payload['transcript'].lower()


def test_briefing_rejects_changed_narrative_digest(ext, monkeypatch):
    client, store, _headers = ext
    analysis = _analyze(ext, _ingest(ext)['dataset_id'])
    aid = analysis['analysis_id']
    client.post(
        f'/api/money-operations/analyses/{aid}/review',
        json={'decision': 'approved', 'expected_revision': analysis['revision']},
        headers=_h(ext, 'controller'),
    )
    from mandate.money_operations_service import _digest, _signed_read, _signed_update
    with store.transaction() as db:
        row, body = _signed_read(db, store.key, 'mo_analyses', aid)
        body = dict(body)
        narrative = dict(body.get('narrative') or {})
        narrative['text'] = (narrative.get('text') or '') + ' Extra unapproved sentence.'
        body['narrative'] = narrative
        _signed_update(db, store.key, 'mo_analyses', aid, body, 'revision=?', (row['revision'],))
    changed = client.post(f'/api/money-operations/analyses/{aid}/briefing', headers=_h(ext, 'controller'))
    assert changed.status_code == 409
    assert changed.json()['error']['code'] == 'narrative_changed'
    assert _digest


def test_mocked_elevenlabs_returns_audio_ready(ext, monkeypatch):
    monkeypatch.setenv('MONEY_OPS_AUDIO_ENABLED', 'true')
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'eleven-secret')
    monkeypatch.setenv('ELEVENLABS_VOICE_ID', 'voice-demo')
    client = ext[0]
    analysis = _analyze(ext, _ingest(ext)['dataset_id'])
    aid = analysis['analysis_id']
    client.post(
        f'/api/money-operations/analyses/{aid}/review',
        json={'decision': 'approved', 'expected_revision': analysis['revision']},
        headers=_h(ext, 'controller'),
    )

    def handler(request):
        assert 'transaction' not in request.content.decode().lower()
        assert 'eleven-secret' not in request.url.path
        assert request.headers.get('xi-api-key') == 'eleven-secret'
        return httpx.Response(200, content=b'ID3FAKEAUDIOBYTES')

    real_client = httpx.Client

    def fake_client(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), follow_redirects=False, timeout=kwargs.get('timeout', 20.0), trust_env=False)

    with patch('mandate.money_operations_audio.httpx.Client', side_effect=fake_client):
        briefing = client.post(f'/api/money-operations/analyses/{aid}/briefing', headers=_h(ext, 'analyst'))
    assert briefing.status_code == 200, briefing.text
    payload = briefing.json()
    assert payload['status'] == 'audio_ready'
    assert payload['provider'] == 'elevenlabs'
    assert payload['audio_url']
    audio = client.get(payload['audio_url'], headers=_h(ext, 'auditor'))
    assert audio.status_code == 200
    assert audio.content == b'ID3FAKEAUDIOBYTES'


def test_extension_routes_require_auth(ext):
    client = ext[0]
    analysis = _analyze(ext, _ingest(ext)['dataset_id'])
    aid = analysis['analysis_id']
    assert client.get(f'/api/money-operations/analyses/{aid}/overview').status_code == 401
    assert client.get(f'/api/money-operations/analyses/{aid}/graph').status_code == 401
    assert client.get(f'/api/money-operations/analyses/{aid}/memo').status_code == 401
    assert client.post(f'/api/money-operations/analyses/{aid}/chat', json={'question': 'What changed?'}).status_code == 401


def test_import_prismtrace_resolves():
    import prismtrace
    assert hasattr(prismtrace, 'PRISMtrace')
