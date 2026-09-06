"""
women_veterans_router.py
SQUAD BAT — Women Veterans Division module entry point.
"""

from __future__ import annotations

import sys
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

_LOGIC_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'AGENTS', 'LOGIC')
if _LOGIC_PATH not in sys.path:
    sys.path.insert(0, _LOGIC_PATH)

from WomenVeterans_v0_1 import WomenVetProfile, route_women_veterans  # type: ignore


VALID_NEEDS = {
    "healthcare", "maternity", "mst", "mental_health", "reproductive_health",
    "housing", "childcare", "peer_support", "benefits_help"
}
VALID_DISCHARGE = {"honorable", "general", "other_than_honorable", "dishonorable", "unknown"}

# Found via a top-down audit: this router validated and read a field named
# "housing_situation" against {"stable","at_risk","homeless","unknown"} --
# but questionnaire_intake_bridge_v1.py (the actual real-intake path) has
# never sent that field name at all. It sends "housing_status", with values
# unhoused/unstable/at_risk/stable/unknown (see that module's own
# _map_housing_status) -- every other division's router (housing_router.py
# included) already reads exactly that field/vocabulary. Confirmed directly:
# on real bridge-built intake, payload.get("housing_situation", "") is always
# "" (key never present), so _validate()'s housing check silently no-opped
# and _build_profile() always fell back to housing_situation="unknown" --
# regardless of what the veteran actually answered. WomenVeterans_v0_1.py's
# own Track 6 (Housing/Homeless), specifically reordered ahead of Track 1 in
# an earlier fix because a housing crisis must take priority, keys directly
# off profile.housing_situation in ("homeless", "at_risk") -- unreachable
# from real intake data for as long as this mismatch existed. No existing
# test caught this because tests/test_women_veterans.py constructs
# WomenVetProfile directly, bypassing this router (and its field-name bug)
# entirely.
VALID_HOUSING_STATUS = {"unhoused", "unstable", "at_risk", "stable", "unknown"}

# Translates the bridge's shared vocabulary into WomenVeterans_v0_1.py's own
# internal one (which predates the bridge and was never reconciled with it).
# "unhoused" -> "homeless" is a direct semantic match. "unstable" has no
# exact equivalent in the internal vocabulary; "at_risk" is the closest
# available bucket -- same kind of documented approximation the bridge
# itself already makes for other fields, not a silent guess.
_HOUSING_STATUS_TO_INTERNAL = {
    "unhoused": "homeless",
    "unstable": "at_risk",
    "at_risk": "at_risk",
    "stable": "stable",
    "unknown": "unknown",
}


def _map_housing_status(raw: str) -> str:
    return _HOUSING_STATUS_TO_INTERNAL.get(raw, "unknown")


@dataclass(frozen=True)
class WomenVeteransResult:
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

    needs = payload.get("needs", [])
    if needs and not isinstance(needs, list):
        errors.append("needs must be a list of strings.")
    else:
        for n in (needs or []):
            if n not in VALID_NEEDS:
                errors.append(f"Invalid need '{n}'. Valid: {sorted(VALID_NEEDS)}")

    discharge_raw = payload.get("discharge", "")
    discharge = discharge_raw[0] if isinstance(discharge_raw, list) else discharge_raw
    if discharge and discharge not in VALID_DISCHARGE:
        errors.append(f"Invalid discharge '{discharge}'. Valid: {sorted(VALID_DISCHARGE)}")

    housing = payload.get("housing_status", "")
    if housing and housing not in VALID_HOUSING_STATUS:
        errors.append(f"Invalid housing_status '{housing}'. Valid: {sorted(VALID_HOUSING_STATUS)}")

    rating = payload.get("disability_rating")
    if rating is not None:
        try:
            r = int(rating)
            if not (0 <= r <= 100):
                errors.append("disability_rating must be 0–100.")
        except (ValueError, TypeError):
            errors.append("disability_rating must be a number.")

    return errors


def _build_profile(payload: Dict[str, Any]) -> WomenVetProfile:
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

    return WomenVetProfile(
        needs=_list("needs"),
        enrolled_va_healthcare=_bool("enrolled_va_healthcare"),
        is_pregnant=_bool("is_pregnant"),
        has_young_children=_bool("has_young_children"),
        has_mst=_bool("has_mst"),
        has_ptsd=_bool("has_ptsd"),
        has_depression_anxiety=_bool("has_depression_anxiety"),
        housing_situation=_map_housing_status(payload.get("housing_status", "unknown")),
        disability_rating=_int_or_none("disability_rating"),
        discharge=(lambda v: v[0] if isinstance(v, list) else v)(payload.get("discharge", "unknown")),
        state=payload.get("state", ""),
        county=payload.get("county", ""),
    )


def run(payload: Dict[str, Any]) -> WomenVeteransResult:
    audit: Dict[str, Any] = {
        "module": "WOMEN_VETERANS",
        "version": "0.1.0",
        "input_keys": sorted(payload.keys()),
    }

    errors = _validate(payload)
    if errors:
        return WomenVeteransResult(
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
        routing = route_women_veterans(profile)
    except Exception as exc:
        return WomenVeteransResult(
            status="FAILED_CLOSED",
            primary_path=None,
            secondary_options=[],
            flags=["routing_exception"],
            next_action="Call the Women Veterans Call Center: 1-855-829-6636.",
            key_resources=["Women Veterans Call Center — 1-855-829-6636"],
            key_forms=[],
            notes=[str(exc)],
            questions=[],
            audit={**audit, "exception": str(exc)},
        )

    return WomenVeteransResult(
        status="OK",
        primary_path=routing.get("primary_path"),
        secondary_options=routing.get("secondary_options", []),
        flags=routing.get("flags", []),
        next_action=routing.get("next_action"),
        key_resources=routing.get("key_resources", []),
        key_forms=routing.get("key_forms", []),
        notes=routing.get("notes", []),
        questions=[],
        audit=audit,
    )
