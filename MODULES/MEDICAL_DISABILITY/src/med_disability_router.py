"""
med_disability_router.py
SQUAD BAT — Medical & Disability Division module entry point.

Wraps MedDisability_v0.1.py routing logic with standard module interface.
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

from MedDisability_v0_1 import VetMedProfile, route_med_disability  # type: ignore
from local_resources import find_local_resources, format_local_resource_line  # type: ignore


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
    # Added for local-resource lookup wiring -- see the identical comment
    # in va_benefits_router.py's VaBenefitsResult for the full reasoning:
    # secondary_options gets truncated to [:3] by
    # pf_coordinator_v1.py's invoke_division() when building next_actions,
    # and every real intake already has 3+ items there before any local
    # match -- confirmed directly that a real Mesa County match never
    # reached the coordinator's actual output as a result. key_resources
    # is not truncated. Defaulted so no existing construction here needs
    # to change.
    key_resources: List[str] = field(default_factory=list)


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


def _local_resource_tags(flags: List[str]) -> List[str]:
    """Service tags to search for, driven by the flags route_med_disability()
    already computed."""
    tags = ["claims_assistance", "benefits_navigation"]

    if any(f in flags for f in ("mst_flagged", "ptsd_flagged", "tbi_flagged")):
        tags.append("mental_health")

    if "pcafc_candidate" in flags:
        tags.append("caregiver_support")

    return tags


def _is_crisis(flags: List[str]) -> bool:
    # mst_flagged/ptsd_flagged/tbi_flagged are exactly the "health and
    # welfare or self-harm concern" case the crisis-widened mental_health
    # branch (GOVERNANCE/auernyx.nonprofit.scope.json's
    # crisis_widened_branches) was built for -- the clearest, most directly
    # applicable use of that widening across all 8 Divisions.
    return any(f in flags for f in ("mst_flagged", "ptsd_flagged", "tbi_flagged"))


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

    # VetMedProfile has a single "location" field, but nothing in
    # route_med_disability() actually reads it (confirmed by grep -- no
    # Track references profile.location at all), and the real bridge never
    # sends a flat "location" string anyway (it sends separate "state"/
    # "county" keys) -- so that field has always been a no-op, not
    # something to route local-resource lookups through. Reading
    # state/county straight off payload instead, matching how every other
    # Division's own local-resource wiring already does it.
    result_flags = routing.get("flags", [])
    local = find_local_resources(
        state=payload.get("state", ""),
        county=payload.get("county", ""),
        service_tags=_local_resource_tags(result_flags),
        crisis_or_self_harm=_is_crisis(result_flags),
    )
    key_resources = [format_local_resource_line(r) for r in local]

    return MedDisabilityResult(
        status="OK",
        primary_path=routing.get("primary_path"),
        secondary_options=routing.get("secondary_options", []),
        flags=result_flags,
        next_action=routing.get("next_action"),
        key_forms=routing.get("key_forms", []),
        key_resources=key_resources,
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
        "key_resources": r.key_resources,
        "notes": r.notes,
        "questions": r.questions,
        "audit": r.audit,
    }


# The Pathfinder coordinator (AGENTS/CORE/PATHFINDER/pf_coordinator_v1.py)
# dynamically loads each Division's entry module and calls mod.run(intake) —
# every other wired Division (housing, legal, transportation, women_veterans,
# toxic_exposure) exposes exactly that name. This module only ever exposed
# route()/route_to_dict(), so even with config/divisions.json pointed at this
# file, invoke_division()'s `hasattr(mod, "run")` check would still fail and
# the coordinator would report this Division SKIPPED — "no run() entrypoint"
# — for every intake touching MEDICAL, CLAIMS, or MENTAL_HEALTH. Verified
# directly: this was the actual reason medical-disability-division's entry
# was still empty in divisions.json alongside two other complete, working
# routers.
run = route
