"""Pure tamper-evident journal construction and chain verification."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from types import MappingProxyType
from typing import Any, Final, NoReturn, cast


class JournalValidationError(ValueError):
    """Raised when unsafe journal input cannot be represented or verified."""


class JournalStatus(str, Enum):
    """Stable journal verification outcomes."""

    VALID = "VALID"
    EMPTY_CHAIN = "EMPTY_CHAIN"
    PAYLOAD_HASH_MISMATCH = "PAYLOAD_HASH_MISMATCH"
    EVENT_INTEGRITY_INVALID = "EVENT_INTEGRITY_INVALID"
    SEQUENCE_INVALID = "SEQUENCE_INVALID"
    PREV_HASH_MISMATCH = "PREV_HASH_MISMATCH"
    RUN_MISMATCH = "RUN_MISMATCH"
    CASE_MISMATCH = "CASE_MISMATCH"
    DUPLICATE_EVENT_ID = "DUPLICATE_EVENT_ID"
    TERMINAL_SEQUENCE_MISMATCH = "TERMINAL_SEQUENCE_MISMATCH"
    TERMINAL_HASH_MISMATCH = "TERMINAL_HASH_MISMATCH"


GENESIS_HASH: Final[str] = "0" * 64
_MINIMUM_HMAC_KEY_BYTES: Final[int] = 32
_MAXIMUM_HMAC_KEY_BYTES: Final[int] = 4_096
_MAX_NESTING_DEPTH: Final[int] = 32
_MAX_CANONICAL_NODES: Final[int] = 10_000
_MAX_STRING_BYTES: Final[int] = 65_536
_MAX_CHAIN_EVENTS: Final[int] = 10_000
_MAX_TEXT_BYTES: Final[int] = 4_096
_MAX_INTEGER_BITS: Final[int] = 4_096
_MAX_TOTAL_STRING_BYTES: Final[int] = 1_048_576
_HMAC_DOMAIN: Final[bytes] = b"resolve:journal:v1\x00"
_JOURNAL_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "event_id",
        "case_id",
        "run_id",
        "sequence",
        "timestamp",
        "event_type",
        "payload",
        "payload_hash",
        "prev_hash",
        "event_hash_or_mac",
    }
)


def _invalid(path: str, message: str) -> NoReturn:
    raise JournalValidationError(f"{path}: {message}")


def _validate_nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _invalid(field, "must be a non-empty string")
    if len(value.encode("utf-8")) > _MAX_TEXT_BYTES:
        _invalid(field, f"must not exceed {_MAX_TEXT_BYTES:,} bytes")
    return value.strip()


def _validate_sha256(value: object, field: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _invalid(field, "must be a SHA-256 hex digest")


def _validate_secret_key(secret_key: object) -> None:
    if not isinstance(secret_key, bytes) or not (
        _MINIMUM_HMAC_KEY_BYTES <= len(secret_key) <= _MAXIMUM_HMAC_KEY_BYTES
    ):
        _invalid(
            "secret_key", "must be bytes of at least 32 bytes and at most 4,096 bytes"
        )


def _canonicalize(
    value: object,
    path: str,
    *,
    _depth: int = 0,
    _active_containers: set[int] | None = None,
    _node_count: list[int] | None = None,
    _string_byte_count: list[int] | None = None,
) -> Any:
    if _depth > _MAX_NESTING_DEPTH:
        _invalid(path, f"exceeds maximum nesting depth {_MAX_NESTING_DEPTH}")
    active_containers = _active_containers if _active_containers is not None else set()
    node_count = _node_count if _node_count is not None else [0]
    string_byte_count = _string_byte_count if _string_byte_count is not None else [0]
    node_count[0] += 1
    if node_count[0] > _MAX_CANONICAL_NODES:
        _invalid(path, f"exceeds maximum node count {_MAX_CANONICAL_NODES:,}")

    if isinstance(value, (Mapping, list, tuple)):
        if len(value) > _MAX_CANONICAL_NODES:
            _invalid(path, f"exceeds maximum member count {_MAX_CANONICAL_NODES:,}")
        identity = id(value)
        if identity in active_containers:
            _invalid(path, "contains a cyclic reference")
        active_containers.add(identity)
        try:
            if isinstance(value, Mapping):
                if any(not isinstance(key, str) for key in value):
                    _invalid(path, "mapping keys must be strings")
                if any(len(key.encode("utf-8")) > _MAX_STRING_BYTES for key in value):
                    _invalid(path, f"mapping key exceeds {_MAX_STRING_BYTES:,} bytes")
                string_byte_count[0] += sum(len(key.encode("utf-8")) for key in value)
                if string_byte_count[0] > _MAX_TOTAL_STRING_BYTES:
                    _invalid(
                        path,
                        f"exceeds total string budget {_MAX_TOTAL_STRING_BYTES:,} bytes",
                    )
                return {
                    key: _canonicalize(
                        value[key],
                        f"{path}.{key}",
                        _depth=_depth + 1,
                        _active_containers=active_containers,
                        _node_count=node_count,
                        _string_byte_count=string_byte_count,
                    )
                    for key in sorted(value)
                }
            return [
                _canonicalize(
                    item,
                    f"{path}[{index}]",
                    _depth=_depth + 1,
                    _active_containers=active_containers,
                    _node_count=node_count,
                    _string_byte_count=string_byte_count,
                )
                for index, item in enumerate(value)
            ]
        finally:
            active_containers.remove(identity)
    if isinstance(value, str):
        string_bytes = len(value.encode("utf-8"))
        if string_bytes > _MAX_STRING_BYTES:
            _invalid(path, f"string exceeds {_MAX_STRING_BYTES:,} bytes")
        string_byte_count[0] += string_bytes
        if string_byte_count[0] > _MAX_TOTAL_STRING_BYTES:
            _invalid(
                path,
                f"exceeds total string budget {_MAX_TOTAL_STRING_BYTES:,} bytes",
            )
        return value
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value.bit_length() > _MAX_INTEGER_BITS:
            _invalid(path, f"integer exceeds {_MAX_INTEGER_BITS:,} bits")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            _invalid(path, "must be a finite number")
        return value
    _invalid(path, f"contains unsupported value type {type(value).__name__}")


def _freeze(value: object) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _utc_text(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _validate_datetime(value: object, field: str) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        _invalid(field, "must be timezone-aware")
    return value


def _parse_datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        _invalid(field, "must be an ISO-8601 string")
    if len(value) > 128:
        _invalid(field, "timestamp is too long")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise JournalValidationError(
            f"{field}: must be a valid ISO-8601 timestamp"
        ) from error
    return _validate_datetime(parsed, field)


@dataclass(frozen=True, slots=True)
class JournalEvent:
    """One immutable canonical event linked to the preceding event."""

    event_id: str
    case_id: str
    run_id: str
    sequence: int
    timestamp: datetime
    event_type: str
    payload: Mapping[str, Any]
    payload_hash: str
    prev_hash: str
    event_hash_or_mac: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the frozen Mongo/API event interface."""

        return {
            "event_id": self.event_id,
            "case_id": self.case_id,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "timestamp": _utc_text(self.timestamp),
            "event_type": self.event_type,
            "payload": _thaw(self.payload),
            "payload_hash": self.payload_hash,
            "prev_hash": self.prev_hash,
            "event_hash_or_mac": self.event_hash_or_mac,
        }


