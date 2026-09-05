from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


NEED_BRANCHES = {"housing", "claims", "crisis", "legal", "education"}
HOUSING_STATUS = {"housed", "unhoused", "unstable", "unknown"}
CLAIM_STAGE = {"not_filed", "filed", "in_progress", "appeal", "unknown"}
EMPLOYMENT_STATUS = {"employed", "unemployed", "unknown"}
CONTACT_PREFS = {"phone", "email", "in_person"}
URGENCY = {"low", "med", "high"}


def _norm(s: Any) -> Optional[str]:
    if not isinstance(s, str):
        return None
    t = s.strip()
    return t if t else None


def _norm_lower(s: Any) -> Optional[str]:
    v = _norm(s)
    return v.lower() if v else None


def _ensure_list(x: Any) -> List[Any]:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


@dataclass(frozen=True)
class IntakeGateResult:
    status: str  # NEEDS_INPUT | OK
    questions: List[str]
    normalized: Dict[str, Any]


def gate_intake(payload: Dict[str, Any]) -> IntakeGateResult:
    """Do-not-guess intake gate.

    If required basics are missing, returns NEEDS_INPUT + questions only.
    Otherwise returns OK + normalized fields.
    """

    p = payload or {}

    # `.get("location", {})` only falls back to {} when the key is ABSENT --
    # a payload with "location": null (a plausible shape from an intake form
    # that serializes an unfilled object as JSON null) has the key present
    # with value None, so .get("location", {}) returns None and the next
    # .get("state") crashes with AttributeError. A non-dict value (e.g. a
    # stray string) crashes the same way. This module's entire purpose is
    # asking a clarifying question instead of failing, so it must not crash
    # on exactly the kind of incomplete/malformed input it exists to handle.
    # Confirmed against the pre-fix code: {"location": None, ...} and
    # {"location": "somewhere", ...} both raised AttributeError instead of
    # returning NEEDS_INPUT asking for state/county. Matches the isinstance
    # guard already used for `constraints` below.
    location = p.get("location") if isinstance(p.get("location"), dict) else {}
    state = _norm_upper_state(p.get("state") or location.get("state"))
    county = _norm(p.get("county") or location.get("county"))

    needs_raw = _ensure_list(p.get("need") or p.get("needs") or p.get("need_branch") or p.get("need_branches"))
    needs: List[str] = []
    for n in needs_raw:
        nn = _norm_lower(n)
        if nn and nn in NEED_BRANCHES and nn not in needs:
            needs.append(nn)
    if len(needs) > 2:
        needs = needs[:2]

    # Same non-dict-value gap as `location` above: `(p.get("status") or {})`
    # protects against None/falsy but a truthy non-dict value (a stray
    # string) still crashes on the following .get(). Confirmed against the
    # pre-fix code: {"status": "weird_string", ...} raised AttributeError.
    status_block = p.get("status") if isinstance(p.get("status"), dict) else {}
    housing_status = _norm_lower(p.get("housing_status") or status_block.get("housing"))
    claim_stage = _norm_lower(p.get("claim_stage") or status_block.get("claim"))
    employment_status = _norm_lower(p.get("employment_status") or status_block.get("employment"))

    contact_pref = _norm_lower(p.get("contact_preference") or p.get("contact_pref"))

    urgency = _norm_lower(p.get("urgency"))
    if urgency not in URGENCY:
        urgency = None

    constraints = p.get("constraints") if isinstance(p.get("constraints"), dict) else {}

    questions: List[str] = []

    # Location
    if not state:
        questions.append("What state are you in? (2-letter code, e.g., CO)")
    if not county:
        questions.append("What county are you in? (e.g., Mesa)")

    # Need branch
    if not needs:
        questions.append("Which need type is this? Pick 1–2: housing, claims, crisis, legal, education")

    # Status
    if housing_status not in HOUSING_STATUS:
        questions.append("Current housing status? (housed / unhoused / unstable)")
    if claim_stage not in CLAIM_STAGE:
        questions.append("Claim stage? (not_filed / filed / in_progress / appeal)")
    if employment_status not in EMPLOYMENT_STATUS:
        questions.append("Employment status? (employed / unemployed)")

    # Contact preference
    if contact_pref not in CONTACT_PREFS:
        questions.append("Contact preference? (phone / email / in_person)")

    if questions:
        return IntakeGateResult(status="NEEDS_INPUT", questions=questions, normalized={})

    normalized = {
        "location": {"state": state, "county": county},
        "needs": needs,
        "status": {
            "housing_status": housing_status,
            "claim_stage": claim_stage,
            "employment_status": employment_status,
        },
        "contact_preference": contact_pref,
        "urgency": urgency or "low",
        "constraints": constraints,
    }

    return IntakeGateResult(status="OK", questions=[], normalized=normalized)


def _norm_upper_state(value: Any) -> Optional[str]:
    s = _norm(value)
    if not s:
        return None
    s2 = s.strip().upper()
    if len(s2) != 2:
        return None
    if not s2.isalpha():
        return None
    return s2
