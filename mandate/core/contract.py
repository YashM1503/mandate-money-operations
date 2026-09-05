"""Deterministic Resolve Contract permission evaluation.

The model and integration layers may assemble structured decision facts, but
they cannot provide a gate result or final disposition.  This module validates
those facts and computes all permission consequences without model, network,
database, clock, or filesystem access.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Final, TypeVar, cast

from .case import candidate_fingerprint, case_fingerprint, normalize_case


class DecisionValidationError(ValueError):
    """Raised when a DecisionInput is unsafe or internally inconsistent."""


class GateValue(str, Enum):
    """The complete machine vocabulary for an individual contract gate."""

    # Bandit B105 treats any constant named PASS as a possible password.
    PASS = "PASS"  # nosec B105
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class Disposition(str, Enum):
    """The complete machine vocabulary for final permission disposition."""

    BLOCKED = "BLOCKED"
    MORE_EVIDENCE_REQUIRED = "MORE_EVIDENCE_REQUIRED"
    WAITING_HUMAN = "WAITING_HUMAN"
    ADMISSIBLE = "ADMISSIBLE"


_GATE_ORDER: Final[tuple[str, ...]] = (
    "intent",
    "evidence",
    "constraints",
    "consequence",
    "reversibility",
    "rehearsal",
    "authority",
    "verification",
)
_CONSEQUENCE_CLASSES: Final[frozenset[str]] = frozenset({"C0", "C1", "C2", "C3", "C4"})
_CONSEQUENCE_RANK: Final[dict[str, int]] = {
    "C0": 0,
    "C1": 1,
    "C2": 2,
    "C3": 3,
    "C4": 4,
}
_MAX_IDENTIFIER_BYTES: Final[int] = 4_096
_MAX_EVIDENCE_IDS: Final[int] = 10_000
_MAX_TOTAL_IDENTIFIER_BYTES: Final[int] = 1_048_576
_EVIDENCE_DOMAIN: Final[bytes] = b"resolve:evidence:v1\x00"
_DECISION_DOMAIN: Final[bytes] = b"resolve:decision:v1\x00"
_ReceiptT = TypeVar("_ReceiptT")
ConstraintValidator = Callable[[Mapping[str, Any], Mapping[str, Any]], tuple[str, ...]]
ObjectiveValidator = Callable[[Mapping[str, Any], "EvidenceReceipt"], str | None]


def _is_sha256(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    return all(character in "0123456789abcdef" for character in value)


def _validate_optional_string(value: object, field: str) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise DecisionValidationError(f"{field} must be a non-empty string or None")
    if isinstance(value, str) and len(value.encode("utf-8")) > _MAX_IDENTIFIER_BYTES:
        raise DecisionValidationError(
            f"{field} must not exceed {_MAX_IDENTIFIER_BYTES:,} bytes"
        )


def _validate_bool(value: object, field: str) -> None:
    if type(value) is not bool:
        raise DecisionValidationError(f"{field} must be a boolean")


def _validate_optional_bool(value: object, field: str) -> None:
    if value is not None and type(value) is not bool:
        raise DecisionValidationError(f"{field} must be a boolean or None")


def _validate_evidence_ids(value: object, field: str) -> None:
    if not isinstance(value, frozenset):
        raise DecisionValidationError(f"{field} must be a frozenset")
    if len(value) > _MAX_EVIDENCE_IDS:
        raise DecisionValidationError(
            f"{field} must not exceed {_MAX_EVIDENCE_IDS:,} IDs"
        )
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise DecisionValidationError(f"{field} contains an invalid evidence ID")
    if any(len(item.encode("utf-8")) > _MAX_IDENTIFIER_BYTES for item in value):
        raise DecisionValidationError(
            f"{field} contains an ID exceeding {_MAX_IDENTIFIER_BYTES:,} bytes"
        )
    if sum(len(item.encode("utf-8")) for item in value) > _MAX_TOTAL_IDENTIFIER_BYTES:
        raise DecisionValidationError(
            f"{field} exceeds total identifier budget "
            f"{_MAX_TOTAL_IDENTIFIER_BYTES:,} bytes"
        )


def _validated_sha256(value: object, field: str) -> str:
    if not _is_sha256(value):
        raise DecisionValidationError(f"{field} must be a SHA-256 hex digest")
    return cast(str, value)


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


@dataclass(frozen=True, slots=True, init=False)
class EvidenceReceipt:
    """Validated evidence registry content and the IDs used by one candidate."""

    evidence_fingerprint: str
    required_evidence_ids: frozenset[str]
    available_evidence_ids: frozenset[str]
    candidate_evidence_ids: frozenset[str]
    _validated: bool


@dataclass(frozen=True, slots=True, init=False)
class ObjectiveReceipt:
    """Authorized objective derived by trusted Python and bound to evidence."""

    case_fingerprint: str
    evidence_fingerprint: str
    authorized_objective: str | None
    candidate_objective: str | None
    _validated: bool


@dataclass(frozen=True, slots=True, init=False)
class ConstraintValidationReceipt:
    """Trusted constraint-validator result bound to one case and candidate."""

    case_fingerprint: str
    candidate_fingerprint: str
    checked_constraint_ids: frozenset[str]
    violations: tuple[str, ...]
    _validated: bool


@dataclass(frozen=True, slots=True, init=False)
class RehearsalReceipt:
    """Simulator rehearsal result bound to one candidate and starting state."""

    candidate_fingerprint: str
    state_fingerprint: str
    passed: bool
    _validated: bool


@dataclass(frozen=True, slots=True, init=False)
class VerificationReceipt:
    """Verification-plan result bound to one candidate and starting state."""

    candidate_fingerprint: str
    state_fingerprint: str
    possible: bool
    _validated: bool


def _new_receipt(receipt_type: type[_ReceiptT], **values: object) -> _ReceiptT:
    receipt = object.__new__(receipt_type)
    for field, value in values.items():
        object.__setattr__(receipt, field, value)
    return receipt


def build_evidence_receipt(
    *,
    evidence_registry: Mapping[str, str],
    required_evidence_ids: frozenset[str],
    candidate_evidence_ids: frozenset[str],
) -> EvidenceReceipt:
    """Validate evidence content hashes and bind the exact available snapshot."""

    if not isinstance(evidence_registry, Mapping):
        raise DecisionValidationError("evidence_registry must be a mapping")
    if any(not isinstance(key, str) for key in evidence_registry):
        raise DecisionValidationError("evidence_registry keys must be strings")
    available_evidence_ids = frozenset(evidence_registry)
    _validate_evidence_ids(required_evidence_ids, "required_evidence_ids")
    _validate_evidence_ids(available_evidence_ids, "available_evidence_ids")
    _validate_evidence_ids(candidate_evidence_ids, "candidate_evidence_ids")
    for evidence_id, content_fingerprint in evidence_registry.items():
        _validated_sha256(
            content_fingerprint,
            f"evidence_registry[{evidence_id!r}]",
        )
    registry_payload = {
        evidence_id: evidence_registry[evidence_id]
        for evidence_id in sorted(evidence_registry)
    }
    fingerprint = hashlib.sha256(
        _EVIDENCE_DOMAIN + _canonical_json(registry_payload).encode("utf-8")
    ).hexdigest()
    return _new_receipt(
        EvidenceReceipt,
        evidence_fingerprint=fingerprint,
        required_evidence_ids=required_evidence_ids,
        available_evidence_ids=available_evidence_ids,
        candidate_evidence_ids=candidate_evidence_ids,
        _validated=True,
    )


def build_objective_receipt(
    *,
    raw_case: Mapping[str, Any],
    evidence_receipt: EvidenceReceipt,
    candidate_objective: str | None,
    validator: ObjectiveValidator,
) -> ObjectiveReceipt:
    """Derive the authorized objective through a trusted local validator."""

    if not isinstance(raw_case, Mapping):
        raise DecisionValidationError("raw_case must be a mapping")
    normalized = normalize_case(raw_case)
    if not isinstance(evidence_receipt, EvidenceReceipt) or not getattr(
        evidence_receipt, "_validated", False
    ):
        raise DecisionValidationError("evidence_receipt must be an EvidenceReceipt")
    _validate_optional_string(candidate_objective, "candidate_objective")
    if not callable(validator):
        raise DecisionValidationError("objective validator must be callable")
    try:
        authorized_objective = validator(normalized, evidence_receipt)
    except Exception as error:
        raise DecisionValidationError("objective validator failed") from error
    _validate_optional_string(authorized_objective, "authorized_objective")
    return _new_receipt(
        ObjectiveReceipt,
        case_fingerprint=case_fingerprint(raw_case),
        evidence_fingerprint=evidence_receipt.evidence_fingerprint,
        authorized_objective=authorized_objective,
        candidate_objective=candidate_objective,
        _validated=True,
    )


def _validate_violation_codes(value: object) -> tuple[str, ...]:
    if not isinstance(value, tuple) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise DecisionValidationError("violations must be a tuple of non-empty strings")
    if len(value) > _MAX_EVIDENCE_IDS:
        raise DecisionValidationError("violations is too large")
    if any(len(item.encode("utf-8")) > _MAX_IDENTIFIER_BYTES for item in value):
        raise DecisionValidationError("violations contains an oversized code")
    return value


def build_constraint_validation_receipt(
    *,
    raw_case: Mapping[str, Any],
    candidate: Mapping[str, Any],
    validators: Mapping[str, ConstraintValidator],
) -> ConstraintValidationReceipt:
    """Run trusted Python validators and bind their results to exact inputs."""

    normalized = normalize_case(raw_case)
    bound_case_fingerprint = case_fingerprint(raw_case)
    bound_candidate_fingerprint = candidate_fingerprint(candidate)
    known_constraints = frozenset(normalized["constraints"])
    if not isinstance(validators, Mapping) or any(
        not isinstance(key, str) for key in validators
    ):
        raise DecisionValidationError("validators must map constraint IDs to callables")
    checked_constraint_ids = frozenset(validators)
    _validate_evidence_ids(checked_constraint_ids, "checked_constraint_ids")
    if not checked_constraint_ids <= known_constraints:
        raise DecisionValidationError("validators contains an unknown constraint ID")
    violations: list[str] = []
    for constraint_id in sorted(checked_constraint_ids):
        validator = validators[constraint_id]
        if not callable(validator):
            raise DecisionValidationError(
                f"validator for {constraint_id!r} must be callable"
            )
        try:
            result = validator(normalized, candidate)
        except Exception as error:
            raise DecisionValidationError(
                f"validator for {constraint_id!r} failed"
            ) from error
        violations.extend(_validate_violation_codes(result))
    validated_violations = _validate_violation_codes(tuple(violations))
    return _new_receipt(
        ConstraintValidationReceipt,
        case_fingerprint=bound_case_fingerprint,
        candidate_fingerprint=bound_candidate_fingerprint,
        checked_constraint_ids=checked_constraint_ids,
        violations=validated_violations,
        _validated=True,
    )


def build_rehearsal_receipt(
    *, candidate: Mapping[str, Any], state_fingerprint: str, passed: bool
) -> RehearsalReceipt:
    """Bind a trusted bounded-rehearsal result to candidate and starting state."""

    _validated_sha256(state_fingerprint, "state_fingerprint")
    _validate_bool(passed, "passed")
    return _new_receipt(
        RehearsalReceipt,
        candidate_fingerprint=candidate_fingerprint(candidate),
        state_fingerprint=state_fingerprint,
        passed=passed,
        _validated=True,
    )


def build_verification_receipt(
    *, candidate: Mapping[str, Any], state_fingerprint: str, possible: bool
) -> VerificationReceipt:
    """Bind a trusted verification-plan result to candidate and starting state."""

    _validated_sha256(state_fingerprint, "state_fingerprint")
    _validate_bool(possible, "possible")
    return _new_receipt(
        VerificationReceipt,
        candidate_fingerprint=candidate_fingerprint(candidate),
        state_fingerprint=state_fingerprint,
        possible=possible,
        _validated=True,
    )


@dataclass(frozen=True, slots=True, init=False)
class DecisionInput:
    """Validated, immutable facts consumed by the permission kernel.

    No field accepts model-authored gate values or dispositions.  Objective IDs
    and evidence IDs are explicit identifiers resolved by upstream validation;
    this module compares them rather than performing semantic interpretation.
    """

    case_fingerprint: str
    candidate_fingerprint: str
    evidence_fingerprint: str
    state_fingerprint: str
    authorized_objective: str | None
    candidate_objective: str | None
    required_evidence_ids: frozenset[str]
    available_evidence_ids: frozenset[str]
    candidate_evidence_ids: frozenset[str]
    constraints_checked: bool
    hard_constraint_violations: tuple[str, ...]
    consequence_class: str | None
    consequence_assessed: bool
    reversibility_required: bool
    reversibility_confirmed: bool | None
    rehearsal_required: bool
    rehearsal_passed: bool | None
    human_approval_required: bool
    required_authority: str | None
    requested_approver_role: str | None
    verification_possible: bool | None

    def _validate(self) -> None:
        if not _is_sha256(self.case_fingerprint):
            raise DecisionValidationError(
                "case_fingerprint must be a SHA-256 hex digest"
            )
        if not _is_sha256(self.candidate_fingerprint):
            raise DecisionValidationError(
                "candidate_fingerprint must be a SHA-256 hex digest"
            )
        _validated_sha256(self.evidence_fingerprint, "evidence_fingerprint")
        _validated_sha256(self.state_fingerprint, "state_fingerprint")

        _validate_optional_string(self.authorized_objective, "authorized_objective")
        _validate_optional_string(self.candidate_objective, "candidate_objective")
        _validate_evidence_ids(self.required_evidence_ids, "required_evidence_ids")
        _validate_evidence_ids(self.available_evidence_ids, "available_evidence_ids")
        _validate_evidence_ids(self.candidate_evidence_ids, "candidate_evidence_ids")
        _validate_bool(self.constraints_checked, "constraints_checked")

        if not isinstance(self.hard_constraint_violations, tuple) or any(
            not isinstance(item, str) or not item.strip()
            for item in self.hard_constraint_violations
        ):
            raise DecisionValidationError(
                "hard_constraint_violations must be a tuple of non-empty strings"
            )
        if len(self.hard_constraint_violations) > _MAX_EVIDENCE_IDS or any(
            len(item.encode("utf-8")) > _MAX_IDENTIFIER_BYTES
            for item in self.hard_constraint_violations
        ):
            raise DecisionValidationError("hard_constraint_violations is too large")
        if (
            sum(len(item.encode("utf-8")) for item in self.hard_constraint_violations)
            > _MAX_TOTAL_IDENTIFIER_BYTES
        ):
            raise DecisionValidationError(
                "hard_constraint_violations exceeds total identifier budget"
            )

        if (
            self.consequence_class is not None
            and self.consequence_class not in _CONSEQUENCE_CLASSES
        ):
            raise DecisionValidationError(
                f"consequence_class must be one of {sorted(_CONSEQUENCE_CLASSES)} or None"
            )
        _validate_bool(self.consequence_assessed, "consequence_assessed")
        _validate_bool(self.reversibility_required, "reversibility_required")
        _validate_optional_bool(self.reversibility_confirmed, "reversibility_confirmed")
        _validate_bool(self.rehearsal_required, "rehearsal_required")
        _validate_optional_bool(self.rehearsal_passed, "rehearsal_passed")
        _validate_bool(self.human_approval_required, "human_approval_required")
        _validate_optional_string(self.required_authority, "required_authority")
        _validate_optional_string(
            self.requested_approver_role, "requested_approver_role"
        )
        _validate_optional_bool(self.verification_possible, "verification_possible")


def _parameter_allowed(value: object, rule: object) -> bool | None:
    """Return whether a value satisfies one frozen allowed-parameter rule."""

    if isinstance(rule, list):
        return any(type(value) is type(item) and value == item for item in rule)
    if isinstance(rule, Mapping):
        if not rule or any(key not in {"minimum", "maximum"} for key in rule):
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        minimum = rule.get("minimum")
        maximum = rule.get("maximum")
        if minimum is not None and (
            isinstance(minimum, bool)
            or not isinstance(minimum, (int, float))
            or value < minimum
        ):
            return False
        if maximum is not None and (
            isinstance(maximum, bool)
            or not isinstance(maximum, (int, float))
            or value > maximum
        ):
            return False
        return minimum is not None or maximum is not None
    return type(value) is type(rule) and value == rule


def _derive_policy(
    raw_case: Mapping[str, Any], candidate: Mapping[str, Any]
) -> tuple[bool, tuple[str, ...], str | None, bool, bool, bool, str | None, bool]:
    """Derive permission policy from the case rather than caller assertions."""

    normalized = normalize_case(raw_case)
    action_type = candidate.get("action_type")
    actions = normalized["actions"]
    action = next((item for item in actions if item["id"] == action_type), None)
    if action is None:
        return (
            True,
            ("ACTION_NOT_AUTHORIZED",),
            None,
            True,
            True,
            True,
            None,
            False,
        )

    candidate_parameters = candidate["parameters"]
    allowed_parameters = action["allowed_parameters"]

    violations: list[str] = []
    constraints_checked = True
    candidate_target = candidate.get("target")
    allowed_targets = action.get("allowed_targets")
    if allowed_targets is None:
        constraints_checked = False
    elif not any(
        type(candidate_target) is type(target) and candidate_target == target
        for target in allowed_targets
    ):
        violations.append("TARGET_NOT_AUTHORIZED")
    candidate_keys = set(candidate_parameters)
    allowed_keys = set(allowed_parameters)
    if candidate_keys != allowed_keys:
        violations.append("PARAMETER_SET_NOT_AUTHORIZED")
    for name in sorted(candidate_keys & allowed_keys):
        allowed = _parameter_allowed(
            candidate_parameters[name], allowed_parameters[name]
        )
        if allowed is None:
            constraints_checked = False
        elif not allowed:
            violations.append(f"PARAMETER_NOT_AUTHORIZED:{name}")

    consequence_class = action["consequence"]
    high_consequence = _CONSEQUENCE_RANK[consequence_class] >= _CONSEQUENCE_RANK["C2"]
    explicit_human = action.get("human_approval_required", False)
    explicit_rehearsal = action.get("rehearsal_required", False)
    if type(explicit_human) is not bool or type(explicit_rehearsal) is not bool:
        raise DecisionValidationError(
            "action approval and rehearsal requirements must be booleans"
        )
    return (
        constraints_checked,
        tuple(violations),
        consequence_class,
        high_consequence,
        high_consequence or explicit_rehearsal,
        high_consequence or explicit_human,
        action["authority"],
        action["reversible"],
    )


def build_decision_input(
    *,
    raw_case: Mapping[str, Any],
    candidate: Mapping[str, Any],
    objective_receipt: ObjectiveReceipt,
    evidence_receipt: EvidenceReceipt,
    constraint_receipt: ConstraintValidationReceipt | None,
    state_fingerprint: str,
    consequence_assessed: bool,
    reversibility_confirmed: bool | None,
    rehearsal_receipt: RehearsalReceipt | None,
    requested_approver_role: str | None,
    verification_receipt: VerificationReceipt | None,
) -> DecisionInput:
    """Build the only supported DecisionInput from case-derived policy facts.

    Model output may propose the candidate and cite evidence, but it cannot set
    constraints, consequence, rehearsal requirements, authority, or whether a
    human is required.  Those permission-producing facts come from the case.
    """

    if not isinstance(raw_case, Mapping):
        raise DecisionValidationError("raw_case must be a mapping")
    if not isinstance(candidate, Mapping):
        raise DecisionValidationError("candidate must be a mapping")
    if not isinstance(evidence_receipt, EvidenceReceipt) or not getattr(
        evidence_receipt, "_validated", False
    ):
        raise DecisionValidationError("evidence_receipt must be an EvidenceReceipt")
    _validated_sha256(state_fingerprint, "state_fingerprint")
    current_case_fingerprint = case_fingerprint(raw_case)
    current_candidate_fingerprint = candidate_fingerprint(candidate)
    if not isinstance(objective_receipt, ObjectiveReceipt) or not getattr(
        objective_receipt, "_validated", False
    ):
        raise DecisionValidationError("objective_receipt must be an ObjectiveReceipt")
    if (
        objective_receipt.case_fingerprint != current_case_fingerprint
        or objective_receipt.evidence_fingerprint
        != evidence_receipt.evidence_fingerprint
    ):
        raise DecisionValidationError(
            "objective receipt does not match case and evidence"
        )
    (
        constraints_checked,
        hard_constraint_violations,
        consequence_class,
        reversibility_required,
        rehearsal_required,
        human_approval_required,
        required_authority,
        policy_reversible,
    ) = _derive_policy(raw_case, candidate)

    required_constraints = frozenset(normalize_case(raw_case)["constraints"])
    if constraint_receipt is None:
        constraints_checked = False
        receipt_violations: tuple[str, ...] = ()
    elif not isinstance(constraint_receipt, ConstraintValidationReceipt) or not getattr(
        constraint_receipt, "_validated", False
    ):
        raise DecisionValidationError(
            "constraint_receipt must be a ConstraintValidationReceipt or None"
        )
    else:
        if (
            constraint_receipt.case_fingerprint != current_case_fingerprint
            or constraint_receipt.candidate_fingerprint != current_candidate_fingerprint
        ):
            raise DecisionValidationError(
                "constraint receipt does not match case and candidate"
            )
        constraints_checked = constraints_checked and (
            constraint_receipt.checked_constraint_ids == required_constraints
        )
        receipt_violations = constraint_receipt.violations
    hard_constraint_violations = tuple(
        dict.fromkeys((*hard_constraint_violations, *receipt_violations))
    )

    if rehearsal_receipt is None:
        rehearsal_passed = None
    elif not isinstance(rehearsal_receipt, RehearsalReceipt) or not getattr(
        rehearsal_receipt, "_validated", False
    ):
        raise DecisionValidationError(
            "rehearsal_receipt must be a RehearsalReceipt or None"
        )
    else:
        if (
            rehearsal_receipt.candidate_fingerprint != current_candidate_fingerprint
            or rehearsal_receipt.state_fingerprint != state_fingerprint
        ):
            raise DecisionValidationError(
                "rehearsal receipt does not match candidate and state"
            )
        rehearsal_passed = rehearsal_receipt.passed

    if verification_receipt is None:
        verification_possible = None
    elif not isinstance(verification_receipt, VerificationReceipt) or not getattr(
        verification_receipt, "_validated", False
    ):
        raise DecisionValidationError(
            "verification_receipt must be a VerificationReceipt or None"
        )
    else:
        if (
            verification_receipt.candidate_fingerprint != current_candidate_fingerprint
            or verification_receipt.state_fingerprint != state_fingerprint
        ):
            raise DecisionValidationError(
                "verification receipt does not match candidate and state"
            )
        verification_possible = verification_receipt.possible

    if reversibility_required and not policy_reversible:
        reversibility_confirmed = False

    decision = object.__new__(DecisionInput)
    values: dict[str, object] = {
        "case_fingerprint": current_case_fingerprint,
        "candidate_fingerprint": current_candidate_fingerprint,
        "evidence_fingerprint": evidence_receipt.evidence_fingerprint,
        "state_fingerprint": state_fingerprint,
        "authorized_objective": objective_receipt.authorized_objective,
        "candidate_objective": objective_receipt.candidate_objective,
        "required_evidence_ids": evidence_receipt.required_evidence_ids,
        "available_evidence_ids": evidence_receipt.available_evidence_ids,
        "candidate_evidence_ids": evidence_receipt.candidate_evidence_ids,
        "constraints_checked": constraints_checked,
        "hard_constraint_violations": hard_constraint_violations,
        "consequence_class": consequence_class,
        "consequence_assessed": consequence_assessed,
        "reversibility_required": reversibility_required,
        "reversibility_confirmed": reversibility_confirmed,
        "rehearsal_required": rehearsal_required,
        "rehearsal_passed": rehearsal_passed,
        "human_approval_required": human_approval_required,
        "required_authority": required_authority,
        "requested_approver_role": requested_approver_role,
        "verification_possible": verification_possible,
    }
    for field, value in values.items():
        object.__setattr__(decision, field, value)
    decision._validate()
    return decision


@dataclass(frozen=True, slots=True)
class ContractResult:
    """Immutable gate vector, final disposition, and stable reason codes."""

    gates: Mapping[str, GateValue]
    disposition: Disposition
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to the frozen integration interface."""

        return {
            "gates": {name: self.gates[name].value for name in _GATE_ORDER},
            "disposition": self.disposition.value,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True, init=False)
