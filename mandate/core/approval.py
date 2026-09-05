"""Exact, expiring, one-use approval grants protected by HMAC integrity."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Final, cast

from .contract import Disposition, EvaluatedDecision


class ApprovalValidationError(ValueError):
    """Raised when an approval cannot be created, validated, or consumed."""


class ApprovalStatus(str, Enum):
    """Stable reasons an approval is valid or cannot authorize an action."""

    VALID = "VALID"
    INTEGRITY_INVALID = "INTEGRITY_INVALID"
    ALREADY_USED = "ALREADY_USED"
    EXPIRED = "EXPIRED"
    NOT_YET_VALID = "NOT_YET_VALID"
    CANDIDATE_MISMATCH = "CANDIDATE_MISMATCH"
    CASE_MISMATCH = "CASE_MISMATCH"
    EVIDENCE_MISMATCH = "EVIDENCE_MISMATCH"
    STATE_MISMATCH = "STATE_MISMATCH"
    DECISION_MISMATCH = "DECISION_MISMATCH"
    AUTHORITY_MISMATCH = "AUTHORITY_MISMATCH"
    CONSEQUENCE_MISMATCH = "CONSEQUENCE_MISMATCH"


_CONSEQUENCE_CLASSES: Final[frozenset[str]] = frozenset({"C0", "C1", "C2", "C3", "C4"})
_MINIMUM_HMAC_KEY_BYTES: Final[int] = 32
_MAXIMUM_HMAC_KEY_BYTES: Final[int] = 4_096
_MAX_TEXT_BYTES: Final[int] = 4_096
_HMAC_DOMAIN: Final[bytes] = b"resolve:approval:v1\x00"
_APPROVAL_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "candidate_fingerprint",
        "case_fingerprint",
        "evidence_fingerprint",
        "state_fingerprint",
        "decision_fingerprint",
        "approver",
        "authority",
        "consequence_class",
        "issued_at",
        "expires_at",
        "nonce",
        "used",
        "integrity",
    }
)


def _validate_sha256(value: object, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ApprovalValidationError(f"{field} must be a SHA-256 hex digest")


def _validate_nonempty_string(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ApprovalValidationError(f"{field} must be a non-empty string")
    if len(value.encode("utf-8")) > _MAX_TEXT_BYTES:
        raise ApprovalValidationError(
            f"{field} must not exceed {_MAX_TEXT_BYTES:,} bytes"
        )


def _validate_datetime(value: object, field: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ApprovalValidationError(f"{field} must be timezone-aware")


def _validate_secret_key(secret_key: object) -> None:
    if not isinstance(secret_key, bytes) or not (
        _MINIMUM_HMAC_KEY_BYTES <= len(secret_key) <= _MAXIMUM_HMAC_KEY_BYTES
    ):
        raise ApprovalValidationError(
            "secret_key must be bytes of at least 32 bytes and at most 4,096 bytes"
        )


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class ApprovalGrant:
    """A signed grant bound to one exact decision context and action."""

    candidate_fingerprint: str
    case_fingerprint: str
    evidence_fingerprint: str
    state_fingerprint: str
    decision_fingerprint: str
    approver: str
    authority: str
    consequence_class: str
    issued_at: datetime
    expires_at: datetime
    nonce: str
    used: bool
    integrity: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a Mongo/API-safe integration representation."""

        return {
            "candidate_fingerprint": self.candidate_fingerprint,
            "case_fingerprint": self.case_fingerprint,
            "evidence_fingerprint": self.evidence_fingerprint,
            "state_fingerprint": self.state_fingerprint,
            "decision_fingerprint": self.decision_fingerprint,
            "approver": self.approver,
            "authority": self.authority,
            "consequence_class": self.consequence_class,
            "issued_at": _utc_text(self.issued_at),
            "expires_at": _utc_text(self.expires_at),
            "nonce": self.nonce,
            "used": self.used,
            "integrity": self.integrity,
        }


