"""
housing_router.py
SQUAD BAT — Housing Division module entry point.

Wraps Housing_v0_1.py routing logic with standard module interface.
"""

from __future__ import annotations

import sys
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

_LOGIC_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'AGENTS', 'LOGIC')
if _LOGIC_PATH not in sys.path:
    sys.path.insert(0, _LOGIC_PATH)

_SHARED_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '_shared')
if _SHARED_PATH not in sys.path:
    sys.path.insert(0, _SHARED_PATH)

from Housing_v0_1 import VetHousingProfile, route_housing  # type: ignore
from local_resources import find_local_resources, format_local_resource_line  # type: ignore


VALID_HOUSING_STATUS = {"unhoused", "unstable", "at_risk", "stable", "unknown"}
VALID_DISCHARGE = {
    "honorable", "general", "other_than_honorable", "dishonorable",
    "unknown", "medical", "entry_level", "bcd",
}


@dataclass(frozen=True)
class HousingResult:
    status: str
    primary_path: Optional[str]
    secondary_options: List[str]
    flags: List[str]
    next_action: Optional[str]
    key_resources: List[str]
    key_forms: List[str]
    notes: List[str]
    questions: List[str]
    audit: Dict[str, Any]


def _validate(payload: Dict[str, Any]) -> List[str]:
    errors = []

    hs = payload.get("housing_status", "")
    if hs and hs not in VALID_HOUSING_STATUS:
        errors.append(f"Invalid housing_status '{hs}'. Valid: {sorted(VALID_HOUSING_STATUS)}")

    discharge_raw = payload.get("discharge", "")
    discharge = discharge_raw[0] if isinstance(discharge_raw, list) else discharge_raw
    if discharge and discharge not in VALID_DISCHARGE:
        errors.append(f"Invalid discharge '{discharge}'. Valid: {sorted(VALID_DISCHARGE)}")

    months = payload.get("homelessness_months")
    if months is not None:
        try:
            m = int(months)
            if m < 0:
                errors.append("homelessness_months must be >= 0.")
        except (ValueError, TypeError):
            errors.append("homelessness_months must be a number.")

    rating = payload.get("disability_rating")
    if rating is not None:
        try:
            r = int(rating)
            if not (0 <= r <= 100):
                errors.append("disability_rating must be 0–100.")
        except (ValueError, TypeError):
            errors.append("disability_rating must be a number.")

    return errors


def _build_profile(payload: Dict[str, Any]) -> VetHousingProfile:
    def _bool(key: str) -> bool:
        return bool(payload.get(key, False))

    def _int_or_none(key: str) -> Optional[int]:
        val = payload.get(key)
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    def _int_or_zero(key: str) -> int:
        val = payload.get(key, 0)
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0

    def _str_or_first(key: str, default: str = "") -> str:
        val = payload.get(key, default)
        return val[0] if isinstance(val, list) else (val or default)

    return VetHousingProfile(
        housing_status=payload.get("housing_status", "unknown"),
        homelessness_months=_int_or_zero("homelessness_months"),
        is_chronically_homeless=_bool("is_chronically_homeless"),
        has_dv_situation=_bool("has_dv_situation"),
        has_active_criminal_case=_bool("active_criminal_case"),
        disability_rating=_int_or_none("disability_rating"),
        has_va_loan_interest=_bool("has_va_loan_interest"),
        discharge=_str_or_first("discharge", "unknown"),
        branch=_str_or_first("branch", "unknown"),
        facing_eviction=_bool("facing_eviction"),
        va_facility_obstruction=_bool("va_facility_obstruction"),
        state=payload.get("state", ""),
        county=payload.get("county", ""),
    )


def _local_resource_tags(flags: List[str]) -> List[str]:
    """Service tags to search for, driven by the flags route_housing()
    already computed -- reuses signal the Division itself decided was
    relevant, rather than re-deriving separate logic from the raw profile."""
    tags = ["housing_support"]

    if any(f in flags for f in ("chronically_homeless", "currently_unhoused", "housing_at_risk", "eviction_imminent")):
        tags.extend(["homelessness_prevention", "emergency_shelter"])

    if "dv_housing_need" in flags:
        tags.extend(["dv_shelter", "dv_advocacy"])

    if "housing_legal_protection" in flags:
        tags.append("legal_referral")

    return tags


def run(payload: Dict[str, Any]) -> HousingResult:
    """
    Module entrypoint. No required fields — every veteran gets a path.

    Optional fields:
        housing_status (str), homelessness_months (int),
        is_chronically_homeless (bool), has_dv_situation (bool),
        active_criminal_case (bool), disability_rating (int),
        discharge (str), branch (str), facing_eviction (bool),
        va_facility_obstruction (bool), state (str), county (str)
    """
    audit: Dict[str, Any] = {
        "module": "HOUSING",
        "version": "0.1.0",
        "input_keys": sorted(payload.keys()),
    }

    errors = _validate(payload)
    if errors:
        return HousingResult(
            status="NEEDS_INPUT",
            primary_path=None,
            secondary_options=[],
            flags=["validation_error"],
            next_action=None,
            key_resources=[],
            key_forms=[],
            notes=[],
            questions=errors,
            audit={**audit, "errors": errors},
        )

    try:
        profile = _build_profile(payload)
        routing = route_housing(profile)
    except Exception as exc:
        return HousingResult(
            status="FAILED_CLOSED",
            primary_path=None,
            secondary_options=[],
            flags=["routing_exception"],
            next_action=(
                "Call VA National Call Center for Homeless Veterans: "
                "1-877-4AID-VET (1-877-424-3838) — 24/7."
            ),
            key_resources=["VA National Call Center for Homeless Veterans — 1-877-4AID-VET (1-877-424-3838)"],
            key_forms=[],
            notes=[str(exc)],
            questions=[],
            audit={**audit, "exception": str(exc)},
        )

    key_resources = list(routing.get("key_resources", []))

    # Additive only: local_resources fails safe and never raises, so a bad
    # shard file or unresolvable county degrades to "no local resources
    # found" -- this can never take the routing result above down with it.
    local = find_local_resources(
        state=profile.state,
        county=profile.county,
        service_tags=_local_resource_tags(routing.get("flags", [])),
    )
    key_resources.extend(format_local_resource_line(r) for r in local)

    return HousingResult(
        status="OK",
        primary_path=routing.get("primary_path"),
        secondary_options=routing.get("secondary_options", []),
        flags=routing.get("flags", []),
        next_action=routing.get("next_action"),
        key_resources=key_resources,
        key_forms=routing.get("key_forms", []),
        notes=routing.get("notes", []),
        questions=[],
        audit=audit,
    )