class EvaluatedDecision:
    """A contract result cryptographically bound to its complete input context."""

    decision_fingerprint: str
    case_fingerprint: str
    candidate_fingerprint: str
    evidence_fingerprint: str
    state_fingerprint: str
    required_authority: str | None
    consequence_class: str | None
    human_approval_required: bool
    result: ContractResult
    _validated: bool

    def to_dict(self) -> dict[str, Any]:
        """Serialize the context envelope Coder 3 must persist and approve."""

        return {
            "decision_fingerprint": self.decision_fingerprint,
            "case_fingerprint": self.case_fingerprint,
            "candidate_fingerprint": self.candidate_fingerprint,
            "evidence_fingerprint": self.evidence_fingerprint,
            "state_fingerprint": self.state_fingerprint,
            "required_authority": self.required_authority,
            "consequence_class": self.consequence_class,
            "human_approval_required": self.human_approval_required,
            "contract_result": self.result.to_dict(),
        }


def decision_fingerprint(decision: DecisionInput) -> str:
    """Return a stable identity for every fact that produced a gate vector."""

    if not isinstance(decision, DecisionInput):
        raise DecisionValidationError("decision must be a DecisionInput")
    decision._validate()
    payload = {
        "case_fingerprint": decision.case_fingerprint,
        "candidate_fingerprint": decision.candidate_fingerprint,
        "evidence_fingerprint": decision.evidence_fingerprint,
        "state_fingerprint": decision.state_fingerprint,
        "authorized_objective": decision.authorized_objective,
        "candidate_objective": decision.candidate_objective,
        "required_evidence_ids": sorted(decision.required_evidence_ids),
        "available_evidence_ids": sorted(decision.available_evidence_ids),
        "candidate_evidence_ids": sorted(decision.candidate_evidence_ids),
        "constraints_checked": decision.constraints_checked,
        "hard_constraint_violations": list(decision.hard_constraint_violations),
        "consequence_class": decision.consequence_class,
        "consequence_assessed": decision.consequence_assessed,
        "reversibility_required": decision.reversibility_required,
        "reversibility_confirmed": decision.reversibility_confirmed,
        "rehearsal_required": decision.rehearsal_required,
        "rehearsal_passed": decision.rehearsal_passed,
        "human_approval_required": decision.human_approval_required,
        "required_authority": decision.required_authority,
        "requested_approver_role": decision.requested_approver_role,
        "verification_possible": decision.verification_possible,
    }
    return hashlib.sha256(
        _DECISION_DOMAIN + _canonical_json(payload).encode("utf-8")
    ).hexdigest()