@dataclass(frozen=True, slots=True)
class ApprovalValidation:
    """A deterministic validation result suitable for journal recording."""

    valid: bool
    status: ApprovalStatus
    reason_code: str | None


def _signed_payload(grant: ApprovalGrant) -> dict[str, Any]:
    return {key: value for key, value in grant.to_dict().items() if key != "integrity"}


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _integrity_for(grant: ApprovalGrant, secret_key: bytes) -> str:
    payload = _HMAC_DOMAIN + _canonical_json(_signed_payload(grant)).encode("utf-8")
    return hmac.new(secret_key, payload, hashlib.sha256).hexdigest()


def _invalid(status: ApprovalStatus) -> ApprovalValidation:
    return ApprovalValidation(valid=False, status=status, reason_code=status.value)


def _parse_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ApprovalValidationError(f"{field} must be an ISO-8601 string")
    if len(value) > 128:
        raise ApprovalValidationError(f"{field} timestamp is too long")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ApprovalValidationError(
            f"{field} must be a valid ISO-8601 timestamp"
        ) from error
    _validate_datetime(parsed, field)
    return parsed


def _validate_grant_shape(grant: ApprovalGrant) -> None:
    _validate_sha256(grant.candidate_fingerprint, "candidate_fingerprint")
    _validate_sha256(grant.case_fingerprint, "case_fingerprint")
    _validate_sha256(grant.evidence_fingerprint, "evidence_fingerprint")
    _validate_sha256(grant.state_fingerprint, "state_fingerprint")
    _validate_sha256(grant.decision_fingerprint, "decision_fingerprint")
    _validate_nonempty_string(grant.approver, "approver")
    _validate_nonempty_string(grant.authority, "authority")
    if grant.consequence_class not in _CONSEQUENCE_CLASSES:
        raise ApprovalValidationError("consequence_class must be valid")
    _validate_datetime(grant.issued_at, "issued_at")
    _validate_datetime(grant.expires_at, "expires_at")
    if grant.expires_at <= grant.issued_at:
        raise ApprovalValidationError("expires_at must be later than issued_at")
    _validate_nonempty_string(grant.nonce, "nonce")
    if type(grant.used) is not bool:
        raise ApprovalValidationError("used must be a boolean")
    _validate_sha256(grant.integrity, "integrity")


def approval_from_dict(record: Mapping[str, Any]) -> ApprovalGrant:
    """Strictly restore an approval received from persistence or an API."""

    if not isinstance(record, Mapping):
        raise ApprovalValidationError("approval record must be a mapping")
    if any(not isinstance(key, str) for key in record):
        raise ApprovalValidationError("approval record keys must be strings")
    actual_fields = set(record)
    if actual_fields != _APPROVAL_FIELDS:
        missing = sorted(_APPROVAL_FIELDS - actual_fields)
        unknown = sorted(actual_fields - _APPROVAL_FIELDS)
        raise ApprovalValidationError(
            f"approval record schema mismatch; missing={missing}, unknown={unknown}"
        )

    grant = ApprovalGrant(
        candidate_fingerprint=cast(str, record["candidate_fingerprint"]),
        case_fingerprint=cast(str, record["case_fingerprint"]),
        evidence_fingerprint=cast(str, record["evidence_fingerprint"]),
        state_fingerprint=cast(str, record["state_fingerprint"]),
        decision_fingerprint=cast(str, record["decision_fingerprint"]),
        approver=cast(str, record["approver"]),
        authority=cast(str, record["authority"]),
        consequence_class=cast(str, record["consequence_class"]),
        issued_at=_parse_datetime(record["issued_at"], "issued_at"),
        expires_at=_parse_datetime(record["expires_at"], "expires_at"),
        nonce=cast(str, record["nonce"]),
        used=cast(bool, record["used"]),
        integrity=cast(str, record["integrity"]),
    )
    _validate_grant_shape(grant)
    return grant


