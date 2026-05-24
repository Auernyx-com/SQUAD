"""
legal_router.py
SQUAD BAT — Legal Division module entry point.

Wraps Legal_v0_1.py routing logic with standard module interface.
"""

from __future__ import annotations

import sys
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

_LOGIC_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'AGENTS', 'LOGIC')
if _LOGIC_PATH not in sys.path:
    sys.path.insert(0, _LOGIC_PATH)

from Legal_v0_1 import VetLegalProfile, route_legal  # type: ignore


VALID_LEGAL_NEEDS = {
    "discharge_upgrade", "va_appeal", "mst", "civilian_legal",
    "records_correction", "predatory_lending", "benefits_denial"
}
VALID_DISCHARGE = {"honorable", "general", "other_than_honorable", "dishonorable", "unknown"}
VALID_APPEALS_LANE = {"none", "hlr", "supplemental", "bva", "cavc", "unknown"}
VALID_CIVILIAN_ISSUE = {"housing", "employment", "family", "consumer", "criminal_record", "other", ""}


@dataclass(frozen=True)
class LegalResult:
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

    needs = payload.get("legal_needs", [])
    if needs and not isinstance(needs, list):
        errors.append("legal_needs must be a list of strings.")
    else:
        for n in (needs or []):
            if n not in VALID_LEGAL_NEEDS:
                errors.append(f"Invalid legal_need '{n}'. Valid: {sorted(VALID_LEGAL_NEEDS)}")

    discharge = payload.get("discharge", "")
    if discharge and discharge not in VALID_DISCHARGE:
        errors.append(f"Invalid discharge '{discharge}'. Valid: {sorted(VALID_DISCHARGE)}")

    lane = payload.get("appeals_lane", "")
    if lane and lane not in VALID_APPEALS_LANE:
        errors.append(f"Invalid appeals_lane '{lane}'. Valid: {sorted(VALID_APPEALS_LANE)}")

    issue = payload.get("civilian_issue", "")
    if issue and issue not in VALID_CIVILIAN_ISSUE:
        errors.append(f"Invalid civilian_issue '{issue}'. Valid: {sorted(VALID_CIVILIAN_ISSUE)}")

    years = payload.get("years_since_discharge")
    if years is not None:
        try:
            int(years)
        except (ValueError, TypeError):
            errors.append("years_since_discharge must be a number.")

    return errors


def _build_profile(payload: Dict[str, Any]) -> VetLegalProfile:
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

    return VetLegalProfile(
        legal_needs=_list("legal_needs"),
        discharge=payload.get("discharge", "unknown"),
        years_since_discharge=_int_or_none("years_since_discharge"),
        branch=payload.get("branch", "unknown"),
        has_denied_claim=_bool("has_denied_claim"),
        appeals_lane=payload.get("appeals_lane", "none"),
        has_mst=_bool("has_mst"),
        civilian_issue=payload.get("civilian_issue", ""),
        has_ucmj_history=_bool("has_ucmj_history"),
        state=payload.get("state", ""),
        county=payload.get("county", ""),
    )


def run(payload: Dict[str, Any]) -> LegalResult:
    """
    Module entrypoint. No required fields — every veteran gets a path.

    Optional fields:
        legal_needs (list), discharge (str), years_since_discharge (int),
        branch (str), has_denied_claim (bool), appeals_lane (str),
        has_mst (bool), civilian_issue (str), has_ucmj_history (bool),
        state (str), county (str)
    """
    audit: Dict[str, Any] = {
        "module": "LEGAL",
        "version": "0.1.0",
        "input_keys": sorted(payload.keys()),
    }

    errors = _validate(payload)
    if errors:
        return LegalResult(
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
        routing = route_legal(profile)
    except Exception as exc:
        return LegalResult(
            status="FAILED_CLOSED",
            primary_path=None,
            secondary_options=[],
            flags=["routing_exception"],
            next_action="Contact NVLSP at nvlsp.org or call 211 for local legal aid.",
            key_resources=["NVLSP — nvlsp.org", "211.org"],
            key_forms=[],
            notes=[str(exc)],
            questions=[],
            audit={**audit, "exception": str(exc)},
        )

    return LegalResult(
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