GateEvaluation = tuple[GateValue, tuple[str, ...]]


def _evaluate_intent(decision: DecisionInput) -> GateEvaluation:
    if decision.authorized_objective is None or decision.candidate_objective is None:
        return GateValue.UNKNOWN, ("OBJECTIVE_MISSING",)
    if decision.authorized_objective != decision.candidate_objective:
        return GateValue.FAIL, ("OBJECTIVE_CONFLICT",)
    return GateValue.PASS, ()


def _evaluate_evidence(decision: DecisionInput) -> GateEvaluation:
    invalid_references = (
        decision.candidate_evidence_ids - decision.available_evidence_ids
    )
    missing_required = (
        decision.required_evidence_ids - decision.available_evidence_ids
    ) | (decision.required_evidence_ids - decision.candidate_evidence_ids)

    reasons: list[str] = []
    if invalid_references:
        reasons.append("INVALID_EVIDENCE_REFERENCE")
    if missing_required:
        reasons.append("MISSING_REQUIRED_EVIDENCE")
    if invalid_references:
        return GateValue.FAIL, tuple(reasons)
    if missing_required:
        return GateValue.UNKNOWN, tuple(reasons)
    return GateValue.PASS, ()


def _evaluate_constraints(decision: DecisionInput) -> GateEvaluation:
    if decision.hard_constraint_violations:
        return GateValue.FAIL, ("HARD_CONSTRAINT_VIOLATION",)
    if not decision.constraints_checked:
        return GateValue.UNKNOWN, ("CONSTRAINTS_NOT_CHECKED",)
    return GateValue.PASS, ()