@dataclass(frozen=True, slots=True)
class JournalVerification:
    """Deterministic result of verifying one event or an entire chain."""

    valid: bool
    status: JournalStatus
    failed_sequence: int | None


def journal_event_from_dict(record: Mapping[str, Any]) -> JournalEvent:
    """Strictly restore and freeze an event read from persistence or an API."""

    if not isinstance(record, Mapping):
        _invalid("event record", "must be a mapping")
    if any(not isinstance(key, str) for key in record):
        _invalid("event record", "keys must be strings")
    actual_fields = set(record)
    if actual_fields != _JOURNAL_FIELDS:
        missing = sorted(_JOURNAL_FIELDS - actual_fields)
        unknown = sorted(actual_fields - _JOURNAL_FIELDS)
        _invalid(
            "event record",
            f"schema mismatch; missing={missing}, unknown={unknown}",
        )

    event_id = _validate_nonempty_string(record["event_id"], "event_id")
    case_id = _validate_nonempty_string(record["case_id"], "case_id")
    run_id = _validate_nonempty_string(record["run_id"], "run_id")
    sequence = record["sequence"]
    if type(sequence) is not int or sequence < 1:
        _invalid("sequence", "must be an integer greater than or equal to 1")
    timestamp = _parse_datetime(record["timestamp"], "timestamp")
    event_type = _validate_nonempty_string(record["event_type"], "event_type")
    raw_payload = record["payload"]
    if not isinstance(raw_payload, Mapping):
        _invalid("payload", "must be a mapping")
    normalized_payload = cast(dict[str, Any], _canonicalize(raw_payload, "payload"))
    _validate_sha256(record["payload_hash"], "payload_hash")
    _validate_sha256(record["prev_hash"], "prev_hash")
    _validate_sha256(record["event_hash_or_mac"], "event_hash_or_mac")

    return JournalEvent(
        event_id=event_id,
        case_id=case_id,
        run_id=run_id,
        sequence=sequence,
        timestamp=timestamp,
        event_type=event_type,
        payload=cast(Mapping[str, Any], _freeze(normalized_payload)),
        payload_hash=cast(str, record["payload_hash"]),
        prev_hash=cast(str, record["prev_hash"]),
        event_hash_or_mac=cast(str, record["event_hash_or_mac"]),
    )