def create_approval(
    *,
    candidate_fingerprint: str,
    case_fingerprint: str,
    evidence_fingerprint: str,
    state_fingerprint: str,
    decision_fingerprint: str,
    approver: str,
    authority: str,
    consequence_class: str,
    issued_at: datetime,
    expires_at: datetime,
    secret_key: bytes,
    nonce: str | None = None,
) -> ApprovalGrant:
    """Create an HMAC-protected one-time grant for an exact action context."""

    _validate_sha256(candidate_fingerprint, "candidate_fingerprint")
    _validate_sha256(case_fingerprint, "case_fingerprint")
    _validate_sha256(evidence_fingerprint, "evidence_fingerprint")
    _validate_sha256(state_fingerprint, "state_fingerprint")
    _validate_sha256(decision_fingerprint, "decision_fingerprint")
    _validate_nonempty_string(approver, "approver")
    _validate_nonempty_string(authority, "authority")
    if consequence_class not in _CONSEQUENCE_CLASSES:
        raise ApprovalValidationError(
            f"consequence_class must be one of {sorted(_CONSEQUENCE_CLASSES)}"
        )
    _validate_datetime(issued_at, "issued_at")
    _validate_datetime(expires_at, "expires_at")
    if expires_at <= issued_at:
        raise ApprovalValidationError("expires_at must be later than issued_at")
    _validate_secret_key(secret_key)

    actual_nonce = nonce if nonce is not None else secrets.token_urlsafe(24)
    _validate_nonempty_string(actual_nonce, "nonce")
    unsigned = ApprovalGrant(
        candidate_fingerprint=candidate_fingerprint,
        case_fingerprint=case_fingerprint,
        evidence_fingerprint=evidence_fingerprint,
        state_fingerprint=state_fingerprint,
        decision_fingerprint=decision_fingerprint,
        approver=approver.strip(),
        authority=authority.strip(),
        consequence_class=consequence_class,
        issued_at=issued_at,
        expires_at=expires_at,
        nonce=actual_nonce.strip(),
        used=False,
        integrity="",
    )
    return replace(unsigned, integrity=_integrity_for(unsigned, secret_key))


def create_approval_for_decision(
    decision: EvaluatedDecision,
    *,
    approver: str,
    issued_at: datetime,
    expires_at: datetime,
    secret_key: bytes,
    nonce: str | None = None,
) -> ApprovalGrant:
    """Create approval only from an exact evaluated WAITING_HUMAN envelope."""

    if not isinstance(decision, EvaluatedDecision) or not getattr(
        decision, "_validated", False
    ):
        raise ApprovalValidationError("decision must be produced by evaluate_decision")
    if decision.result.disposition is not Disposition.WAITING_HUMAN:
        raise ApprovalValidationError("decision is not waiting for human approval")
    if decision.required_authority is None or decision.consequence_class is None:
        raise ApprovalValidationError("decision must contain authority and consequence")
    return create_approval(
        candidate_fingerprint=decision.candidate_fingerprint,
        case_fingerprint=decision.case_fingerprint,
        evidence_fingerprint=decision.evidence_fingerprint,
        state_fingerprint=decision.state_fingerprint,
        decision_fingerprint=decision.decision_fingerprint,
        approver=approver,
        authority=decision.required_authority,
        consequence_class=decision.consequence_class,
        issued_at=issued_at,
        expires_at=expires_at,
        secret_key=secret_key,
        nonce=nonce,
    )


