"""Optional ElevenLabs briefing for a controller-approved Money Operations memo.

Voice cannot approve, edit, submit, or distribute. Audio is produced only from
the approved narrative text plus digest. Transaction-level rows are never sent.
"""
from __future__ import annotations

import os
import threading
from urllib.parse import urlsplit

import httpx

from .money_operations_service import MoneyOpsError, _digest

SYNTHETIC_DISCLAIMER = (
    'This briefing is a synthetic demonstration scenario. '
    'It is not production financial advice and does not move funds.'
)
_CACHE_LOCK = threading.Lock()
_AUDIO_CACHE: dict[tuple[str, int, str], bytes] = {}


def reset_audio_cache() -> None:
    with _CACHE_LOCK:
        _AUDIO_CACHE.clear()


def audio_enabled() -> bool:
    return os.getenv('MONEY_OPS_AUDIO_ENABLED', 'false').strip().lower() in {'1', 'true', 'yes'}


def audio_configured() -> bool:
    return bool((os.getenv('ELEVENLABS_API_KEY') or '').strip() and (os.getenv('ELEVENLABS_VOICE_ID') or '').strip())


def audio_state() -> dict:
    enabled = audio_enabled()
    return {
        'enabled': enabled,
        'configured': audio_configured(),
        'provider': 'elevenlabs' if enabled and audio_configured() else 'none',
        'state': 'audio_unavailable' if not (enabled and audio_configured()) else 'configured_unverified',
    }


def narrative_digest(narrative: dict) -> str:
    return _digest(narrative or {})


def approved_transcript(narrative: dict, *, periods: dict | None = None) -> str:
    headline = str(narrative.get('headline') or '').strip()
    body = str(narrative.get('text') or narrative.get('body') or '').strip()
    prior = (periods or {}).get('prior') or ''
    current = (periods or {}).get('current') or ''
    window = f' Periods {prior} to {current}.' if prior and current else ''
    parts = [part for part in (headline, body) if part]
    text = ' '.join(parts) if parts else 'Approved Money Operations memo is empty.'
    if 'synthetic' not in text.lower():
        text = f'{text}{window} {SYNTHETIC_DISCLAIMER}'
    elif window and window.strip() not in text:
        text = f'{text}{window}'
    return text


def _latest_approved_review(db, analysis_id: str):
    return db.execute(
        'SELECT analysis_revision, narrative_digest, decision, actor, created_at '
        'FROM mo_reviews WHERE analysis_id=? AND decision=? ORDER BY created_at DESC',
        (analysis_id, 'approved'),
    ).fetchone()


def assert_approved_memo(row, body: dict, review) -> dict:
    """Reject if not approved, or if revision/narrative digest drifted after approval."""
    narrative = body.get('narrative') or {}
    current_digest = narrative_digest(narrative)
    if body.get('review_status') != 'approved' or review is None:
        raise MoneyOpsError(409, 'approval_required', 'Controller approval is required before a briefing', {
            'review_status': body.get('review_status') or 'draft',
        })
    expected_revision = int(review['analysis_revision']) + 1
    if int(row['revision']) != expected_revision:
        raise MoneyOpsError(409, 'stale_revision', 'Analysis revision changed since approval', {
            'approved_revision': review['analysis_revision'],
            'current_revision': row['revision'],
        })
    if review['narrative_digest'] != current_digest:
        raise MoneyOpsError(409, 'narrative_changed', 'Narrative digest changed since approval', {
            'approved_narrative_digest': review['narrative_digest'],
            'current_narrative_digest': current_digest,
        })
    return {
        'narrative': narrative,
        'narrative_digest': current_digest,
        'approved_revision': review['analysis_revision'],
        'review': {
            'decision': review['decision'],
            'actor': review['actor'],
            'created_at': review['created_at'],
            'analysis_revision': review['analysis_revision'],
            'narrative_digest': review['narrative_digest'],
        },
    }


def _briefing_payload(
    analysis_id: str,
    revision: int,
    digest: str,
    status: str,
    transcript: str,
    *,
    audio_url=None,
    provider: str = 'none',
) -> dict:
    return {
        'analysis_id': analysis_id,
        'analysis_revision': revision,
        'narrative_digest': digest,
        'status': status,
        'synthetic': True,
        'transcript': transcript,
        'audio_url': audio_url,
        'provider': provider,
    }


def _https_url(value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != 'https'
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError('An HTTPS ElevenLabs URL without credentials, query or fragment is required')
    return value


def synthesize_transcript(transcript: str, voice_id: str, api_key: str) -> bytes:
    """Send approved transcript only. Never attach transaction rows."""
    url = _https_url(f'https://api.elevenlabs.io/v1/text-to-speech/{voice_id}')
    with httpx.Client(timeout=20.0, follow_redirects=False, trust_env=False) as client:
        response = client.post(
            url,
            headers={'xi-api-key': api_key, 'Accept': 'audio/mpeg', 'Content-Type': 'application/json'},
            json={'text': transcript, 'model_id': 'eleven_monolingual_v1'},
        )
    response.raise_for_status()
    audio = response.content
    if not audio or len(audio) < 16:
        raise ValueError('Empty audio payload')
    return audio


def build_briefing(db, row, body: dict) -> dict:
    analysis_id = row['id']
    revision = int(row['revision'])
    review = _latest_approved_review(db, analysis_id)
    try:
        approved = assert_approved_memo(row, body, review)
    except MoneyOpsError as exc:
        if exc.code == 'approval_required':
            narrative = body.get('narrative') or {}
            return _briefing_payload(
                analysis_id,
                revision,
                narrative_digest(narrative),
                'approval_required',
                approved_transcript(narrative, periods=body.get('periods')),
            )
        raise
    transcript = approved_transcript(approved['narrative'], periods=body.get('periods'))
    digest = approved['narrative_digest']
    if not audio_enabled() or not audio_configured():
        return _briefing_payload(analysis_id, revision, digest, 'audio_unavailable', transcript)
    try:
        audio = synthesize_transcript(
            transcript,
            os.getenv('ELEVENLABS_VOICE_ID', '').strip(),
            os.getenv('ELEVENLABS_API_KEY', '').strip(),
        )
        cache_key = (analysis_id, revision, digest)
        with _CACHE_LOCK:
            _AUDIO_CACHE[cache_key] = audio
        return _briefing_payload(
            analysis_id,
            revision,
            digest,
            'audio_ready',
            transcript,
            audio_url=f'/api/money-operations/analyses/{analysis_id}/briefing/audio',
            provider='elevenlabs',
        )
    except (httpx.HTTPError, ValueError, TypeError, OSError):
        return _briefing_payload(analysis_id, revision, digest, 'audio_unavailable', transcript)


def cached_audio(analysis_id: str, revision: int, digest: str) -> bytes | None:
    with _CACHE_LOCK:
        return _AUDIO_CACHE.get((analysis_id, revision, digest))
