"""PRISM observation for the Money Operations narrative boundary only.

Deterministic arithmetic is not traced as if PRISM calculated it. A handshake
is never live_connected. Only a received Money Operations application trace ID
in this worker can set live_connected.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from urllib.parse import urlsplit

import httpx

from .money_operations_narrative import NarrativeError, compose, validate_narrative

PRISM_STATES = (
    'not_configured',
    'credential_configured',
    'credential_ok',
    'live_trace_pending',
    'live_connected',
    'error',
)
AGENT_ID = 'mandate-money-operations-narrative'
DEFAULT_HOST = 'https://prism.blockconvey.com'
TEMPLATE_VERSION = 'mo-narrative-template-1.0'

_LOCK = threading.Lock()
_STATE = {
    'state': 'not_configured',
    'application_trace_id': None,
    'run_id': None,
    'handshake_ok': False,
    'last_error': None,
}

ALLOWED_META = frozenset({
    'analysis_id',
    'run_id',
    'prior_period',
    'current_period',
    'calculation_digest',
    'claim_ids',
    'structured_claim_ids',
    'retrieved_context_ids',
    'prompt_version',
    'template_version',
    'model',
    'provider',
    'narrative_source',
    'reconciliation_status',
    'unexplained_item_count',
    'numeric_validation',
    'citation_validation',
    'fallback',
    'error_state',
    'latency_ms',
    'token_usage',
})

_FORBIDDEN_KWARGS = frozenset({
    'source_rows',
    'transactions',
    'transaction_rows',
    'raw_rows',
    'credentials',
    'api_key',
    'customer_rows',
    'claims',
    'full_source_rows',
})


def reset_prism_observation() -> None:
    with _LOCK:
        _STATE.update(
            state='not_configured',
            application_trace_id=None,
            run_id=None,
            handshake_ok=False,
            last_error=None,
        )


def _creds() -> tuple[str | None, str | None]:
    key = os.getenv('PRISMTRACE_API_KEY') or None
    project = os.getenv('PRISMTRACE_PROJECT_ID') or None
    if key:
        key = key.strip() or None
    if project:
        project = project.strip() or None
    return key, project


def _egress_enabled() -> bool:
    return os.getenv('MANDATE_ALLOW_SYNTHETIC_EGRESS') == '1'


def _https_origin(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != 'https'
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ('', '/')
    ):
        raise ValueError('An HTTPS origin without credentials, query or fragment is required')
    return value.rstrip('/')


def _host() -> str:
    return _https_origin(os.getenv('PRISMTRACE_HOST', DEFAULT_HOST))


def _redact(value: str) -> str:
    text = value
    for name in ('PRISMTRACE_API_KEY', 'MANDATE_MODEL_KEY', 'ELEVENLABS_API_KEY'):
        secret = os.getenv(name)
        if secret:
            text = text.replace(secret, '[REDACTED_CREDENTIAL]')
    return text


def _set_state(state: str, **extra) -> None:
    if state not in PRISM_STATES:
        state = 'error'
    with _LOCK:
        if state == 'live_connected' and not extra.get('application_trace_id') and not _STATE.get('application_trace_id'):
            state = 'live_trace_pending'
        _STATE['state'] = state
        for key, value in extra.items():
            if key in _STATE:
                _STATE[key] = value


def _snapshot() -> dict:
    with _LOCK:
        observed = dict(_STATE)
    key, project = _creds()
    state = observed['state']
    if state == 'live_connected' and not observed.get('application_trace_id'):
        state = 'live_trace_pending'
        observed['state'] = state
    if state == 'not_configured' and key and project:
        state = 'credential_ok' if observed.get('handshake_ok') else 'credential_configured'
        observed['state'] = state
    return {
        'state': state,
        'prism': state,
        'live_connected': state == 'live_connected' and bool(observed.get('application_trace_id')),
        'application_trace_id': observed.get('application_trace_id'),
        'run_id': observed.get('run_id'),
        'handshake_ok': bool(observed.get('handshake_ok')),
        'credential_present': bool(key and project),
        'synthetic_egress_enabled': _egress_enabled(),
        'status_scope': 'current_worker_observations',
        'note': (
            'live_connected requires a received Money Operations application trace ID '
            'in this worker. A handshake or payment-adapter diagnostic is not sufficient.'
        ),
    }


def prism_status() -> dict:
    """Honest Money Operations PRISM observation. Never inherited from payments."""
    return _snapshot()


def _client() -> httpx.Client:
    return httpx.Client(timeout=15.0, follow_redirects=False, trust_env=False)


def handshake() -> dict:
    """Credential check only. Never promotes to live_connected."""
    key, project = _creds()
    if not key or not project:
        _set_state('not_configured', handshake_ok=False, application_trace_id=None)
        return {**prism_status(), 'reason': 'PRISMTRACE_API_KEY and PRISMTRACE_PROJECT_ID are required'}
    _set_state('credential_configured')
    if not _egress_enabled():
        return {
            **prism_status(),
            'reason': 'Synthetic egress opt-in is required for a handshake',
        }
    try:
        host = _host()
        with _client() as client:
            response = client.get(
                host + '/api/setup-doctor',
                params={'project_id': project},
                headers={'X-PRISMtrace-Key': key},
            )
        response.raise_for_status()
        body = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
        if not isinstance(body, dict):
            body = {}
        # Project-level doctor live_connected is not a Money Operations application trace.
        _set_state('credential_ok', handshake_ok=True, last_error=None)
        return {
            **prism_status(),
            'doctor_reported_live': body.get('live_connected') is True,
            'blocked_step': _redact(str(body.get('blocked_step') or ''))[:200] or None,
            'note': 'Handshake succeeded. live_connected remains unset until a Money Operations application trace ID is received.',
        }
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        _set_state('error', handshake_ok=False, last_error='handshake_failed')
        return {**prism_status(), 'reason': 'PRISM handshake failed; inspect configuration privately'}


def _clean_id_list(value) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip() and len(item) <= 120:
            out.append(item.strip())
        if len(out) >= 64:
            break
    return out


def _clean_token_usage(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    cleaned = {}
    for key in ('input', 'output', 'token_count_input', 'token_count_output', 'total'):
        item = value.get(key)
        if type(item) is int and 0 <= item < 10**9:
            cleaned[key] = item
    return cleaned or None


def allowlisted_metadata(payload: dict) -> dict:
    """Keep only narrative-boundary identifiers. Drop source rows and secrets."""
    meta: dict = {'source': 'mandate-money-operations', 'advisory_only': True, 'synthetic': True}
    for key in ALLOWED_META:
        if key not in payload:
            continue
        value = payload[key]
        if key in ('claim_ids', 'structured_claim_ids', 'retrieved_context_ids'):
            cleaned = _clean_id_list(value)
            if cleaned:
                meta[key] = cleaned
        elif key == 'token_usage':
            usage = _clean_token_usage(value)
            if usage:
                meta[key] = usage
        elif key in ('unexplained_item_count', 'latency_ms'):
            if type(value) is int and abs(value) < 10**9:
                meta[key] = value
        elif key == 'fallback':
            if isinstance(value, bool):
                meta[key] = value
        elif isinstance(value, str) and value.strip() and len(value) <= 200:
            meta[key] = _redact(value.strip())
    if 'structured_claim_ids' in meta and 'claim_ids' not in meta:
        meta['claim_ids'] = meta['structured_claim_ids']
    return meta


def _narrative_output(payload: dict) -> str:
    for key in ('output', 'narrative_text', 'text', 'body', 'headline'):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return _redact(value.strip())[:4000]
    source = payload.get('narrative_source') or 'deterministic-template'
    return f'Money Operations narrative observation ({source}). Synthetic claims only.'


def _record_received_trace(trace_id: str, run_id: str) -> None:
    if isinstance(trace_id, str) and trace_id.strip() and len(trace_id) <= 128:
        _set_state(
            'live_connected',
            application_trace_id=trace_id.strip(),
            run_id=run_id,
            last_error=None,
        )
    else:
        _set_state('live_trace_pending', run_id=run_id, last_error=None)


def _send_sdk(messages: list, output: str, model: str, latency_ms: int, run_id: str, metadata: dict) -> dict:
    key, project = _creds()
    host = _host()
    from prismtrace import PRISMtrace
    tracer = PRISMtrace(api_key=key, host=host, project_id=project, timeout=15)
    # SDK 0.4.2 trace_llm does not return an ingest receipt.
    tracer.trace_llm(
        model=model,
        input_messages=messages,
        output=output,
        latency_ms=latency_ms,
        token_count_input=int((metadata.get('token_usage') or {}).get('token_count_input') or 0),
        token_count_output=int((metadata.get('token_usage') or {}).get('token_count_output') or 0),
        trace_id=run_id,
        agent_id=AGENT_ID,
        agent_name='Money Operations narrative',
        metadata={**metadata, 'session_id': run_id, 'local_run_id': run_id},
    )
    tracer.flush(timeout=16)
    _set_state('live_trace_pending', run_id=run_id, last_error=None)
    return {'state': 'live_trace_pending', 'run_id': run_id, 'application_trace_id': None, 'transport': 'sdk'}


def _send_http(messages: list, output: str, model: str, latency_ms: int, run_id: str, metadata: dict) -> dict:
    key, project = _creds()
    host = _host()
    payload = {
        'project_id': project,
        'model': model,
        'input_messages': messages,
        'output_message': output,
        'latency_ms': latency_ms,
        'session_id': run_id,
        'agent_id': AGENT_ID,
        'trace_id': run_id,
        'metadata': {**metadata, 'session_id': run_id, 'local_run_id': run_id},
    }
    with _client() as client:
        response = client.post(host + '/api/traces', headers={'X-PRISMtrace-Key': key}, json=payload)
    response.raise_for_status()
    body = response.json() if response.content else {}
    if not isinstance(body, dict):
        body = {}
    received = body.get('id') or body.get('trace_id')
    if response.status_code == 200 and isinstance(received, str) and received.strip():
        _record_received_trace(received, run_id)
        return {
            'state': 'live_connected',
            'run_id': run_id,
            'application_trace_id': received.strip(),
            'transport': 'http',
        }
    _set_state('live_trace_pending', run_id=run_id, last_error=None)
    return {'state': 'live_trace_pending', 'run_id': run_id, 'application_trace_id': None, 'transport': 'http'}


def observe_narrative(*_args, **kwargs) -> dict:
    """Safe hook for Builder 1. Never raises. Never fakes live_connected."""
    run_id = kwargs.get('run_id') if isinstance(kwargs.get('run_id'), str) and kwargs.get('run_id') else str(uuid.uuid4())
    try:
        for forbidden in _FORBIDDEN_KWARGS:
            kwargs.pop(forbidden, None)
        key, project = _creds()
        if not key or not project:
            _set_state('not_configured', run_id=run_id)
            return {**prism_status(), 'run_id': run_id, 'sent': False}
        if not _STATE.get('handshake_ok'):
            _set_state('credential_configured', run_id=run_id)
        if not _egress_enabled():
            return {**prism_status(), 'run_id': run_id, 'sent': False, 'reason': 'synthetic_egress_disabled'}
        metadata = allowlisted_metadata(kwargs)
        output = _narrative_output(kwargs)
        model = metadata.get('model') or metadata.get('narrative_source') or 'deterministic-template'
        provider = metadata.get('provider') or 'deterministic-template'
        latency = kwargs.get('latency_ms') if type(kwargs.get('latency_ms')) is int else 0
        messages = [
            {
                'role': 'system',
                'content': (
                    'Observe a synthetic Money Operations narrative. '
                    'This is phrasing of validated claims, not a calculation.'
                ),
            },
            {
                'role': 'user',
                'content': (
                    f"provider={provider}; model={model}; "
                    f"numeric_validation={metadata.get('numeric_validation')}; "
                    f"citation_validation={metadata.get('citation_validation')}; "
                    f"unexplained_item_count={metadata.get('unexplained_item_count')}"
                ),
            },
        ]
        transport = os.getenv('MANDATE_PRISM_TRANSPORT', 'sdk')
        started = time.monotonic()
        if transport == 'http':
            result = _send_http(messages, output, model, latency or int((time.monotonic() - started) * 1000), run_id, metadata)
        else:
            result = _send_sdk(messages, output, model, latency or 0, run_id, metadata)
        return {**prism_status(), **result, 'sent': True}
    except (httpx.HTTPError, ValueError, TypeError, RuntimeError, ImportError):
        _set_state('error', run_id=run_id, last_error='observe_failed')
        return {**prism_status(), 'run_id': run_id, 'sent': False, 'reason': 'observe_failed'}
    except Exception:
        _set_state('error', run_id=run_id, last_error='observe_failed')
        return {**prism_status(), 'run_id': run_id, 'sent': False, 'reason': 'observe_failed'}


def compose_and_observe(package: dict, **observe_kwargs) -> dict:
    """Phrase claims, then observe the narrative boundary. Arithmetic is untouched."""
    started = time.monotonic()
    narrative = compose(package)
    claims = list(package.get('claims') or [])
    text = narrative.get('text') or narrative.get('body') or ''
    cited = list(narrative.get('cited_claim_ids') or [])
    numeric = 'pass'
    citation = 'pass'
    try:
        validate_narrative(text, claims, cited)
    except NarrativeError as exc:
        numeric = 'reject' if exc.code == 'uncited_number' else 'pass'
        citation = 'reject' if exc.code in ('unknown_claim_ids', 'uncited_entity') else numeric
        if exc.code == 'uncited_number':
            citation = 'pass'
    unexplained = sum(1 for claim in claims if str(claim.get('status', '')).lower() == 'unexplained')
    observe_narrative(
        analysis_id=observe_kwargs.get('analysis_id') or package.get('analysis_id'),
        run_id=observe_kwargs.get('run_id'),
        prior_period=(package.get('periods') or {}).get('prior') or package.get('prior_period'),
        current_period=(package.get('periods') or {}).get('current') or package.get('current_period'),
        calculation_digest=package.get('calculation_digest') or observe_kwargs.get('calculation_digest'),
        structured_claim_ids=cited,
        retrieved_context_ids=observe_kwargs.get('retrieved_context_ids') or [],
        prompt_version=observe_kwargs.get('prompt_version') or TEMPLATE_VERSION,
        template_version=TEMPLATE_VERSION,
        model=narrative.get('mode') or 'deterministic-template',
        provider=narrative.get('narrative_source') or 'deterministic-template',
        narrative_source=narrative.get('narrative_source') or 'deterministic_template',
        reconciliation_status=observe_kwargs.get('reconciliation_status'),
        unexplained_item_count=unexplained,
        numeric_validation=numeric,
        citation_validation=citation,
        fallback=narrative.get('narrative_source') == 'deterministic_template',
        error_state=narrative.get('model_error'),
        latency_ms=int((time.monotonic() - started) * 1000),
        token_usage=observe_kwargs.get('token_usage'),
        text=text,
        headline=narrative.get('headline'),
    )
    narrative = dict(narrative)
    narrative['prism'] = prism_status()
    return narrative
