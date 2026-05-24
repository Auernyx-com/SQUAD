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
VALID_HOUSING = {"stable", "at_risk", "homeless", "unknown"}


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

    discharge = payload.get("discharge", "")
    if discharge and discharge not in VALID_DISCHARGE:
        errors.append(f"Invalid discharge '{discharge}'. Valid: {sorted(VALID_DISCHARGE)}")

    housing = payload.get("housing_situation", "")
    if housing and housing not in VALID_HOUSING:
        errors.append(f"Invalid housing_situation '{housing}'. Valid: {sorted(VALID_HOUSING)}")

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
        housing_situation=payload.get("housing_situation", "unknown"),
        disability_rating=_int_or_none("disability_rating"),
        discharge=payload.get("discharge", "unknown"),
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
