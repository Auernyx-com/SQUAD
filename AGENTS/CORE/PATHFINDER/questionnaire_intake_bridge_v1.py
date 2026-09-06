"""
questionnaire_intake_bridge_v1.py
SQUAD BAT — translates a real wyerd-squad questionnaire submission
(tool/index.html's `intake` object, as sent to pathfinder-worker's /process)
into a valid Pathfinder Coordinator intake (pf_coordinator_v1.run_coordinator).

Why this exists
----------------
Found via a top-down review, verified directly against both codebases: the
questionnaire and the coordinator/division routers were built independently
and use completely incompatible vocabularies for almost every shared field.
None of this is in KNOWN_GAPS.md. Confirmed concretely, not assumed:

  - discharge: questionnaire sends general_uhc/oth/bcd/entry_level/medical;
    every division router's VALID_DISCHARGE only accepts
    honorable/general/other_than_honorable/dishonorable/unknown. A veteran
    selecting OTH or Bad Conduct Discharge — the population Fail-Closed
    Design Law #4 explicitly names as needing the most careful handling —
    would fail router validation outright without this bridge.
  - era: questionnaire sends a MULTI-select array including post_911 (no
    underscore); the router expects a SINGLE value post_9_11 (underscore).
  - disability_rating: questionnaire sends string range buckets (0_20,
    70_90, tdiu); the router requires an integer 0-100 used in real
    threshold checks (verified: AGENTS/LOGIC/VaBenefits_v0_1.py gates a VR&E
    recommendation on `rating >= 10`). A naive midpoint guess for "0_20"
    (e.g. 10) would cross that threshold and falsely recommend VR&E to a
    veteran who may actually be at 0%. Same pattern confirmed for
    income_monthly (a pension eligibility check gates on `< 2000`).
  - housing_status: questionnaire's granular options (unsheltered/car/
    shelter/couch/unstable_housed/stable) don't match the router's
    VALID_HOUSING_STATUS (unhoused/unstable/at_risk/stable/unknown) at all.
  - need (housing/medical/claims/...) needs mapping to the coordinator's
    domain vocabulary (HOUSING/MEDICAL/CLAIMS/...) — and "crisis" is a need
    option but not a routable domain; it maps to the coordinator's separate
    crisis.flagged mechanism instead.
  - urgency: questionnaire sends tonight/days/weeks/planning; the formal
    schema's constraints.urgency wants IMMEDIATE/HIGH/STANDARD, but the
    coordinator's OWN inline edge-case check reads a *different*, lowercase,
    non-namespaced `urgency` field ("high") — an inconsistency inside
    pf_coordinator_v1.py itself, not introduced here. Both forms are set so
    either code path sees a consistent signal.

Design principle for every range/bucket value below: when a threshold check
in the actual routing logic is directional (>= for disability_rating, < for
income), map to whichever bound of the selected range can NEVER falsely
claim the veteran clears (or misses) that threshold. Guessing a midpoint
would be exactly the kind of unverified inference this project's own
"never guess, never present a guess as fact" design law exists to prevent.

Known, documented limitations of this bridge (not silently smoothed over):
  - discharge values bcd, entry_level, and medical have no clean equivalent
    in the routers' VALID_DISCHARGE set. bcd and entry_level are mapped to
    the closest functional analog (documented below); medical is passed
    through UNCHANGED on purpose, because pf_coordinator_v1.py's own
    MEDICAL_RETIREMENT_VA_DISPUTE edge-case check already treats
    discharge == "medical" as a real, expected value — remapping it would
    break that check. A router seeing "medical" will correctly return
    NEEDS_INPUT (a real, human-reviewable question) rather than silently
    misroute; that is the intended behavior, not a fallback failure.
  - The questionnaire's "need" options have no transportation or
    women-veterans choice at all — those two Divisions (both wired and
    working) are currently unreachable from the real intake flow. This
    bridge cannot fix that; it's a frontend content gap, not a data-mapping
    one. Flagged separately, not addressed here.
  - This bridge is Python calling Python within this repo. It does not
    change what pathfinder-worker (a Cloudflare Worker — cannot execute
    Python at all) does in production today. See the accompanying commit
    message / project memory for that separate, larger gap.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_FOUNDING_LAW_SHA256 = "dc0fcb428e24948c5471798bf3c0b77cafade1c68e1aecb39aa13eef264f2f87"
_INTAKE_SCHEMA = "squad-bat.coordinator-intake.v1"

# ---------------------------------------------------------------------------
# discharge
# ---------------------------------------------------------------------------

_DISCHARGE_MAP: Dict[str, str] = {
    "honorable": "honorable",
    "general_uhc": "general",
    "oth": "other_than_honorable",
    # No clean equivalent in VALID_DISCHARGE. BCD is punitive (court-martial)
    # but, per the questionnaire's own description, "not zero" access —
    # functionally closest to other_than_honorable's "significantly limits,
    # not zero" framing. Documented approximation, not an exact match.
    "bcd": "other_than_honorable",
    "dishonorable": "dishonorable",
    # Administrative, non-punitive separation under 180 days — closer to
    # "general" than to any punitive category. Documented approximation.
    "entry_level": "general",
    # Deliberately NOT remapped — see module docstring.
    "medical": "medical",
    "unknown": "unknown",
}


def _map_discharge(raw: Optional[str]) -> str:
    if not raw:
        return "unknown"
    return _DISCHARGE_MAP.get(raw, "unknown")


# ---------------------------------------------------------------------------
# era — questionnaire sends a multi-select array; router wants one value.
# ---------------------------------------------------------------------------

# Priority order: most specific / most consequential first (post-9/11 and
# Gulf War unlock PACT Act framing elsewhere in the routing logic).
_ERA_PRIORITY = ["post_911", "gulf_war", "vietnam", "korea", "cold_war"]

_ERA_MAP: Dict[str, str] = {
    "post_911": "post_9_11",  # fixes the underscore drift
    "gulf_war": "gulf_war",
    "vietnam": "vietnam",
    "korea": "korea",
    # No VALID_ERA bucket fits 1975-1990 cleanly. "peacetime" is the closest
    # available category; documented approximation, not an exact match.
    "cold_war": "peacetime",
    # No VALID_ERA bucket at all for WWII specifically.
}


def _map_era(raw_list: Any) -> str:
    if not isinstance(raw_list, list):
        return "unknown"
    for candidate in _ERA_PRIORITY:
        if candidate in raw_list:
            return _ERA_MAP[candidate]
    return "unknown"


def _era_includes_transitioning(raw_list: Any) -> bool:
    return isinstance(raw_list, list) and "transitioning" in raw_list


# ---------------------------------------------------------------------------
# disability_rating — range bucket -> integer, conservative (lower) bound.
# Router logic gates on `rating >= N`; using the lower bound of the selected
# range guarantees we never claim a threshold the veteran might not clear.
# ---------------------------------------------------------------------------

_DISABILITY_RATING_MAP: Dict[str, Optional[int]] = {
    "none": 0,
    "pending": None,  # no current rating — genuinely unknown, not zero
    "0_20": 0,
    "30_60": 30,
    "70_90": 70,
    "100": 100,
    "tdiu": 100,  # "paid at 100% rate" per the questionnaire's own description
    "denied": 0,
}


def _map_disability_rating(raw: Optional[str]) -> Optional[int]:
    if not raw:
        return None
    return _DISABILITY_RATING_MAP.get(raw)


# ---------------------------------------------------------------------------
# income — range bucket -> integer, conservative (upper) bound.
# Router logic gates on `income_monthly < 2000` (pension check); using the
# upper bound of the selected range guarantees we never claim the veteran is
# below a threshold they might actually be above.
# ---------------------------------------------------------------------------

_INCOME_MAP: Dict[str, Optional[int]] = {
    "none": 0,
    "under_500": 499,
    "500_1000": 1000,
    "1000_2000": 2000,
    "over_2000": 2001,  # only needs to clearly clear the one known `< 2000` gate
}


def _map_income(raw: Optional[str]) -> Optional[int]:
    if not raw:
        return None
    return _INCOME_MAP.get(raw)


# ---------------------------------------------------------------------------
# va_history -> va_status (Medical & Disability router's own required field —
# missed on the first pass through this bridge; caught by actually running a
# real intake through the coordinator and seeing MEDICAL/CLAIMS come back
# NEEDS_INPUT for a missing field that has no matching questionnaire
# question under its own name at all).
# ---------------------------------------------------------------------------

_VA_HISTORY_MAP: Dict[str, str] = {
    "never": "not_enrolled",
    "contacted_only": "not_enrolled",  # contacted but never enrolled — still not enrolled
    "healthcare_only": "enrolled_no_rating",
    "claim_active": "enrolled_no_rating",  # filed, no confirmed rating yet
    "denied": "enrolled_no_rating",  # engaged with VA, no current rating
    # receiving_comp needs disability_rating to disambiguate has_rating vs
    # 100_percent_PT — handled in _map_va_status, not this static table.
}


def _map_va_status(va_history_raw: Optional[str], disability_rating_raw: Optional[str]) -> str:
    if va_history_raw == "receiving_comp":
        return "100_percent_PT" if disability_rating_raw in ("100", "tdiu") else "has_rating"
    if not va_history_raw:
        return "not_enrolled"
    return _VA_HISTORY_MAP.get(va_history_raw, "not_enrolled")


# ---------------------------------------------------------------------------
# housing_status
# ---------------------------------------------------------------------------

_HOUSING_STATUS_MAP: Dict[str, str] = {
    "unsheltered": "unhoused",
    "car": "unhoused",
    # No "sheltered homeless" bucket in VALID_HOUSING_STATUS; "unhoused" is
    # the closest available category for someone in emergency/transitional
    # shelter (matches the coordinator's own CHRONIC_HOMELESS edge case,
    # which treats "unhoused" as the housing-crisis bucket).
    "shelter": "unhoused",
    "couch": "unstable",
    "unstable_housed": "at_risk",  # "facing eviction or losing housing soon" — exact semantic match
    "stable": "stable",
}


def _map_housing_status(raw: Optional[str]) -> str:
    if not raw:
        return "unknown"
    return _HOUSING_STATUS_MAP.get(raw, "unknown")


# ---------------------------------------------------------------------------
# need -> domains. "crisis" is a need option but not a routable Domain —
# it maps to the coordinator's separate crisis.flagged mechanism instead.
# ---------------------------------------------------------------------------

_NEED_TO_DOMAIN: Dict[str, str] = {
    "housing": "HOUSING",
    "medical": "MEDICAL",
    "claims": "CLAIMS",
    "benefits": "BENEFITS",
    "toxic_exposure": "TOXIC_EXPOSURE",
    "employment": "EMPLOYMENT",
    "business": "BUSINESS",
    "legal": "LEGAL",
}

# Known, documented gap (not fixable here — a frontend content gap, not a
# data-mapping one): the questionnaire's "need" question has no
# transportation or women-veterans option, so TRANSPORTATION and
# WOMEN_VETERANS — both wired, working Divisions — are currently
# unreachable from the real intake flow no matter what this bridge does.


def _map_needs_to_domains(raw_list: Any) -> List[str]:
    if not isinstance(raw_list, list):
        return []
    domains: List[str] = []
    for need in raw_list:
        domain = _NEED_TO_DOMAIN.get(need)
        if domain and domain not in domains:
            domains.append(domain)
    return domains


def _needs_flag_crisis(raw_list: Any) -> bool:
    return isinstance(raw_list, list) and "crisis" in raw_list


# ---------------------------------------------------------------------------
# need_branches -- VaBenefits_v0_1.py and BusinessOpportunity_v0_1.py each
# gate their own Tracks on a *sub*-need vocabulary (education/voc_rehab/
# employment/transition/home_loan/adaptive_housing/pension/life_insurance/
# survivor_benefits/burial for VA Benefits; certification/contracting/
# financing/surplus_access/mentorship/training/state_programs for Business)
# that this bridge never forwarded at all -- found while auditing
# va_benefits_router.py, which reads need_branches directly off the intake
# with no translation from anything the questionnaire actually sends.
#
# Confirmed directly: every one of VaBenefits' 6 Tracks gates on
# `"x" in profile.need_branches`, most with no other fallback, so with
# need_branches always [] on real intake, only the FALLBACK path ("VA
# Benefits Review -- contact a VSO") could ever fire, regardless of what a
# veteran actually needed -- GI Bill, home loan, pension, survivor benefits,
# burial. (Two sub-blocks already partially work via a separate fallback on
# disability_rating, which the bridge does forward: VR&E at rating>=10, SAH/
# SHA grants at rating>=50 -- those were never fully dead.)
#
# The questionnaire's own "need" vocabulary (housing/medical/claims/
# benefits/toxic_exposure/employment/business/legal/crisis) has exactly ONE
# value in common with VaBenefits' need_branches vocabulary: "employment"
# (questionnaire's own label: "Employment / Training -- Jobs, retraining,
# SkillBridge, transition assistance" -- matches Track 2 exactly). Forwarding
# that one real overlap, honestly, rather than guessing at the rest.
#
# None of BusinessOpportunity's need_branches vocabulary overlaps with the
# questionnaire's "business" option at all, so nothing can be honestly
# forwarded there -- but its Track 1 (SDVOSB/VOSB certification, the
# division's core value) runs unconditionally regardless of need_branches,
# so that division was never fully dead either.
#
# Known, documented gap (not fixable here -- a frontend content gap, not a
# data-mapping one, same as the transportation/women-veterans "need" gap
# above): the questionnaire has no way to express "I need help with my GI
# Bill specifically" vs. home loan vs. pension vs. life insurance vs. burial.
# VaBenefits' Tracks 1 (GI Bill/Yellow Ribbon path specifically, distinct
# from its already-working VR&E fallback), 3 (home loan path, distinct from
# its already-working SAH/SHA fallback), 4 (pension), and 6 (burial) remain
# unreachable from real intake until the questionnaire can express that
# level of detail.
_NEED_BRANCHES_OVERLAP: Dict[str, str] = {
    "employment": "employment",
}


def _map_need_branches(raw_list: Any) -> List[str]:
    if not isinstance(raw_list, list):
        return []
    branches: List[str] = []
    for need in raw_list:
        branch = _NEED_BRANCHES_OVERLAP.get(need)
        if branch and branch not in branches:
            branches.append(branch)
    return branches


# ---------------------------------------------------------------------------
# is_survivor_or_dependent -- VaBenefits Track 5 (Survivor & Dependent
# Benefits: DIC, CHAMPVA, Survivors Pension, Ch.35 DEA, Fry Scholarship) has
# a real fallback (`"survivor_benefits" in need_branches or
# profile.is_survivor_or_dependent`), but the bridge never set that flag at
# all -- it was always the dataclass default (False). The questionnaire's
# own service_status option "surviving_family" already means exactly this;
# no translation ambiguity, unlike most of the approximations elsewhere in
# this file.
# ---------------------------------------------------------------------------


def _is_survivor_or_dependent(service_status_raw: Optional[str]) -> bool:
    return service_status_raw == "surviving_family"


# ---------------------------------------------------------------------------
# urgency — set both the formal schema's uppercase constraints.urgency AND
# the coordinator's own separate, lowercase, unnamespaced `urgency` field
# (pf_coordinator_v1.py's MULTI_DOMAIN_CRISIS edge case checks
# i.get("urgency") == "high" directly — an inconsistency inside the
# coordinator itself, not introduced by this bridge). Both are set so
# either code path sees a consistent signal.
# ---------------------------------------------------------------------------

_URGENCY_TO_CONSTRAINT: Dict[str, str] = {
    "tonight": "IMMEDIATE",
    "days": "HIGH",
    "weeks": "STANDARD",
    "planning": "STANDARD",
}

_URGENCY_TO_FLAT: Dict[str, str] = {
    "tonight": "high",
    "days": "high",
    "weeks": "standard",
    "planning": "standard",
}


def _map_urgency_constraint(raw: Optional[str]) -> str:
    return _URGENCY_TO_CONSTRAINT.get(raw or "", "STANDARD")


def _map_urgency_flat(raw: Optional[str]) -> str:
    return _URGENCY_TO_FLAT.get(raw or "", "standard")


# ---------------------------------------------------------------------------
# location
# ---------------------------------------------------------------------------

_STATE_RE = re.compile(r"^[A-Za-z]{2}$")


def _normalize_state(raw: Optional[str]) -> str:
    if not raw:
        return ""
    v = raw.strip().upper()
    return v if _STATE_RE.match(v) else ""


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def build_coordinator_intake(
    questionnaire_intake: Dict[str, Any],
    case_id: str,
) -> Dict[str, Any]:
    """
    Translates a real wyerd-squad questionnaire `intake` object (the exact
    shape POSTed to pathfinder-worker's /process) into a valid
    squad-bat.coordinator-intake.v1 payload for pf_coordinator_v1.run_coordinator.

    case_id must already be an opaque, PII-free identifier — this function
    does not generate or validate one.
    """
    q = questionnaire_intake or {}

    era_list = q.get("era")
    need_list = q.get("need")
    location = q.get("location") or {}

    domains = _map_needs_to_domains(need_list)
    crisis_flagged = _needs_flag_crisis(need_list)

    # The coordinator's own schema requires domains to be non-empty
    # (minItems: 1). A veteran who only selected "crisis" still needs a
    # domain to route through — CRISIS is a valid Domain enum value in the
    # formal schema even though no Division currently registers for it, so
    # resolving it honestly surfaces a "gap" (no active Division for CRISIS)
    # rather than silently sending an empty, schema-invalid domains array.
    if not domains:
        domains = ["CRISIS" if crisis_flagged else "UNKNOWN"]

    state = _normalize_state(location.get("state"))
    county = str(location.get("county") or "").strip()

    intake: Dict[str, Any] = {
        "schema": _INTAKE_SCHEMA,
        "case_id": case_id,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "founding_law_sha256": _FOUNDING_LAW_SHA256,
        "stage": "STABILIZE",
        "crisis": {
            "flagged": crisis_flagged,
            "type": "IMMEDIATE_SAFETY" if crisis_flagged else "NONE",
        },
        "domains": domains,
        "case_summary": "Questionnaire-derived case (see mapped fields below).",
        "constraints": {
            "urgency": _map_urgency_constraint(q.get("urgency")),
            "pilot_scope": "western-slope-co",
            **({"location": {"state": state, "county": county}} if state or county else {}),
        },
        # Flat fields the division routers actually read directly off the
        # intake dict (confirmed by reading each router's _build_profile).
        "discharge": _map_discharge(q.get("discharge")),
        "era": _map_era(era_list),
        "is_transitioning": _era_includes_transitioning(era_list),
        "disability_rating": _map_disability_rating(q.get("disability_rating")),
        "housing_status": _map_housing_status(q.get("housing_status")),
        "income_monthly": _map_income(q.get("income")),
        "va_status": _map_va_status(q.get("va_history"), q.get("disability_rating")),
        "service_status": q.get("service_status") or "not_sure",
        # Also set at the top level for the coordinator's own inline
        # confidence/edge-case checks, which read state/county/urgency
        # directly off the intake, not nested under constraints.
        "state": state,
        "county": county,
        "urgency": _map_urgency_flat(q.get("urgency")),
        # va_facility_issues -- pure passthrough, no mapping needed. Found
        # missing entirely (not even in this module's own "known limitations"
        # list) while auditing pf_coordinator_v1.py's edge cases: its
        # VA_FACILITY_OBSTRUCTION check and MODULES/LEGAL/src/legal_router.py
        # both read intake["va_facility_issues"] directly as a raw single-
        # select string and both already expect exactly the questionnaire's
        # own values ("no"/"complaints"/"obstruction"/"distrust") -- no
        # translation required, unlike every other field in this bridge.
        # Without this line, a veteran answering "my local VA is retaliating
        # against me" in the questionnaire could never trigger the coordinator's
        # own real, already-built VA_FACILITY_OBSTRUCTION edge case or Track 10
        # legal routing through the real intake flow -- the field just never
        # reached them.
        "va_facility_issues": q.get("va_facility_issues") or "",
        # need_branches / is_survivor_or_dependent -- see the module-level
        # comments above _map_need_branches and _is_survivor_or_dependent
        # for why these exist and exactly what they do and don't unlock.
        "need_branches": _map_need_branches(need_list),
        "is_survivor_or_dependent": _is_survivor_or_dependent(q.get("service_status")),
    }

    return intake
