"""
contacts.py
SQUAD BAT — Shared verified contact numbers.

Single source of truth for all hardcoded phone numbers used across
BAT divisions, coordinator, and worker prompts.

POLICY:
  - Phone numbers are NEVER LLM-generated.
  - Any number not positively verified is marked VERIFY_BEFORE_PRODUCTION
    and must not be surfaced to a veteran.
  - When a number changes, fix it here only. One edit, all divisions update.
  - Last reviewed: 2026-05-24

USAGE (Python):
    import sys, os
    _SHARED = os.path.join(os.path.dirname(__file__), '..', '..', 'MODULES', '_shared')
    if _SHARED not in sys.path:
        sys.path.insert(0, _SHARED)
    from contacts import VA_MAIN_LINE, VA_OIG, BRANCH_EMERGENCY
"""

from __future__ import annotations
from typing import Dict, List

# ---------------------------------------------------------------------------
# VA — Floor contacts (always surfaced regardless of track)
# ---------------------------------------------------------------------------

VA_MAIN_LINE         = "1-800-827-1000"
VA_HOMELESS_VETERANS = "1-877-4AID-VET (1-877-424-3838)"   # 24/7 homeless veteran support line
VETERANS_CRISIS_LINE = "988, press 1"                       # Veterans Crisis Line (also text 838255)

# ---------------------------------------------------------------------------
# VA — Oversight and escalation
# ---------------------------------------------------------------------------

VA_OIG               = "1-800-488-8244"   # VA Office of Inspector General hotline — report fraud, waste, abuse, facility misconduct
VA_VET_CENTER        = "1-877-WAR-VETS (1-877-927-8387)"   # Vet Center — community-based, separate from VA medical centers

# ---------------------------------------------------------------------------
# VA — Congressional escalation
# POLICY: Congressional rep names are NEVER hardcoded — names change.
#         Always point to the lookup URL. The caseworker does the work.
# ---------------------------------------------------------------------------

CONGRESSIONAL_LOOKUP = "https://www.house.gov/representatives/find-your-representative"
CONGRESSIONAL_NOTE   = (
    "Your U.S. House representative has a VA caseworker whose only job is "
    "to unstick veteran cases with the VA. Find your rep at "
    "house.gov/representatives/find-your-representative — call their district "
    "office and ask for the Veterans Affairs caseworker specifically."
)

# ---------------------------------------------------------------------------
# Service organizations — verified lines
# ---------------------------------------------------------------------------

DAV_SERVICE_LINE           = "1-800-741-4990"   # Disabled American Veterans
COHEN_VETERANS_NETWORK     = "1-855-204-5784"   # Mental health + legal navigation
SERVICEMEMBER_LEGAL_CENTER = "1-800-342-9647"   # Free legal help (also Military OneSource)
NVLSP_NOTE                 = "nvlsp.org"         # National Veterans Legal Services Program — no single verified direct line
SAFE_HELPLINE              = "1-800-773-7927"   # DoD confidential MST/sexual assault support (24/7)
HUD_HOUSING_COUNSELORS     = "1-800-569-4287"   # HUD-approved counselors — foreclosure, tenant rights

# ---------------------------------------------------------------------------
# Branch-specific emergency resources
# Keyed by normalized branch name (lowercase, underscores).
# Used by Legal, Benefits, and any Division routing a multi-domain crisis.
# ---------------------------------------------------------------------------

BRANCH_EMERGENCY: Dict[str, List[str]] = {
    "marine_corps": [
        "Semper Fi & America's Fund — 760-725-3680 — emergency financial assistance "
        "for Marines and their families. Same-week response for verified cases.",
        "Marine Corps Wounded Warrior Regiment — 1-877-487-6299 — recovery support "
        "and benefits navigation for injured/ill Marines.",
    ],
    "army": [
        "Army Emergency Relief (AER) — 1-866-878-6378 — emergency financial assistance, interest-free loans.",
        "Army Wounded Warrior Program (AW2) — 1-800-237-1336",
    ],
    "navy": [
        "Navy-Marine Corps Relief Society — 1-800-654-8364 — emergency financial assistance.",
        "Wounded Warrior Regiment (Navy component) — 1-877-487-6299",
    ],
    "air_force": [
        "Air Force Aid Society — 1-800-769-8951 — emergency financial assistance.",
    ],
    "coast_guard": [
        "Coast Guard Mutual Assistance (CGMA) — 1-800-881-2462 — emergency financial assistance.",
        "NOTE: Coast Guard veterans are routinely and incorrectly told they are ineligible "
        "for VA benefits. They are fully eligible under 38 USC § 101. Escalate any denial.",
    ],
    "army_national_guard": [
        "Army Emergency Relief (AER) — 1-866-878-6378 — Title 10 activation required "
        "for full AER eligibility; Title 32 may qualify for state programs.",
        "State National Guard Family Assistance Center — contact your state Adjutant General's office.",
    ],
    "air_national_guard": [
        "Air Force Aid Society — 1-800-769-8951",
        "State National Guard Family Assistance Center — contact your state Adjutant General's office.",
    ],
}

# ---------------------------------------------------------------------------
# Branch aliases — maps real intake option values to BRANCH_EMERGENCY keys.
#
# The live questionnaire (wyerd-squad/tool/index.html) sends branch as
# 'marines', 'army_ng', 'air_ng', etc. — not the BRANCH_EMERGENCY dict keys
# above ('marine_corps', 'army_national_guard', 'air_national_guard'). Without
# this alias table, get_branch_emergency() silently returned [] for every
# Marine Corps and Guard veteran even though the resources were coded and
# present in the dict — verified against the questionnaire's real option
# values on 2026-09-05.
#
# KNOWN GAP: the questionnaire also offers 'army_reserve', 'navy_reserve',
# 'af_reserve', 'usmc_reserve', and 'uscg_reserve', and BRANCH_EMERGENCY has
# no distinct entries for any Reserve component (only the two National Guard
# branches exist above). Until reserve-specific entries are verified and
# added, those five values are intentionally left unmapped rather than
# guessed at — they fall through to no branch-specific resources, same as
# any other unrecognized branch value. Do not silently alias them to the
# active-duty org entries without verifying reservist eligibility first.
# ---------------------------------------------------------------------------

BRANCH_ALIASES: Dict[str, str] = {
    "marines": "marine_corps",
    "usmc": "marine_corps",
    "army_ng": "army_national_guard",
    "air_ng": "air_national_guard",
}


def get_branch_emergency(branch: str) -> List[str]:
    """
    Normalize a raw branch value (as sent by intake) and return its
    BRANCH_EMERGENCY resource list, or [] if none exists.

    Single source of truth for this lookup — Division routers should call
    this instead of indexing BRANCH_EMERGENCY directly, so an alias fix here
    reaches every caller.
    """
    key = (branch or "").lower().replace(" ", "_").replace("-", "_")
    key = BRANCH_ALIASES.get(key, key)
    return BRANCH_EMERGENCY.get(key, [])


# ---------------------------------------------------------------------------
# VERIFY_BEFORE_PRODUCTION — do not surface to veterans until confirmed
# ---------------------------------------------------------------------------

_UNVERIFIED = {
    # "vtc_nadcp_direct":  "VERIFY_BEFORE_PRODUCTION",
    # "nvlsp_direct_line": "VERIFY_BEFORE_PRODUCTION",
    # "amvets_service":    "VERIFY_BEFORE_PRODUCTION",
}
