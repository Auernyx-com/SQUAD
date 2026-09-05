"""
Housing_v0_1.py
SQUAD BAT — Housing Division routing engine.

Tracks:
  1. Chronically Homeless / Street-Level Crisis  — HUD-VASH, HCHV, 1-877-4AID-VET
  2. At Risk / Unstable Housing                  — SSVF rapid re-housing, emergency resources
  3. Domestic Violence + Housing                 — DV-aware housing referrals, SSVF DV track
  4. Criminal Record Housing Barrier             — HUD-VASH doesn't require clean record (explicit)
  5. VA Adaptive Housing                         — SAH/SHA grants for service-connected disability
  6. VA Home Loan                                — purchase, refinance, IRRRL for eligible veterans
  7. Housing Legal Protection                    — eviction defense, tenant rights, foreclosure

Gate: Housing need never blocks other routing — it runs in parallel.
Design law: Criminal record does not disqualify from HUD-VASH. State this explicitly.
If veteran identifies VA facility as the barrier to housing services: surface obstruction track.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional

# ---------------------------------------------------------------------------
# Shared verified contacts
# ---------------------------------------------------------------------------

_SHARED_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'MODULES', '_shared')
)
if _SHARED_PATH not in sys.path:
    sys.path.insert(0, _SHARED_PATH)

from contacts import (  # type: ignore
    VA_MAIN_LINE         as _VA_MAIN_LINE,
    VA_HOMELESS_VETERANS as _VA_HOMELESS_VETERANS,
    VETERANS_CRISIS_LINE as _VETERANS_CRISIS_LINE,
    VA_OIG               as _VA_OIG,
    HUD_HOUSING_COUNSELORS as _HUD_HOUSING_COUNSELORS,
    get_branch_emergency as _get_branch_emergency,
)


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@dataclass
class VetHousingProfile:
    # Current housing situation
    # "unhoused" | "unstable" | "at_risk" | "stable" | "unknown"
    housing_status: str = "unknown"

    # How long homeless (months) — for chronic homelessness determination
    homelessness_months: int = 0

    # Chronic homelessness flag — set explicitly by intake or derived from months
    is_chronically_homeless: bool = False

    # Active domestic violence situation
    has_dv_situation: bool = False

    # Active criminal case — relevant for flagging HUD-VASH eligibility note
    has_active_criminal_case: bool = False

    # Service-connected disability rating (affects adaptive housing eligibility)
    disability_rating: Optional[int] = None

    # VA home loan eligibility explored
    has_va_loan_interest: bool = False

    # Discharge character
    discharge: str = "unknown"

    # Branch of service
    branch: str = "unknown"

    # Facing eviction
    facing_eviction: bool = False

    # VA facility is the obstruction for housing services
    va_facility_obstruction: bool = False

    # Location
    state: str = ""
    county: str = ""


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def route_housing(profile: VetHousingProfile) -> dict:
    result = {
        "primary_path": None,
        "secondary_options": [],
        "flags": [],
        "next_action": None,
        "key_resources": [],
        "key_forms": [],
        "notes": [],
    }

    status = (profile.housing_status or "unknown").lower()
    is_chronic = (
        profile.is_chronically_homeless or
        profile.homelessness_months >= 6
    )

    # ── TRACK 1: CHRONICALLY HOMELESS / STREET-LEVEL CRISIS ──────────────────
    if status == "unhoused" or is_chronic:
        result["flags"].append("chronically_homeless" if is_chronic else "currently_unhoused")
        result["primary_path"] = "HUD-VASH — VA + HUD Housing Voucher Program (Priority Tier)"

        result["secondary_options"].extend([
            f"VA National Call Center for Homeless Veterans — {_VA_HOMELESS_VETERANS} — "
            "24/7. This line connects to VA coordinators who initiate HUD-VASH referrals. "
            "Call this first. It is the fastest path into the system.",

            "HUD-VASH (HUD-VA Supportive Housing) — joint VA and HUD program providing "
            "Section 8 vouchers specifically for homeless veterans, paired with VA case management. "
            "This is the priority tier. Chronic homelessness is the highest priority classification. "
            "Contact initiates the referral — no advance paperwork required to call.",

            "VA Healthcare for Homeless Veterans (HCHV) — outreach and case management "
            "program operating at most VA facilities. Can connect to shelter, transitional housing, "
            "and long-term housing support. Entry point: same call line as above.",

            "SSVF (Supportive Services for Veteran Families) — VA-funded rapid re-housing "
            "and prevention program run by community nonprofits. Covers emergency financial "
            "assistance, case management, and rental support. Find local providers: "
            "va.gov/homeless/ssvf or call 211 and ask for veteran SSVF providers.",

            "211.org — local emergency resources, shelters, transitional housing. "
            "Available 24/7, text or call 211. Tell them you are a veteran.",
        ])

        if is_chronic:
            result["notes"].append(
                "CHRONIC HOMELESSNESS — defined as 6+ months homeless or repeated episodes. "
                "This is the highest priority classification for HUD-VASH and places this veteran "
                "at the front of the referral queue. State this explicitly when calling."
            )

        result["key_resources"].extend([
            f"VA National Call Center for Homeless Veterans — {_VA_HOMELESS_VETERANS} (24/7)",
            "SSVF provider locator — va.gov/homeless/ssvf",
            "211.org — local emergency housing",
        ])
        result["key_forms"].extend([
            "No advance forms required to call 1-877-4AID-VET — the coordinator initiates paperwork",
        ])
        if not result["next_action"]:
            result["next_action"] = (
                f"Call VA National Call Center for Homeless Veterans now: {_VA_HOMELESS_VETERANS} — 24/7. "
                "Tell them you are a veteran, you are currently unhoused"
                + (", and you have been homeless for 6+ months" if is_chronic else "")
                + ". Ask specifically for a HUD-VASH referral. "
                "No paperwork required to make this call."
            )

    # ── TRACK 2: AT RISK / UNSTABLE HOUSING ──────────────────────────────────
    if status in ("unstable", "at_risk") or profile.facing_eviction:
        result["flags"].append("housing_at_risk")
        result["primary_path"] = result["primary_path"] or "SSVF — Rapid Re-Housing and Prevention"

        result["secondary_options"].extend([
            "SSVF (Supportive Services for Veteran Families) — the fastest VA-funded path for "
            "veterans at risk of losing housing. Covers emergency financial assistance, security "
            "deposits, back rent, utility bills, and case management. "
            "Providers work quickly. Find local SSVF: va.gov/homeless/ssvf or call 211.",

            f"HUD-approved housing counselors — {_HUD_HOUSING_COUNSELORS} — "
            "free or low-cost tenant rights advice, eviction defense guidance, "
            "foreclosure prevention for VA loan holders.",

            "Legal Aid — free eviction defense in most states. Find at lawhelp.org or 211.org. "
            "If an eviction notice has been issued, contact legal aid immediately — deadlines are short.",
        ])

        if profile.facing_eviction:
            result["flags"].append("eviction_imminent")
            result["notes"].append(
                "EVICTION NOTICE RECEIVED — timeline is critical. "
                "Contact legal aid AND SSVF on the same day. "
                "An attorney can request a continuance; SSVF can sometimes pay back rent "
                "fast enough to stop the eviction entirely. Both moves together."
            )

        result["key_resources"].extend([
            "SSVF — va.gov/homeless/ssvf",
            f"HUD Housing Counselors — {_HUD_HOUSING_COUNSELORS}",
            "Legal Aid eviction defense — lawhelp.org",
        ])
        if not result["next_action"]:
            result["next_action"] = (
                "Call 211 and ask for the nearest SSVF provider — same day. "
                "SSVF can provide emergency financial assistance to prevent eviction. "
                + ("Contact a legal aid attorney about the eviction notice immediately — deadlines apply. " if profile.facing_eviction else "")
                + f"For VA-specific help: {_VA_HOMELESS_VETERANS}."
            )

    # ── TRACK 3: DOMESTIC VIOLENCE + HOUSING ─────────────────────────────────
    if profile.has_dv_situation:
        result["flags"].append("dv_housing_need")
        result["primary_path"] = result["primary_path"] or "DV-Aware Housing Resources"

        result["secondary_options"].extend([
            "SSVF DV Track — SSVF providers specifically support veterans fleeing domestic violence. "
            "This includes emergency financial assistance, rapid re-housing, and confidentiality protections. "
            "Your location does not have to be disclosed. Find local SSVF: va.gov/homeless/ssvf.",

            "National Domestic Violence Hotline — 1-800-799-7233 — 24/7 crisis line. "
            "Can connect to local DV shelters that accept veterans and their families. "
            "Text START to 88788.",

            "VA MST Coordinator — if MST is a factor in the DV situation, the MST Coordinator "
            f"at your VA facility can connect to DV-aware housing resources. Call {_VA_MAIN_LINE} "
            "and ask for the MST Coordinator.",

            "Confidentiality note: you are not required to disclose your address to access SSVF. "
            "Providers understand safety planning.",
        ])

        result["notes"].append(
            "DV situations involving a veteran defendant: if there is an active criminal case, "
            "housing and legal routing are both required simultaneously. VTC diversion, "
            "if available, often includes housing as part of the treatment plan."
        )
        if not result["next_action"]:
            result["next_action"] = (
                "Call SSVF through 211 — ask specifically for DV veteran housing support. "
                "Your location does not need to be disclosed. "
                "National DV Hotline: 1-800-799-7233 (24/7)."
            )

    # ── TRACK 4: CRIMINAL RECORD HOUSING BARRIER ─────────────────────────────
    if profile.has_active_criminal_case or (
        profile.discharge in ("other_than_honorable", "dishonorable", "bcd")
    ):
        result["flags"].append("criminal_record_housing_flag")

        result["notes"].append(
            "CRITICAL: HUD-VASH does NOT automatically disqualify veterans with criminal records. "
            "Unlike standard HCV (Section 8), HUD-VASH has a separate, veteran-specific eligibility path. "
            "Individual PHAs have discretion — but the program was designed for veterans who "
            "face barriers, including justice-involved veterans. "
            "Do not accept a blanket 'ineligible' without written documentation of the specific rule applied."
        )
        result["notes"].append(
            "If a PHA denies HUD-VASH based on criminal record: request the denial in writing, "
            "including the specific federal regulation cited. Then contact NVLSP (nvlsp.org) "
            "or a housing legal aid attorney — many such denials are wrongly applied."
        )
        result["secondary_options"].append(
            "Veterans Treatment Court (VTC) programs often include housing stability as part of the "
            "treatment plan — housing providers connected to the VTC may have fewer restrictions "
            "than standard public housing. If a criminal case is active, ask the VTC coordinator "
            "about housing as part of your case plan."
        )

        if not result["primary_path"]:
            result["primary_path"] = "HUD-VASH — Criminal Record Does Not Automatically Disqualify"

    # ── TRACK 5: VA ADAPTIVE HOUSING GRANTS ──────────────────────────────────
    if profile.disability_rating is not None and profile.disability_rating >= 30:
        result["flags"].append("adaptive_housing_candidate")

        result["secondary_options"].append(
            "VA Adaptive Housing Grants — Specially Adapted Housing (SAH) and Special Housing "
            "Adaptation (SHA) grants for veterans with qualifying service-connected disabilities. "
            "SAH: up to $109,986 (FY2024) for severe mobility impairment. "
            "SHA: up to $22,036 for lesser adaptation needs. "
            "Apply through your VA regional loan center or at va.gov/housing-assistance/adaptive-housing-grants."
        )
        result["key_forms"].append("VA Form 26-4555 (Adaptive Housing Application)")

    # ── TRACK 6: VA HOME LOAN ─────────────────────────────────────────────────
    if profile.has_va_loan_interest and status not in ("unhoused", "unstable"):
        result["flags"].append("va_home_loan_track")
        result["secondary_options"].append(
            "VA Home Loan Guarantee — no down payment required for eligible veterans. "
            "Competitive rates, no PMI. Certificate of Eligibility (COE) required. "
            "Apply at va.gov/housing-assistance/home-loans or through a VA-approved lender. "
            "If previously denied, check whether your COE was correctly issued."
        )
        result["key_forms"].append("VA Form 26-1880 (COE Request) or request through lender")

    # ── TRACK 7: HOUSING LEGAL PROTECTION ────────────────────────────────────
    if profile.facing_eviction or status in ("unstable", "at_risk"):
        if "housing_legal_protection" not in result["flags"]:
            result["flags"].append("housing_legal_protection")
            result["secondary_options"].append(
                "SCRA (Servicemembers Civil Relief Act) — if recently separated (within 90 days of discharge) "
                "or on active orders, additional eviction protections may apply. "
                "Servicemember Legal Center: 1-800-342-9647."
            )

    # ── VA FACILITY OBSTRUCTION ───────────────────────────────────────────────
    if profile.va_facility_obstruction:
        result["flags"].append("va_facility_obstruction_housing")
        result["notes"].append(
            "VA facility flagged as obstruction for housing services. "
            "Route AROUND the facility: SSVF providers are community-based and not connected to the VAMC. "
            f"VA National Call Center ({_VA_HOMELESS_VETERANS}) operates independently of local facilities. "
            f"OIG Hotline for facility misconduct: {_VA_OIG}."
        )

    # ── BRANCH EMERGENCY RESOURCES ────────────────────────────────────────────
    if status in ("unhoused", "unstable") or is_chronic:
        branch_resources = _get_branch_emergency(profile.branch)
        if branch_resources:
            result["flags"].append("branch_emergency_resources_available")
            result["notes"].append("BRANCH-SPECIFIC EMERGENCY RESOURCES — available now, separate from VA:")
            result["notes"].extend(branch_resources)

    # ── ALWAYS-AVAILABLE FLOOR RESOURCES ─────────────────────────────────────
    result["key_resources"].extend([
        f"VA National Call Center for Homeless Veterans — {_VA_HOMELESS_VETERANS} (24/7)",
        "SSVF provider locator — va.gov/homeless/ssvf",
        "211.org — local emergency housing, shelters, and rapid re-housing",
        "NVLSP housing legal support — nvlsp.org",
    ])

    # ── FALLBACK ──────────────────────────────────────────────────────────────
    if not result["primary_path"]:
        result["primary_path"] = "VA Housing Resources — Multiple Paths Available"
        result["secondary_options"].append(
            f"Call VA main line {_VA_MAIN_LINE} and ask for housing assistance. "
            "They can connect to the right program for your situation."
        )
        result["secondary_options"].append(
            "211.org — local housing resources and veteran-specific programs."
        )
        if not result["next_action"]:
            result["next_action"] = (
                f"Call VA main line: {_VA_MAIN_LINE} — ask for housing assistance. "
                "Or call 211 for local veteran housing resources."
            )

    return result