def validate_approval(
    grant: ApprovalGrant,
    *,
    expected_candidate_fingerprint: str,
    expected_case_fingerprint: str,
    expected_evidence_fingerprint: str,
    expected_state_fingerprint: str,
    expected_decision_fingerprint: str,
    expected_authority: str,
    expected_consequence_class: str,
    now: datetime,
    secret_key: bytes,
) -> ApprovalValidation:
    """Validate integrity, lifetime, one-use status, and every bound field."""

    if not isinstance(grant, ApprovalGrant):
        raise ApprovalValidationError("grant must be an ApprovalGrant")
    _validate_grant_shape(grant)
    _validate_datetime(now, "now")
    _validate_secret_key(secret_key)
    _validate_sha256(expected_candidate_fingerprint, "expected_candidate_fingerprint")
    _validate_sha256(expected_case_fingerprint, "expected_case_fingerprint")
    _validate_sha256(expected_evidence_fingerprint, "expected_evidence_fingerprint")
    _validate_sha256(expected_state_fingerprint, "expected_state_fingerprint")
    _validate_sha256(expected_decision_fingerprint, "expected_decision_fingerprint")
    _validate_nonempty_string(expected_authority, "expected_authority")
    if expected_consequence_class not in _CONSEQUENCE_CLASSES:
        raise ApprovalValidationError(
            "expected_consequence_class must be a valid consequence class"
        )

    expected_integrity = _integrity_for(grant, secret_key)
    if not hmac.compare_digest(grant.integrity, expected_integrity):
        return _invalid(ApprovalStatus.INTEGRITY_INVALID)
    if grant.used:
        return _invalid(ApprovalStatus.ALREADY_USED)
    if now < grant.issued_at:
        return _invalid(ApprovalStatus.NOT_YET_VALID)
    if now >= grant.expires_at:
        return _invalid(ApprovalStatus.EXPIRED)
    if grant.candidate_fingerprint != expected_candidate_fingerprint:
        return _invalid(ApprovalStatus.CANDIDATE_MISMATCH)
    if grant.case_fingerprint != expected_case_fingerprint:
        return _invalid(ApprovalStatus.CASE_MISMATCH)
    if grant.evidence_fingerprint != expected_evidence_fingerprint:
        return _invalid(ApprovalStatus.EVIDENCE_MISMATCH)
    if grant.state_fingerprint != expected_state_fingerprint:
        return _invalid(ApprovalStatus.STATE_MISMATCH)
    if grant.decision_fingerprint != expected_decision_fingerprint:
        return _invalid(ApprovalStatus.DECISION_MISMATCH)
    if grant.authority != expected_authority:
        return _invalid(ApprovalStatus.AUTHORITY_MISMATCH)
    if grant.consequence_class != expected_consequence_class:
        return _invalid(ApprovalStatus.CONSEQUENCE_MISMATCH)
    return ApprovalValidation(valid=True, status=ApprovalStatus.VALID, reason_code=None)


def consume_approval(
    grant: ApprovalGrant,
    *,
    expected_candidate_fingerprint: str,
    expected_case_fingerprint: str,
    expected_evidence_fingerprint: str,
    expected_state_fingerprint: str,
    expected_decision_fingerprint: str,
    expected_authority: str,
    expected_consequence_class: str,
    now: datetime,
    secret_key: bytes,
) -> ApprovalGrant:
    """Return a signed used copy after validation.

    This pure helper cannot atomically consume every stale copy.  The commit
    admission layer must compare-and-set the approval nonce/fingerprint and use
    an idempotency key before producing an external effect.
    """

    validation = validate_approval(
        grant,
        expected_candidate_fingerprint=expected_candidate_fingerprint,
        expected_case_fingerprint=expected_case_fingerprint,
        expected_evidence_fingerprint=expected_evidence_fingerprint,
        expected_state_fingerprint=expected_state_fingerprint,
        expected_decision_fingerprint=expected_decision_fingerprint,
        expected_authority=expected_authority,
        expected_consequence_class=expected_consequence_class,
        now=now,
        secret_key=secret_key,
    )
    if not validation.valid:
        raise ApprovalValidationError(validation.status.value)

    used_grant = replace(grant, used=True, integrity="")
    return replace(
        used_grant,
        integrity=_integrity_for(used_grant, secret_key),
    )


def approval_fingerprint(grant: ApprovalGrant) -> str:
    """Return a stable SHA-256 identity for the complete approval artifact."""

    if not isinstance(grant, ApprovalGrant):
        raise ApprovalValidationError("grant must be an ApprovalGrant")
    return hashlib.sha256(_canonical_json(grant.to_dict()).encode("utf-8")).hexdigest()

