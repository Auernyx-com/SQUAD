"""
toxic_exposure_router.py
SQUAD BAT — Toxic Exposure Division module entry point.
"""

from __future__ import annotations

import sys
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

_LOGIC_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'AGENTS', 'LOGIC')
if _LOGIC_PATH not in sys.path:
    sys.path.insert(0, _LOGIC_PATH)

from ToxicExposure_v0_1 import ToxicExposureProfile, route_toxic_exposure  # type: ignore


VALID_EXPOSURE_TYPES = {
    "burn_pit", "agent_orange", "camp_lejeune",
    "gulf_war_syndrome", "radiation", "pfas", "unknown"
}
VALID_ERA = {
    "post_9_11", "gulf_war", "vietnam", "korea",
    "cold_war", "wwii", "unknown"
}
VALID_CONDITIONS = {
    "respiratory", "cancer", "neurological", "gi", "chronic_fatigue",
    "skin", "cardiac", "reproductive", "undiagnosed", "none_yet"
}
VALID_DISCHARGE = {"honorable", "general", "other_than_honorable", "dishonorable", "unknown"}


@dataclass(frozen=True)
class ToxicExposureResult:
    status: str
    primary_path: Optional[str]
    secondary_options: List[str]
    flags: List[str]
    next_action: Optional[str]
    key_resources: List[str]
    key_forms: List[str]
    notes: List[str]
    presumptive_conditions: List[str]
    questions: List[str]
    audit: Dict[str, Any]


def _validate(payload: Dict[str, Any]) -> List[str]:
    errors = []

    for field_name, valid_set in [
        ("exposure_types", VALID_EXPOSURE_TYPES),
        ("conditions", VALID_CONDITIONS),
    ]:
        vals = payload.get(field_name, [])
        if vals and not isinstance(vals, list):
            errors.append(f"{field_name} must be a list.")
        else:
            for v in (vals or []):
                if v not in valid_set:
                    errors.append(f"Invalid {field_name} value '{v}'. Valid: {sorted(valid_set)}")

    era = payload.get("era", "")
    if era and era not in VALID_ERA:
        errors.append(f"Invalid era '{era}'. Valid: {sorted(VALID_ERA)}")

    discharge = payload.get("discharge", "")
    if discharge and discharge not in VALID_DISCHARGE:
        errors.append(f"Invalid discharge '{discharge}'. Valid: {sorted(VALID_DISCHARGE)}")

    return errors


def _build_profile(payload: Dict[str, Any]) -> ToxicExposureProfile:
    def _bool(key: str) -> bool:
        return bool(payload.get(key, False))

    def _list(key: str) -> List[str]:
        val = payload.get(key, [])
        return val if isinstance(val, list) else []

    return ToxicExposureProfile(
        exposure_types=_list("exposure_types"),
        era=payload.get("era", "unknown"),
        locations_served=_list("locations_served"),
        conditions=_list("conditions"),
        camp_lejeune=_bool("camp_lejeune"),
        is_lejeune_family_member=_bool("is_lejeune_family_member"),
        has_existing_claim=_bool("has_existing_claim"),
        was_previously_denied=_bool("was_previously_denied"),
        enrolled_va_healthcare=_bool("enrolled_va_healthcare"),
        discharge=payload.get("discharge", "unknown"),
        state=payload.get("state", ""),
        county=payload.get("county", ""),
    )


def run(payload: Dict[str, Any]) -> ToxicExposureResult:
    """
    Module entrypoint. No required fields — every veteran gets a path.
    """
    audit: Dict[str, Any] = {
        "module": "TOXIC_EXPOSURE",
        "version": "0.1.0",
        "input_keys": sorted(payload.keys()),
    }

    errors = _validate(payload)
    if errors:
        return ToxicExposureResult(
            status="NEEDS_INPUT",
            primary_path=None,
            secondary_options=[],
            flags=["validation_error"],
            next_action=None,
            key_resources=[],
            key_forms=[],
            notes=[],
            presumptive_conditions=[],
            questions=errors,
            audit={**audit, "errors": errors},
        )

    try:
        profile = _build_profile(payload)
        routing = route_toxic_exposure(profile)
    except Exception as exc:
        return ToxicExposureResult(
            status="FAILED_CLOSED",
            primary_path=None,
            secondary_options=[],
            flags=["routing_exception"],
            next_action="Call 1-800-827-1000 and ask about PACT Act eligibility and the Burn Pit Registry.",
            key_resources=[
                "PACT Act — va.gov/pact-act-information",
                "Burn Pits 360 — burnpits360.org",
            ],
            key_forms=[],
            notes=[str(exc)],
            presumptive_conditions=[],
            questions=[],
            audit={**audit, "exception": str(exc)},
        )

    return ToxicExposureResult(
        status="OK",
        primary_path=routing.get("primary_path"),
        secondary_options=routing.get("secondary_options", []),
        flags=routing.get("flags", []),
        next_action=routing.get("next_action"),
        key_resources=routing.get("key_resources", []),
        key_forms=routing.get("key_forms", []),
        notes=routing.get("notes", []),
        presumptive_conditions=routing.get("presumptive_conditions", []),
        questions=[],
        audit=audit,
    )
