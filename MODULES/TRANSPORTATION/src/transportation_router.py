"""
transportation_router.py
SQUAD BAT — Transportation Division module entry point.
"""

from __future__ import annotations

import sys
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

_LOGIC_PATH = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'AGENTS', 'LOGIC')
if _LOGIC_PATH not in sys.path:
    sys.path.insert(0, _LOGIC_PATH)

from Transportation_v0_1 import VetTransportProfile, route_transportation  # type: ignore


VALID_TRANSPORT_NEEDS = {"va_appointment", "adaptive_vehicle", "rural", "daily_transit", "crisis", "relocation"}


@dataclass(frozen=True)
class TransportationResult:
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

    needs = payload.get("transport_needs", [])
    if needs and not isinstance(needs, list):
        errors.append("transport_needs must be a list of strings.")
    else:
        for n in (needs or []):
            if n not in VALID_TRANSPORT_NEEDS:
                errors.append(f"Invalid transport_need '{n}'. Valid: {sorted(VALID_TRANSPORT_NEEDS)}")

    rating = payload.get("disability_rating")
    if rating is not None:
        try:
            r = int(rating)
            if not (0 <= r <= 100):
                errors.append("disability_rating must be 0–100.")
        except (ValueError, TypeError):
            errors.append("disability_rating must be a number.")

    return errors


def _build_profile(payload: Dict[str, Any]) -> VetTransportProfile:
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

    return VetTransportProfile(
        transport_needs=_list("transport_needs"),
        has_sc_disability=_bool("has_sc_disability"),
        disability_rating=_int_or_none("disability_rating"),
        enrolled_va_healthcare=_bool("enrolled_va_healthcare"),
        is_rural=_bool("is_rural"),
        has_vehicle=bool(payload.get("has_vehicle", True)),
        can_drive=bool(payload.get("can_drive", True)),
        needs_adaptive_vehicle=_bool("needs_adaptive_vehicle"),
        state=payload.get("state", ""),
        county=payload.get("county", ""),
    )


def run(payload: Dict[str, Any]) -> TransportationResult:
    """
    Module entrypoint. No required fields — every veteran gets a path.
    """
    audit: Dict[str, Any] = {
        "module": "TRANSPORTATION",
        "version": "0.1.0",
        "input_keys": sorted(payload.keys()),
    }

    errors = _validate(payload)
    if errors:
        return TransportationResult(
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
        routing = route_transportation(profile)
    except Exception as exc:
        return TransportationResult(
            status="FAILED_CLOSED",
            primary_path=None,
            secondary_options=[],
            flags=["routing_exception"],
            next_action="Call 211 for local transport resources or contact your VA social worker.",
            key_resources=["211.org", "DAV — dav.org/find-a-chapter"],
            key_forms=[],
            notes=[str(exc)],
            questions=[],
            audit={**audit, "exception": str(exc)},
        )

    return TransportationResult(
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
