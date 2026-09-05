"""Pure validation and identity helpers for Resolve decision inputs.

This module is deliberately independent of models, databases, and runtime
state.  It turns untrusted mappings into canonical data before the permission
kernel or approval layer relies on them.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any, NoReturn, cast


class CaseValidationError(ValueError):
    """Raised when case or candidate data is unsafe to use for permission."""


_CONSEQUENCE_CLASSES = frozenset({"C0", "C1", "C2", "C3", "C4"})
_MAX_NESTING_DEPTH = 32
_MAX_CANONICAL_NODES = 10_000
_MAX_STRING_BYTES = 65_536
_MAX_INTEGER_BITS = 4_096
_MAX_TOTAL_STRING_BYTES = 1_048_576


def _invalid(path: str, message: str) -> NoReturn:
    raise CaseValidationError(f"{path}: {message}")


def _require_mapping(value: object, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _invalid(path, "must be a mapping")
    return value


def _require_nonempty_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        _invalid(path, "must be a non-empty string")
    if len(value.encode("utf-8")) > _MAX_STRING_BYTES:
        _invalid(path, f"string exceeds {_MAX_STRING_BYTES:,} bytes")
    return value.strip()


def _require_string_list(
    value: object, path: str, *, allow_empty: bool = True
) -> list[str]:
    if not isinstance(value, list):
        _invalid(path, "must be a list")
    if not allow_empty and not value:
        _invalid(path, "must not be empty")
    if len(value) > _MAX_CANONICAL_NODES:
        _invalid(path, f"exceeds maximum member count {_MAX_CANONICAL_NODES:,}")
    return [
        _require_nonempty_string(item, f"{path}[{index}]")
        for index, item in enumerate(value)
    ]


def _required(mapping: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in mapping:
        _invalid(f"{path}.{key}", "is required")
    return mapping[key]


def _canonicalize(
    value: object,
    path: str = "value",
    *,
    trim_strings: bool = True,
    _depth: int = 0,
    _active_containers: set[int] | None = None,
    _node_count: list[int] | None = None,
    _string_byte_count: list[int] | None = None,
) -> Any:
    """Return JSON-safe data with stable key order and trimmed strings.

    All supplied fields are retained.  Dropping an unfamiliar field here could
    let a policy-relevant change keep the same fingerprint, so unsupported
    runtime objects fail explicitly instead.
    """

    if _depth > _MAX_NESTING_DEPTH:
        _invalid(path, f"exceeds maximum nesting depth {_MAX_NESTING_DEPTH}")
    active_containers = _active_containers if _active_containers is not None else set()
    node_count = _node_count if _node_count is not None else [0]
    string_byte_count = _string_byte_count if _string_byte_count is not None else [0]
    node_count[0] += 1
    if node_count[0] > _MAX_CANONICAL_NODES:
        _invalid(path, f"exceeds maximum node count {_MAX_CANONICAL_NODES:,}")

    if isinstance(value, (Mapping, list)):
        if len(value) > _MAX_CANONICAL_NODES:
            _invalid(path, f"exceeds maximum member count {_MAX_CANONICAL_NODES:,}")
        identity = id(value)
        if identity in active_containers:
            _invalid(path, "contains a cyclic reference")
        active_containers.add(identity)
        try:
            if isinstance(value, Mapping):
                normalized: dict[str, Any] = {}
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
                for key in sorted(value):
                    child_trim_strings = trim_strings and key != "allowed_parameters"
                    normalized[key] = _canonicalize(
                        value[key],
                        f"{path}.{key}",
                        trim_strings=child_trim_strings,
                        _depth=_depth + 1,
                        _active_containers=active_containers,
                        _node_count=node_count,
                        _string_byte_count=string_byte_count,
                    )
                return normalized
            return [
                _canonicalize(
                    item,
                    f"{path}[{index}]",
                    trim_strings=trim_strings,
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
        return value.strip() if trim_strings else value
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


def normalize_case(raw_case: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and canonically normalize a case without mutating its input.

    Validation covers the permission-critical P0 shape.  Unknown JSON-safe
    fields remain in the result and therefore remain bound into the case hash.
    """

    case = _require_mapping(raw_case, "case")
    _require_nonempty_string(_required(case, "name", "case"), "case.name")

    objective = _require_mapping(_required(case, "objective", "case"), "case.objective")
    _require_nonempty_string(
        _required(objective, "primary", "case.objective"),
        "case.objective.primary",
    )
    _require_string_list(
        _required(objective, "protected_outcomes", "case.objective"),
        "case.objective.protected_outcomes",
    )
    _require_string_list(
        _required(objective, "anti_objectives", "case.objective"),
        "case.objective.anti_objectives",
    )

    _require_string_list(
        _required(case, "evidence_roots", "case"), "case.evidence_roots"
    )
    constraint_ids = _require_string_list(
        _required(case, "constraints", "case"),
        "case.constraints",
    )
    if len(set(constraint_ids)) != len(constraint_ids):
        _invalid("case.constraints", "must not contain duplicate constraint IDs")

    actions = _required(case, "actions", "case")
    if not isinstance(actions, list):
        _invalid("case.actions", "must be a list")
    if not actions:
        _invalid("case.actions", "must not be empty")
    if len(actions) > _MAX_CANONICAL_NODES:
        _invalid(
            "case.actions",
            f"exceeds maximum member count {_MAX_CANONICAL_NODES:,}",
        )

    action_ids: set[str] = set()
    for index, value in enumerate(actions):
        path = f"case.actions[{index}]"
        action = _require_mapping(value, path)
        action_id = _require_nonempty_string(
            _required(action, "id", path), f"{path}.id"
        )
        if action_id in action_ids:
            _invalid(f"{path}.id", f"duplicate action id {action_id!r}")
        action_ids.add(action_id)

        consequence = _require_nonempty_string(
            _required(action, "consequence", path), f"{path}.consequence"
        )
        if consequence not in _CONSEQUENCE_CLASSES:
            _invalid(
                f"{path}.consequence",
                f"must be one of {sorted(_CONSEQUENCE_CLASSES)}",
            )
        reversible = _required(action, "reversible", path)
        if type(reversible) is not bool:
            _invalid(f"{path}.reversible", "must be a boolean")
        _require_nonempty_string(
            _required(action, "authority", path), f"{path}.authority"
        )
        if "allowed_targets" in action:
            allowed_targets = _require_string_list(
                action["allowed_targets"],
                f"{path}.allowed_targets",
                allow_empty=False,
            )
            if len(set(allowed_targets)) != len(allowed_targets):
                _invalid(f"{path}.allowed_targets", "must not contain duplicates")
        _require_mapping(
            _required(action, "allowed_parameters", path),
            f"{path}.allowed_parameters",
        )

    verification = _require_mapping(
        _required(case, "verification", "case"), "case.verification"
    )
    _require_string_list(
        _required(
            verification,
            "success_conditions",
            "case.verification",
        ),
        "case.verification.success_conditions",
        allow_empty=False,
    )

    if "watch" in case:
        watch = _require_mapping(case["watch"], "case.watch")
        _require_string_list(
            _required(watch, "reopen_conditions", "case.watch"),
            "case.watch.reopen_conditions",
        )

    return cast(dict[str, Any], _canonicalize(case, "case"))


def case_fingerprint(raw_case: Mapping[str, Any]) -> str:
    """Return the SHA-256 identity of a validated normalized case."""

    return _sha256(normalize_case(raw_case))


def candidate_fingerprint(candidate: Mapping[str, Any]) -> str:
    """Return the SHA-256 identity of an exact candidate action.

    The full candidate is hashed, not just the three required interface fields,
    so adding or mutating a material execution parameter invalidates approval.
    """

    value = _require_mapping(candidate, "candidate")
    _require_nonempty_string(
        _required(value, "action_type", "candidate"),
        "candidate.action_type",
    )
    _require_nonempty_string(
        _required(value, "target", "candidate"), "candidate.target"
    )
    _require_mapping(
        _required(value, "parameters", "candidate"), "candidate.parameters"
    )

    return _sha256(_canonicalize(value, "candidate", trim_strings=False))