def _evaluate_consequence(decision: DecisionInput) -> GateEvaluation:
    if decision.consequence_class is None:
        return GateValue.UNKNOWN, ("CONSEQUENCE_UNKNOWN",)
    if not decision.consequence_assessed:
        return GateValue.UNKNOWN, ("CONSEQUENCE_NOT_ASSESSED",)
    return GateValue.PASS, ()


def _evaluate_reversibility(decision: DecisionInput) -> GateEvaluation:
    if not decision.reversibility_required:
        return GateValue.PASS, ()
    if decision.reversibility_confirmed is None:
        return GateValue.UNKNOWN, ("REVERSIBILITY_UNKNOWN",)
    if not decision.reversibility_confirmed:
        return GateValue.FAIL, ("REVERSIBILITY_REQUIRED",)
    return GateValue.PASS, ()


def _evaluate_rehearsal(decision: DecisionInput) -> GateEvaluation:
    if not decision.rehearsal_required:
        return GateValue.PASS, ()
    if decision.rehearsal_passed is None:
        return GateValue.UNKNOWN, ("REHEARSAL_MISSING",)
    if not decision.rehearsal_passed:
        return GateValue.FAIL, ("REHEARSAL_FAILED",)
    return GateValue.PASS, ()


def _evaluate_authority(decision: DecisionInput) -> GateEvaluation:
    if decision.required_authority is None or decision.requested_approver_role is None:
        return GateValue.UNKNOWN, ("AUTHORITY_UNKNOWN",)
    if decision.required_authority != decision.requested_approver_role:
        return GateValue.FAIL, ("AUTHORITY_MISMATCH",)
    return GateValue.PASS, ()