def _event_integrity_payload(event: JournalEvent) -> dict[str, Any]:
    return {
        key: value
        for key, value in event.to_dict().items()
        if key != "event_hash_or_mac"
    }


def _integrity_for(event: JournalEvent, secret_key: bytes) -> str:
    message = _HMAC_DOMAIN + _canonical_json(_event_integrity_payload(event)).encode(
        "utf-8"
    )
    return hmac.new(secret_key, message, hashlib.sha256).hexdigest()


def _result(status: JournalStatus, sequence: int | None = None) -> JournalVerification:
    return JournalVerification(
        valid=status is JournalStatus.VALID,
        status=status,
        failed_sequence=sequence,
    )


def create_event(
    *,
    event_id: str,
    case_id: str,
    run_id: str,
    sequence: int,
    timestamp: datetime,
    event_type: str,
    payload: Mapping[str, Any],
    prev_hash: str,
    secret_key: bytes,
) -> JournalEvent:
    """Validate, canonicalize, freeze, hash, and HMAC one journal event."""

    normalized_event_id = _validate_nonempty_string(event_id, "event_id")
    normalized_case_id = _validate_nonempty_string(case_id, "case_id")
    normalized_run_id = _validate_nonempty_string(run_id, "run_id")
    if type(sequence) is not int or sequence < 1:
        _invalid("sequence", "must be an integer greater than or equal to 1")
    _validate_datetime(timestamp, "timestamp")
    normalized_event_type = _validate_nonempty_string(event_type, "event_type")
    if not isinstance(payload, Mapping):
        _invalid("payload", "must be a mapping")
    _validate_sha256(prev_hash, "prev_hash")
    _validate_secret_key(secret_key)

    normalized_payload = cast(dict[str, Any], _canonicalize(payload, "payload"))
    frozen_payload = cast(Mapping[str, Any], _freeze(normalized_payload))
    payload_hash = _sha256(normalized_payload)
    unsigned = JournalEvent(
        event_id=normalized_event_id,
        case_id=normalized_case_id,
        run_id=normalized_run_id,
        sequence=sequence,
        timestamp=timestamp,
        event_type=normalized_event_type,
        payload=frozen_payload,
        payload_hash=payload_hash,
        prev_hash=prev_hash,
        event_hash_or_mac="",
    )
    return JournalEvent(
        event_id=unsigned.event_id,
        case_id=unsigned.case_id,
        run_id=unsigned.run_id,
        sequence=unsigned.sequence,
        timestamp=unsigned.timestamp,
        event_type=unsigned.event_type,
        payload=unsigned.payload,
        payload_hash=unsigned.payload_hash,
        prev_hash=unsigned.prev_hash,
        event_hash_or_mac=_integrity_for(unsigned, secret_key),
    )


