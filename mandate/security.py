"""Deterministic synthetic security questionnaire analyst; no live AI or certification.

Sources are local demonstration records, not externally verified company facts. Hashes
prove stored-content consistency only. Parent service authenticates actors and persists
profiles/history using its own transaction/audit boundary.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
import re


def _now():
    return datetime.now(UTC).isoformat()


def _hash(source):
    return hashlib.sha256(json.dumps({k: v for k, v in source.items() if k != 'sha256'},
                                    sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def _source(sid, title, kind, text, origin=None, parents=(), updated='2026-09-04T16:00:00+00:00'):
    result = dict(id=sid, title=title, kind=kind, text=text, origin_id=origin or sid,
                  parent_ids=list(parents), updated_at=updated)
    result['sha256'] = _hash(result)
    return result


_BASE = [
    _source('mfa-policy-v1', 'Access policy v1', 'policy', 'MFA is mandatory for Google Workspace and GitHub. Policy requirement; this document does not attest actual enrollment.'),
    _source('mfa-exception-v1', 'Contractor access message', 'internal_message', 'An active contractor exception may leave one Google Workspace account without MFA. Verify current account state.', updated='2026-09-05T08:00:00+00:00'),
    _source('rds-snapshot-v1', 'Primary database infrastructure snapshot', 'infrastructure', 'Primary customer database: AWS RDS in us-east-1. StorageEncrypted=true. Scope excludes replicas, exports, logs, backups and employee devices.'),
    _source('ci-policy-v1', 'Container CI pipeline configuration', 'configuration', 'Container image vulnerability scan is configured in CI. No evidence here of latest successful run, web application scans or penetration tests.'),
    _source('prod-access-v1', 'Production access roster', 'employee_information', 'Two synthetic named production administrators: Maya Chen and Leo Patel. This roster does not prove no additional effective permissions exist.'),
    _source('offboarding-v1', 'Employee offboarding procedure', 'policy', 'On departure, the People owner requests account disablement and the IT owner removes access and records completion. A documented process; no completed offboarding samples supplied.'),
]
_RESOLUTION = _source('mfa-iam-v2', 'New synthetic IAM snapshot v2', 'infrastructure',
    'Synthetic current IAM check: prior contractor exception disabled; all currently listed Google Workspace and GitHub accounts have MFA enabled. Scope: these two services at snapshot time only.',
    updated='2026-09-05T15:00:00+00:00')
_KNOWN = {s['id']: s for s in _BASE + [_RESOLUTION]}
_QS = [
    ('mfa', 'Is MFA enabled?', 'IT owner', 'high'),
    ('storage', 'Where is customer data stored?', 'Engineering owner', 'high'),
    ('encryption', 'Do you encrypt data at rest?', 'Engineering owner', 'high'),
    ('backups', 'How often are backups performed, and are they automated?', 'Engineering owner', 'high'),
    ('scans', 'Is vulnerability scanning configured in CI?', 'Engineering owner', 'medium'),
    ('production_access', 'Who has access to production?', 'IT owner', 'high'),
    ('offboarding', 'Do you have an employee offboarding process?', 'People owner', 'medium'),
    ('background_checks', 'Do you conduct employee background checks?', 'People owner', 'medium'),
]
_RELEVANT = {'mfa': ['mfa-policy-v1', 'mfa-exception-v1', 'mfa-iam-v2'],
             'storage': ['rds-snapshot-v1'], 'encryption': ['rds-snapshot-v1'],
             'backups': [], 'scans': ['ci-policy-v1'], 'production_access': ['prod-access-v1'],
             'offboarding': ['offboarding-v1'], 'background_checks': []}


def _valid_sources(profile):
    sources = profile.get('sources', [])
    byid = {s.get('id'): s for s in sources if isinstance(s, dict) and isinstance(s.get('id'), str)}
    duplicates = {sid for sid in byid if sum(s.get('id') == sid for s in sources if isinstance(s, dict)) > 1}
    roots, invalid = {}, set(duplicates)
    def visit(sid, path):
        if sid in path or sid not in byid or sid in invalid:
            invalid.update(path | {sid})
            return set()
        if sid in roots:
            return roots[sid]
        s = byid[sid]
        if s.get('sha256') != _hash(s) or not isinstance(s.get('parent_ids'), list) or not isinstance(s.get('origin_id'), str):
            invalid.add(sid)
            return set()
        # Known IDs support claims only as the recognized fixture version, not as arbitrary text.
        if sid in _KNOWN and s != _KNOWN[sid]:
            invalid.add(sid)
            return set()
        result = set()
        if s['parent_ids']:
            for p in s['parent_ids']:
                if not isinstance(p, str):
                    invalid.add(sid)
                    return set()
                result |= visit(p, path | {sid})
                if p in invalid:
                    invalid.add(sid)
        else:
            result.add(s['origin_id'])
        roots[sid] = result
        return result
    for sid in byid:
        visit(sid, set())
    return {sid: s for sid, s in byid.items() if sid not in invalid}, roots, sorted(invalid)


def _search(profile, qid, actor):
    valid, roots, invalid = _valid_sources(profile)
    wanted = _RELEVANT.get(qid, []) if qid else list(_KNOWN)
    # Content hashes establish integrity, not truth. Only recognized imported fixture
    # versions can support this bounded engine's fixed claims; arbitrary new text cannot.
    found = [sid for sid in wanted if sid in valid and valid[sid] == _KNOWN[sid]]
    root_set = set().union(*(roots.get(sid, set()) for sid in found)) if found else set()
    event = dict(type='retrieval', question_id=qid, actor=actor, time=_now(),
                 retrieved_ids=found, invalid_source_ids=invalid,
                 unique_origin_count=len(root_set), revision=profile['revision'])
    profile['history'].append(event)
    return found


def _question(profile, qid):
    return next(q for q in profile['questions'] if q['id'] == qid)


def _set_question(q, answer, status, source_ids, support):
    q.update(answer=answer, status=status, source_ids=source_ids, support=support)


def _refresh(profile):
    valid, _, _ = _valid_sources(profile)
    known = {sid for sid, src in valid.items() if sid in _KNOWN and src == _KNOWN[sid]}
    texts = {
        'storage': 'Primary customer database is AWS RDS in us-east-1. Other copies, exports, logs and devices are not established.',
        'encryption': 'The primary RDS snapshot reports StorageEncrypted=true. Encryption of replicas, exports, logs, backups and devices is not established.',
        'scans': 'Container image scanning is configured in CI. Successful recent execution, other scan coverage and penetration tests are not established.',
        'production_access': 'The supplied roster names two synthetic production administrators: Maya Chen and Leo Patel. Effective access completeness is not established.',
        'offboarding': 'A documented employee offboarding process assigns People and IT responsibilities. Evidence of implementation in individual departures was not supplied.',
    }
    for qid, answer in texts.items():
        ids = _RELEVANT[qid]
        q = _question(profile, qid)
        if all(s in known for s in ids):
            _set_question(q, answer, 'evidence_backed', ids, 'Supported within the stated scope of the synthetic company record; not an external certification.')
        else:
            _set_question(q, 'Unknown: required source is missing, changed or fails integrity validation.', 'unknown', [], 'An intact, recognized source version is required.')
    q = _question(profile, 'mfa')
    if 'mfa-iam-v2' in known and 'mfa-policy-v1' in known:
        _set_question(q, 'Current synthetic IAM snapshot reports MFA enabled for listed Google Workspace and GitHub accounts and the prior contractor exception disabled. Other services and future state are not established.', 'evidence_backed', ['mfa-policy-v1', 'mfa-exception-v1', 'mfa-iam-v2'] if 'mfa-exception-v1' in known else ['mfa-policy-v1', 'mfa-iam-v2'], 'Newer operational evidence resolves the earlier exception for these two services; prior conflicting evidence remains in history.')
    elif {'mfa-policy-v1', 'mfa-exception-v1'} <= known:
        _set_question(q, 'Conflict: policy requires MFA for Google Workspace and GitHub, but an internal message reports a possible active contractor exception. Current enforcement is unconfirmed.', 'conflict', ['mfa-policy-v1', 'mfa-exception-v1'], 'A policy requirement is not evidence of universal enforcement. Obtain current account state or exception resolution.')
    else:
        _set_question(q, 'Unknown: current MFA enforcement needs intact policy and operational evidence.', 'unknown', [s for s in _RELEVANT['mfa'] if s in known], 'Do not infer operational compliance from a policy alone.')


def init_profile() -> dict:
    profile = dict(revision=1, questions=[dict(id=qid, question=text, answer='Unknown / needs confirmation.',
                    status='unknown', source_ids=[], support='No relevant company evidence supplied.', owner=owner, priority=priority)
                    for qid, text, owner, priority in _QS], sources=deepcopy(_BASE), messages=[], history=[],
                    memory={'backups': {'performed': None, 'frequency': None, 'automated': None}}, pending=None)
    _search(profile, None, 'system')
    _refresh(profile)
    return profile


def _intent(text):
    """Match only when the user clearly names a control; bare 'admin' is not production access."""
    choices = [('mfa', r'\bmfa\b|multi.factor'), ('background_checks', r'background|screening'),
               ('backups', r'backup|back.up|restore'), ('encryption', r'encrypt|at rest'),
               ('storage', r'stor|region|data live|data located'), ('scans', r'vulnerab|scan|penetration'),
               ('offboarding', r'offboard|departure|leaver'), ('production_access', r'\bproduction\b|access roster')]
    return next((qid for qid, pat in choices if re.search(pat, text)), None)


def _backup_answer(profile):
    b = profile['memory']['backups']
    q = _question(profile, 'backups')
    if b['performed'] is False:
        _set_question(q, 'User reports that backups are not performed.', 'user_confirmed', [], 'Employee assertion; not independently verified.')
    elif b['performed'] is True and b['frequency'] and b['automated'] is not None:
        _set_question(q, f"User reports backups are performed {b['frequency']} and are {'automated' if b['automated'] else 'not automated'}.", 'user_confirmed', [], 'Employee assertion; not independently verified. Supporting configuration or restore-test evidence is still absent.')
    else:
        details = [f'{key}={value}' for key, value in b.items() if value is not None]
        _set_question(q, 'Unknown / incomplete backup details' + (': ' + ', '.join(details) if details else '') + '.', 'unknown', [], 'Partial employee information is retained; completion requires performance, frequency and automation details.')


def _backup_prompt(profile):
    b = profile['memory']['backups']
    if b['performed'] is None:
        field, reply = 'performed', 'I found no backup practice evidence in the supplied records. Do you perform backups?'
    elif b['performed'] and not b['frequency']:
        field, reply = 'frequency', 'How frequently are backups performed? For example, daily or weekly.'
    elif b['performed'] and b['automated'] is None:
        field, reply = 'automated', 'Are those backups automated?'
    else:
        profile['pending'] = None
        return _question(profile, 'backups')['answer']
    profile['pending'] = {'question_id': 'backups', 'field': field}
    return reply


def respond(profile: dict, message: str, actor: str) -> tuple[dict, str]:
    p = deepcopy(profile)
    if not isinstance(message, str) or not message.strip() or len(message) > 4000:
        raise ValueError('Message must contain 1–4000 characters')
    if not isinstance(actor, str) or not actor.strip() or len(actor) > 100:
        raise ValueError('Authenticated actor required')
    p['revision'] += 1
    text = message.strip().lower()
    pending = p.get('pending') if isinstance(p.get('pending'), dict) else None
    named = _intent(text)
    # Prefer the open follow-up unless the user clearly names another control.
    qid = named or (pending['question_id'] if pending else None)
    found = _search(p, qid, actor)
    _refresh(p)
    p['messages'].append(dict(role='user', content=message.strip(), source_ids=[], status='user_input', time=_now(), actor=actor))
    before = deepcopy(p['memory'])
    vague = bool(re.search(
        r'ignore (all |the )?(instructions|guardrails|rules)|everything (is )?(secure|fine|compliant)'
        r'|just (say|answer) yes|make.*evidence|forget (the |about the )?conflict', text))
    if vague:
        reply = 'That statement does not establish a specific security practice or resolve conflicting evidence. Please name the control and its actual scope; existing unknowns and conflicts remain.'
    elif qid == 'backups' and (text.endswith('?') or (
            re.match(r'^(do|does|are|is|how|what|can|could|should)\b', text)
            and not re.match(r'^(do|does) not\b', text))):
        reply = _backup_prompt(p)
    elif qid == 'backups':
        b = p['memory']['backups']
        field = pending.get('field') if pending and pending['question_id'] == 'backups' else None
        yes = text in ('yes', 'yes.', 'y', 'correct', 'true')
        no = text in ('no', 'no.', 'n', 'false')
        freq = re.search(r'\b(daily|weekly|hourly|monthly|nightly)\b', text)
        if freq:
            b['performed'], b['frequency'] = True, ('daily' if freq.group() == 'nightly' else freq.group())
        if re.search(r'\b(no backups|do not (perform |do )?backups|don.t (perform |do )?backups)\b', text):
            b.update(performed=False, frequency=None, automated=None)
        elif re.search(r'\b(not automated|manual|manually)\b', text):
            b.update(performed=True, automated=False)
        elif re.search(r'\b(automated|automatically)\b', text) and not text.endswith('?'):
            b.update(performed=True, automated=True)
        elif field in ('performed', 'automated') and (yes or no):
            b[field] = yes
            if field == 'performed' and no:
                b.update(frequency=None, automated=None)
        elif field == 'frequency' and re.search(r'\bevery (\d{1,3}) (hours?|days?|weeks?)\b', text):
            b['frequency'] = re.search(r'\bevery (\d{1,3}) (hours?|days?|weeks?)\b', text).group()
        _backup_answer(p)
        reply = _backup_prompt(p)
    elif qid == 'background_checks':
        q = _question(p, qid)
        if pending and pending['question_id'] == qid and len(text) >= 12 and text not in ('yes', 'no') and not text.endswith('?'):
            _set_question(q, 'User reports: ' + message.strip(), 'user_confirmed', [], 'Employee assertion, not independently verified; recorded with actor and history.')
            p['pending'] = None
            reply = q['answer']
        elif q['status'] == 'user_confirmed':
            reply = q['answer']
        else:
            p['pending'] = {'question_id': qid, 'field': 'scope'}
            reply = 'I found no background-check evidence. Are checks performed; if so, for which people and at what stage?'
    elif qid:
        q = _question(p, qid)
        reply = q['answer']
        if q['status'] == 'conflict':
            reply += ' Can you provide current account-level evidence that resolves the contractor exception?'
            p['pending'] = {'question_id': qid, 'field': 'current_evidence'}
        else:
            p['pending'] = None
    else:
        p['pending'] = None
        reply = 'Which security control should I investigate: MFA, storage, encryption, backups, scans, production access, offboarding, or background checks? I searched the supplied records before asking.'
    if before != p['memory']:
        p['history'].append(dict(type='memory_updated', actor=actor, time=_now(), revision=p['revision'],
                                 before=before, after=deepcopy(p['memory']), message=message.strip()))
    q = _question(p, qid) if qid else None
    p['history'].append(dict(type='response', actor=actor, question_id=qid, time=_now(), revision=p['revision'],
                             retrieved_ids=found, status=q['status'] if q else 'unknown'))
    p['messages'].append(dict(role='assistant', content=reply, source_ids=found,
                             status=q['status'] if q else 'unknown', time=_now()))
    return p, reply


def add_resolution(profile: dict, actor: str) -> dict:
    if not isinstance(actor, str) or not actor.strip() or len(actor) > 100:
        raise ValueError('Authenticated actor required')
    p = deepcopy(profile)
    p['revision'] += 1
    before = deepcopy(_question(p, 'mfa'))
    if not any(s['id'] == _RESOLUTION['id'] for s in p['sources']):
        p['sources'].append(deepcopy(_RESOLUTION))
    p['history'].append(dict(type='synthetic_source_added', actor=actor, time=_now(), revision=p['revision'],
                             source_id=_RESOLUTION['id'], source_sha256=_RESOLUTION['sha256'], prior_question=before))
    ids = _search(p, 'mfa', actor)
    _refresh(p)
    p['pending'] = None
    p['messages'].append(dict(role='assistant', content='New synthetic IAM fixture added. ' + _question(p, 'mfa')['answer'],
                              source_ids=ids, status=_question(p, 'mfa')['status'], time=_now()))
    return p


def export_questionnaire(profile: dict) -> dict:
    p = deepcopy(profile)
    _search(p, None, 'export')
    _refresh(p)
    _backup_answer(p)
    valid, roots, invalid = _valid_sources(p)
    return dict(schema_version='1.0', synthetic=True, engine='deterministic-local', revision=p['revision'],
                generated_at=_now(), questions=p['questions'], sources=p['sources'], history=p['history'],
                verification=dict(invalid_source_ids=invalid, intact_source_count=len(valid),
                                  unique_origin_count=len(set().union(*(roots.get(k, set()) for k in valid))) if valid else 0,
                                  limitation='Hashes check consistency, not real-world truth. Evidence-backed answers are scoped to synthetic imported records; employee claims remain user_confirmed.'),
                statuses={s: sum(q['status'] == s for q in p['questions']) for s in ('evidence_backed', 'user_confirmed', 'unknown', 'conflict')})