def _evaluate_verification(decision: DecisionInput) -> GateEvaluation:
    if decision.verification_possible is None:
        return GateValue.UNKNOWN, ("VERIFICATION_UNKNOWN",)
    if not decision.verification_possible:
        return GateValue.FAIL, ("VERIFICATION_IMPOSSIBLE",)
    return GateValue.PASS, ()


def evaluate_contract(decision: DecisionInput) -> ContractResult:
    """Compute all eight gates and the final deterministic disposition."""

    if not isinstance(decision, DecisionInput):
        raise DecisionValidationError("decision must be a DecisionInput")

    evaluations: tuple[GateEvaluation, ...] = (
        _evaluate_intent(decision),
        _evaluate_evidence(decision),
        _evaluate_constraints(decision),
        _evaluate_consequence(decision),
        _evaluate_reversibility(decision),
        _evaluate_rehearsal(decision),
        _evaluate_authority(decision),
        _evaluate_verification(decision),
    )
    gate_values = {
        name: evaluation[0]
        for name, evaluation in zip(_GATE_ORDER, evaluations, strict=True)
    }
    reason_codes = tuple(reason for _, reasons in evaluations for reason in reasons)

    if any(value is GateValue.FAIL for value in gate_values.values()):
        disposition = Disposition.BLOCKED
    elif any(value is GateValue.UNKNOWN for value in gate_values.values()):
        disposition = Disposition.MORE_EVIDENCE_REQUIRED
    elif decision.human_approval_required:
        disposition = Disposition.WAITING_HUMAN
    else:
        disposition = Disposition.ADMISSIBLE

    return ContractResult(
        gates=MappingProxyType(gate_values),
        disposition=disposition,
        reason_codes=reason_codes,
    )


def evaluate_decision(decision: DecisionInput) -> EvaluatedDecision:
    """Evaluate and wrap a result with the exact context Coder 3 must persist."""

    result = evaluate_contract(decision)
    return _new_receipt(
        EvaluatedDecision,
        decision_fingerprint=decision_fingerprint(decision),
        case_fingerprint=decision.case_fingerprint,
        candidate_fingerprint=decision.candidate_fingerprint,
        evidence_fingerprint=decision.evidence_fingerprint,
        state_fingerprint=decision.state_fingerprint,
        required_authority=decision.required_authority,
        consequence_class=decision.consequence_class,
        human_approval_required=decision.human_approval_required,
        result=result,
        _validated=True,
    )

