"""
va_benefits_router.py
SQUAD BAT — VA Benefits Division module entry point.

Wraps VaBenefits_v0_1.py routing logic with standard module interface.
Accepts a dict payload, validates required fields, and returns a structured result.
"""

from __future__ import annotations

import sys
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Allow import from AGENTS/LOGIC without install
_LOGIC_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'AGENTS', 'LOGIC')
if _LOGIC_PATH not in sys.path:
    sys.path.insert(0, _LOGIC_PATH)

_SHARED_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '_shared')
if _SHARED_PATH not in sys.path:
    sys.path.insert(0, _SHARED_PATH)

from VaBenefits_v0_1 import VaBenefitsProfile, route_va_benefits  # type: ignore
from local_resources import find_local_resources, format_local_resource_line  # type: ignore


REQUIRED_FIELDS = {"discharge"}

VALID_DISCHARGE = {"honorable", "general", "other_than_honorable", "dishonorable", "unknown"}
VALID_ERA = {"post_9_11", "gulf_war", "vietnam", "korea", "peacetime", "unknown"}


@dataclass(frozen=True)
class VaBenefitsResult:
    status: str                    # OK | NEEDS_INPUT | FAILED_CLOSED
    primary_path: Optional[str]
    secondary_options: List[str]
    flags: List[str]
    next_action: Optional[str]
    key_forms: List[str]
    notes: List[str]
    questions: List[str]           # populated when NEEDS_INPUT
    audit: Dict[str, Any]
    # Added for local-resource lookup wiring. Found directly: this
    # Division had no key_resources field at all, so local resources were
    # going into secondary_options -- but pf_coordinator_v1.py's
    # invoke_division() truncates secondary_options to [:3] when building
    # next_actions, and every real intake that reaches this Division
    # already has 3+ items there before any local match gets appended.
    # Confirmed directly: a real Mesa County match was present in this
    # router's own return value but completely absent from the
    # coordinator's actual output. key_resources is NOT truncated by
    # invoke_division() (confirmed by reading it), which is why every
    # other Division routes local resources through it instead. A default
    # is given so no existing NEEDS_INPUT/FAILED_CLOSED construction here
    # needs to change.
    key_resources: List[str] = field(default_factory=list)


def _validate(payload: Dict[str, Any]) -> List[str]:
    """Returns list of validation errors. Empty = OK."""
    errors = []

    for field in REQUIRED_FIELDS:
        if field not in payload or not payload[field]:
            errors.append(f"Missing required field: {field}")

    discharge = payload.get("discharge", "")
    if discharge and discharge not in VALID_DISCHARGE:
        errors.append(f"Invalid discharge '{discharge}'. Valid: {sorted(VALID_DISCHARGE)}")

    era = payload.get("era", "")
    if era and era not in VALID_ERA:
        errors.append(f"Invalid era '{era}'. Valid: {sorted(VALID_ERA)}")

    rating = payload.get("disability_rating")
    if rating is not None:
        try:
            r = int(rating)
            if not (0 <= r <= 100):
                errors.append("disability_rating must be 0–100.")
        except (ValueError, TypeError):
            errors.append("disability_rating must be a number.")

    income = payload.get("income_monthly")
    if income is not None:
        try:
            int(income)
        except (ValueError, TypeError):
            errors.append("income_monthly must be a number.")

    months = payload.get("months_since_separation")
    if months is not None:
        try:
            int(months)
        except (ValueError, TypeError):
            errors.append("months_since_separation must be a number.")

    return errors


def _build_profile(payload: Dict[str, Any]) -> VaBenefitsProfile:
    def _bool(key: str) -> bool:
        return bool(payload.get(key, False))

    def _list(key: str) -> List[str]:
        val = payload.get(key, [])
        return val if isinstance(val, list) else []

    def _int_or_none(key: str) -> Optional[int]:
        val = payload.get(key)
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    return VaBenefitsProfile(
        discharge=payload["discharge"],
        era=payload.get("era", "unknown"),
        need_branches=_list("need_branches"),
        is_transitioning=_bool("is_transitioning"),
        disability_rating=_int_or_none("disability_rating"),
        wartime_service=_bool("wartime_service"),
        income_monthly=_int_or_none("income_monthly"),
        has_dependents=_bool("has_dependents"),
        is_survivor_or_dependent=_bool("is_survivor_or_dependent"),
        months_since_separation=_int_or_none("months_since_separation"),
        state=payload.get("state", ""),
        county=payload.get("county", ""),
    )


def _local_resource_tags(flags: List[str]) -> List[str]:
    """Service tags to search for, driven by the flags route_va_benefits()
    already computed."""
    tags = ["benefits_navigation", "claims_assistance"]

    if any(f in flags for f in ("vre_candidate", "ch33_candidate", "ch30_candidate", "dependent_education_programs")):
        tags.append("education_support")

    if any(f in flags for f in ("transitioning_service_member", "employment_track")):
        tags.extend(["employment_transition", "employment_support", "tap_program", "skillbridge_coordination"])

    if any(f in flags for f in ("pension_candidate", "pension_check_recommended")):
        tags.append("financial_counseling")

    if "survivor_dependent_track" in flags:
        tags.extend(["family_support", "bereavement"])

    if "burial_track" in flags:
        tags.append("memorial_civic")

    return tags


def run(payload: Dict[str, Any]) -> VaBenefitsResult:
    """
    Module entrypoint. Accepts a dict, returns VaBenefitsResult.

    Required fields:
        discharge (str): "honorable" | "general" | "other_than_honorable" | "dishonorable" | "unknown"

    Optional fields:
        era (str), need_branches (list), is_transitioning (bool),
        disability_rating (int 0–100), wartime_service (bool),
        income_monthly (int), has_dependents (bool),
        is_survivor_or_dependent (bool), months_since_separation (int),
        state (str), county (str)
    """
    audit: Dict[str, Any] = {
        "module": "VA_BENEFITS",
        "version": "0.1.0",
        "input_keys": sorted(payload.keys()),
    }

    # Validate
    errors = _validate(payload)
    if errors:
        return VaBenefitsResult(
            status="NEEDS_INPUT",
            primary_path=None,
            secondary_options=[],
            flags=["validation_error"],
            next_action=None,
            key_forms=[],
            notes=[],
            questions=errors,
            audit={**audit, "errors": errors},
        )

    # Route
    try:
        profile = _build_profile(payload)
        routing = route_va_benefits(profile)
    except Exception as exc:
        return VaBenefitsResult(
            status="FAILED_CLOSED",
            primary_path=None,
            secondary_options=[],
            flags=["routing_exception"],
            next_action="Contact a VSO directly: 1-800-827-1000 or va.gov",
            key_forms=[],
            notes=[str(exc)],
            questions=[],
            audit={**audit, "exception": str(exc)},
        )

    local = find_local_resources(
        state=profile.state,
        county=profile.county,
        service_tags=_local_resource_tags(routing.get("flags", [])),
    )
    key_resources = [format_local_resource_line(r) for r in local]

    return VaBenefitsResult(
        status="OK",
        primary_path=routing.get("primary_path"),
        secondary_options=routing.get("secondary_options", []),
        flags=routing.get("flags", []),
        next_action=routing.get("next_action"),
        key_forms=routing.get("key_forms", []),
        key_resources=key_resources,
        notes=routing.get("notes", []),
        questions=[],
        audit={**audit, "qualification_status": routing.get("qualification", {}).get("status")},
    )
