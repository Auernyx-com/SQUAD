"""
med_disability_router.py
SQUAD BAT — Medical & Disability Division module entry point.

Wraps MedDisability_v0.1.py routing logic with standard module interface.
Accepts a dict payload, validates required fields, and returns a structured result.
"""

from __future__ import annotations

import sys
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

# Allow import from AGENTS/LOGIC without install
_LOGIC_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'AGENTS', 'LOGIC')
if _LOGIC_PATH not in sys.path:
    sys.path.insert(0, _LOGIC_PATH)

from MedDisability_v0_1 import VetMedProfile, route_med_disability  # type: ignore


REQUIRED_FIELDS = {"va_status", "discharge"}

VALID_VA_STATUS = {"not_enrolled", "enrolled_no_rating", "has_rating", "100_percent_PT"}
VALID_DISCHARGE = {"honorable", "general", "other_than_honorable", "dishonorable", "unknown"}


@dataclass(frozen=True)
class MedDisabilityResult:
    status: str                    # OK | NEEDS_INPUT | FAILED_CLOSED
    primary_path: Optional[str]
    secondary_options: List[str]
    flags: List[str]
    next_action: Optional[str]
    key_forms: List[str]
    notes: List[str]
    questions: List[str]           # populated when NEEDS_INPUT
    audit: Dict[str, Any]


def _validate(payload: Dict[str, Any]) -> List[str]:
    """Returns list of validation errors. Empty = OK."""
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in payload or not payload[field]:
            errors.append(f"Missing required field: {field}")

    va_status = payload.get("va_status", "")
    if va_status and va_status not in VALID_VA_STATUS:
        errors.append(f"Invalid va_status '{va_status}'. Valid: {sorted(VALID_VA_STATUS)}")

    discharge = payload.get("discharge", "")
    if discharge and discharge not in VALID_DISCHARGE:
        errors.append(f"Invalid discharge '{discharge}'. Valid: {sorted(VALID_DISCHARGE)}")

    rating = payload.get("disability_rating")
    if rating is not None:
        try:
            r = int(rating)
            if not (0 <= r <= 100):
                errors.append("disability_rating must be 0–100.")
        except (ValueError, TypeError):
            errors.append("disability_rating must be a number.")

    return errors


def _build_profile(payload: Dict[str, Any]) -> VetMedProfile:
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

    return VetMedProfile(
        va_status=payload.get("va_status", ""),
        discharge=payload.get("discharge", "unknown"),
        disability_rating=_int_or_none("disability_rating"),
        need_branches=_list("need_branches"),
        recent_denial=_bool("recent_denial"),
        has_new_evidence=_bool("has_new_evidence"),
        unemployable=_bool("unemployable"),
        caregiver_need=_bool("caregiver_need"),
        ptsd=_bool("ptsd"),
        tbi=_bool("tbi"),
        mst=_bool("mst"),
        location=str(payload.get("location", "")),
        permanent_total=_bool("permanent_total"),
        has_dependents=_bool("has_dependents"),
    )


def route(payload: Dict[str, Any]) -> MedDisabilityResult:
    """
    Main module entry point.
    payload: dict matching intake fields defined in module.json
    Returns MedDisabilityResult.
    """
    if not isinstance(payload, dict):
        return MedDisabilityResult(
            status="FAILED_CLOSED",
            primary_path=None,
            secondary_options=[],
            flags=["invalid_payload"],
            next_action=None,
            key_forms=[],
            notes=[],
            questions=[],
            audit={"error": "payload must be a dict"},
        )

    errors = _validate(payload)
    if errors:
        questions = []
        if any("va_status" in e for e in errors):
            questions.append("Are you currently enrolled in VA healthcare? (yes / no / not sure)")
        if any("discharge" in e for e in errors):
            questions.append("What type of discharge did you receive? (honorable / general / other than honorable / dishonorable / not sure)")
        return MedDisabilityResult(
            status="NEEDS_INPUT",
            primary_path=None,
            secondary_options=[],
            flags=["incomplete_intake"],
            next_action="Collect missing intake fields before routing.",
            key_forms=[],
            notes=errors,
            questions=questions,
            audit={"validation_errors": errors},
        )

    profile = _build_profile(payload)
    routing = route_med_disability(profile)

    return MedDisabilityResult(
        status="OK",
        primary_path=routing.get("primary_path"),
        secondary_options=routing.get("secondary_options", []),
        flags=routing.get("flags", []),
        next_action=routing.get("next_action"),
        key_forms=routing.get("key_forms", []),
        notes=routing.get("notes", []),
        questions=[],
        audit={
            "va_status": profile.va_status,
            "discharge": profile.discharge,
            "disability_rating": profile.disability_rating,
            "need_branches": profile.need_branches,
            "flags_triggered": routing.get("flags", []),
        },
    )


def route_to_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Convenience wrapper — returns plain dict instead of dataclass."""
    r = route(payload)
    return {
        "status": r.status,
        "primary_path": r.primary_path,
        "secondary_options": r.secondary_options,
        "flags": r.flags,
        "next_action": r.next_action,
        "key_forms": r.key_forms,
        "notes": r.notes,
        "questions": r.questions,
        "audit": r.audit,
    }