def verify_event(event: JournalEvent, *, secret_key: bytes) -> JournalVerification:
    """Verify one event's payload hash and HMAC without trusting persistence."""

    if not isinstance(event, JournalEvent):
        raise JournalValidationError("event must be a JournalEvent")
    _validate_secret_key(secret_key)

    normalized_payload = _canonicalize(_thaw(event.payload), "payload")
    if not hmac.compare_digest(event.payload_hash, _sha256(normalized_payload)):
        return _result(JournalStatus.PAYLOAD_HASH_MISMATCH, event.sequence)
    if not hmac.compare_digest(
        event.event_hash_or_mac, _integrity_for(event, secret_key)
    ):
        return _result(JournalStatus.EVENT_INTEGRITY_INVALID, event.sequence)
    return _result(JournalStatus.VALID)


def verify_chain(
    events: Sequence[JournalEvent],
    *,
    secret_key: bytes,
    expected_final_sequence: int | None = None,
    expected_final_hash: str | None = None,
) -> JournalVerification:
    """Verify one run and, when anchored, prove the supplied tail is complete.

    Internal linkage alone proves integrity only for the supplied prefix.  A
    complete replay must also provide the separately retained final sequence
    and final event HMAC.
    """

    _validate_secret_key(secret_key)
    if len(events) > _MAX_CHAIN_EVENTS:
        _invalid("events", f"exceeds maximum chain length {_MAX_CHAIN_EVENTS:,}")
    if (expected_final_sequence is None) != (expected_final_hash is None):
        _invalid(
            "replay anchor",
            "expected_final_sequence and expected_final_hash must be provided together",
        )
    if expected_final_sequence is not None:
        if type(expected_final_sequence) is not int or expected_final_sequence < 1:
            _invalid("expected_final_sequence", "must be a positive integer")
        _validate_sha256(expected_final_hash, "expected_final_hash")
    if not events:
        return _result(JournalStatus.EMPTY_CHAIN)
    if any(not isinstance(event, JournalEvent) for event in events):
        raise JournalValidationError("events must contain only JournalEvent values")

    first = events[0]
    expected_run_id = first.run_id
    expected_case_id = first.case_id
    expected_prev_hash = GENESIS_HASH
    seen_event_ids: set[str] = set()

    for expected_sequence, event in enumerate(events, start=1):
        event_verification = verify_event(event, secret_key=secret_key)
        if not event_verification.valid:
            return event_verification
        if event.sequence != expected_sequence:
            return _result(JournalStatus.SEQUENCE_INVALID, event.sequence)
        if event.run_id != expected_run_id:
            return _result(JournalStatus.RUN_MISMATCH, event.sequence)
        if event.case_id != expected_case_id:
            return _result(JournalStatus.CASE_MISMATCH, event.sequence)
        if event.event_id in seen_event_ids:
            return _result(JournalStatus.DUPLICATE_EVENT_ID, event.sequence)
        if event.prev_hash != expected_prev_hash:
            return _result(JournalStatus.PREV_HASH_MISMATCH, event.sequence)

        seen_event_ids.add(event.event_id)
        expected_prev_hash = event.event_hash_or_mac

    if expected_final_sequence is not None and first.sequence + len(events) - 1 != (
        expected_final_sequence
    ):
        return _result(JournalStatus.TERMINAL_SEQUENCE_MISMATCH, events[-1].sequence)
    if expected_final_hash is not None and not hmac.compare_digest(
        events[-1].event_hash_or_mac, expected_final_hash
    ):
        return _result(JournalStatus.TERMINAL_HASH_MISMATCH, events[-1].sequence)

    return _result(JournalStatus.VALID)

