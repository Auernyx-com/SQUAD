"""
MedDisability_v0.1.py
SQUAD BAT — Medical & Disability Division routing engine.

Inputs: VetMedProfile dataclass
Output: dict with primary_path, secondary_options, flags, next_action

Decision tracks:
  1. Not enrolled in VA healthcare            → enrollment path
  2. Enrolled, no disability rating           → initial claim path
  3. Has rating, seeking increase / appeals   → supplemental / HLR / BVA path
  4. Has rating, checking additional benefits → TDIU / SMC / Aid & Attendance / Caregiver
  5. Mental health specific needs             → Vet Center / specialized programs
  6. Caregiver situation                      → PCAFC path
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class VetMedProfile:
    # VA enrollment status
    # "not_enrolled" | "enrolled_no_rating" | "has_rating" | "100_percent_PT"
    va_status: str

    # Discharge character — affects healthcare eligibility
    # "honorable" | "general" | "other_than_honorable" | "dishonorable" | "unknown"
    discharge: str

    # Current VA disability rating (0–100). None if not rated.
    disability_rating: Optional[int]

    # What the veteran is coming in for (multi-select allowed)
    # "healthcare_enrollment" | "initial_claim" | "increase_claim" | "appeal"
    # "mental_health" | "caregiver" | "tdiu" | "smc" | "aid_and_attendance"
    need_branches: List[str] = field(default_factory=list)

    # Were they recently denied? (within 1 year)
    recent_denial: bool = False

    # Do they have new evidence for a claim (nexus letter, buddy statement, new diagnosis)?
    has_new_evidence: bool = False

    # Is unemployment a factor (can't work due to SC conditions)?
    unemployable: bool = False

    # Does the veteran or a family member need in-home care assistance?
    caregiver_need: bool = False

    # Mental health flags
    ptsd: bool = False
    tbi: bool = False
    mst: bool = False  # Military Sexual Trauma

    # Location (state or county string) — used to point to nearest VAMC / Vet Center
    location: str = ""

    # Rating is Permanent & Total (P&T)
    permanent_total: bool = False

    # Has dependents (spouse, children) — affects allowance calculations
    has_dependents: bool = False


def route_med_disability(profile: VetMedProfile) -> dict:
    """
    Primary routing engine for medical and disability needs.
    Returns a structured result dict — never a guaranteed eligibility claim.
    Pathfinder surfaces this to the veteran with plain-language framing.
    """

    result = {
        "primary_path": None,
        "secondary_options": [],
        "flags": [],
        "next_action": None,
        "key_forms": [],
        "notes": [],
    }

    discharge_lower = (profile.discharge or "").lower()

    # ── DISCHARGE GATE ────────────────────────────────────────────────────────
    # Dishonorable discharge is a hard block on most VA benefits.
    # OTH blocks most healthcare UNLESS combat veteran (2-year window) or MST.
    if discharge_lower == "dishonorable":
        result["primary_path"] = "Discharge Upgrade Review"
        result["secondary_options"] = [
            "Military Records Review Board (BCMR/BCNR)",
            "Discharge Review Board (DRB) — if within 15 years of discharge",
            "Legal aid through a veterans law clinic",
        ]
        result["flags"].append("dishonorable_hard_block")
        result["next_action"] = (
            "Explore discharge upgrade before applying for VA benefits. "
            "A veterans law clinic can advise at no cost."
        )
        result["notes"].append(
            "Dishonorable discharge bars most VA benefits. "
            "Upgrade to OTH or higher may restore eligibility."
        )
        return result

    if discharge_lower == "other_than_honorable":
        result["flags"].append("oth_discharge_limited_eligibility")
        result["notes"].append(
            "OTH discharge limits some benefits but does NOT bar all. "
            "MST-related care is available regardless of discharge. "
            "Combat veterans may qualify for 2-year healthcare window. "
            "Discharge upgrade worth exploring alongside any claim."
        )

    # ── TRACK 1: NOT ENROLLED IN VA HEALTHCARE ────────────────────────────────
    if profile.va_status == "not_enrolled" or "healthcare_enrollment" in profile.need_branches:
        result["primary_path"] = "VA Healthcare Enrollment — VA Form 10-10EZ"
        result["secondary_options"] = [
            "Vet Centers (community-based, less paperwork, mental health focused)",
            "Community Care (if VA facility is too far — 30/60-minute drive thresholds)",
            "State Veterans Health Programs (varies by state)",
        ]
        result["flags"].append("not_enrolled")
        result["key_forms"].append("VA Form 10-10EZ (Healthcare Enrollment)")
        result["next_action"] = (
            "Apply online at va.gov/health-care/apply or call 1-877-222-8387. "
            "Bring DD-214. If OTH discharge, ask specifically about MST care or combat veteran eligibility."
        )

        if profile.disability_rating and profile.disability_rating >= 50:
            result["secondary_options"].insert(0, "Priority Group 1–3 enrollment — likely no copays at 50%+")
            result["flags"].append("priority_enrollment_likely")

        if profile.ptsd or profile.mst or profile.tbi:
            result["secondary_options"].insert(0, "Vet Centers — specialized in combat/MST trauma, open to OTH")
        return result

    # ── TRACK 2: ENROLLED, NO RATING — FILE INITIAL CLAIM ────────────────────
    if profile.va_status == "enrolled_no_rating" or "initial_claim" in profile.need_branches:
        result["primary_path"] = "Initial Disability Claim — VA Form 21-526EZ"
        result["secondary_options"] = [
            "Free VSO assistance (DAV, VFW, American Legion — accredited claim agents)",
            "VA Regional Office in-person appointment",
            "Nexus letter from private doctor (connects condition to service)",
            "Buddy statements (fellow service members as evidence)",
        ]
        result["flags"].append("unrated_claim_candidate")
        result["key_forms"].extend([
            "VA Form 21-526EZ (Disability Compensation)",
            "DD-214 (Certificate of Release)",
            "Service treatment records (STRs)",
        ])
        result["next_action"] = (
            "File at va.gov/disability/file-disability-claim or visit your nearest VA Regional Office. "
            "Contact a VSO first — they are free and dramatically improve approval rates."
        )
        result["notes"].append(
            "Filing date matters — your effective date is the date VA receives your claim. "
            "File as soon as possible, even with incomplete evidence. You can add evidence later."
        )
        return result

    # ── TRACK 3: HAS RATING — INCREASE / APPEALS ─────────────────────────────
    if profile.va_status in ("has_rating", "100_percent_PT"):
        rating = profile.disability_rating or 0

        # Appeals track
        if "appeal" in profile.need_branches or profile.recent_denial:
            if profile.has_new_evidence:
                result["primary_path"] = "Supplemental Claim (new evidence)"
                result["key_forms"].append("VA Form 20-0995 (Supplemental Claim)")
                result["next_action"] = (
                    "Submit new evidence (nexus letter, buddy statement, new diagnosis) "
                    "with VA Form 20-0995. No time limit."
                )
            else:
                result["primary_path"] = "Higher-Level Review (HLR) — same evidence, senior reviewer"
                result["key_forms"].append("VA Form 20-0996 (Higher-Level Review)")
                result["next_action"] = (
                    "Request HLR within 1 year of denial with VA Form 20-0996. "
                    "No new evidence required — a senior reviewer re-examines the file."
                )
            result["secondary_options"] = [
                "Board of Veterans Appeals (BVA) — direct review, evidence, or hearing lanes",
                "Accredited VA attorney or claims agent (fee only on back pay if you win)",
                "Veterans Service Organization (VSO) — free representation at BVA",
            ]
            result["flags"].append("appeals_track")
            result["notes"].append(
                "You have one year from your decision letter to request HLR or appeal to BVA. "
                "Supplemental Claim has no time limit if new evidence exists."
            )

        # Increase track
        elif "increase_claim" in profile.need_branches:
            result["primary_path"] = "Rating Increase — Supplemental Claim or direct increase request"
            result["secondary_options"] = [
                "VSO review of your current rating decision",
                "Private C&P exam (nexus letter strengthens increase)",
                "Buddy statements documenting worsening condition",
            ]
            result["key_forms"].append("VA Form 20-0995 or VA Form 21-526EZ (for new conditions)")
            result["flags"].append("increase_track")
            result["next_action"] = (
                "Contact a VSO to review your existing rating. "
                "If condition has worsened, file VA Form 21-526EZ for that condition or "
                "a Supplemental Claim with new medical evidence."
            )

        # ── TRACK 4: ADDITIONAL BENEFIT CHECKS ───────────────────────────────

        # TDIU — Total Disability Individual Unemployability
        if profile.unemployable and rating >= 60:
            result["secondary_options"].insert(0, "TDIU — Individual Unemployability (paid at 100% rate)")
            result["key_forms"].append("VA Form 21-8940 (TDIU Application)")
            result["flags"].append("tdiu_candidate")
            result["notes"].append(
                "TDIU may apply at 60%+ single rating or 70%+ combined. "
                "Pays at 100% rate if unemployable due to SC conditions. "
                "File VA Form 21-8940."
            )
        elif profile.unemployable and rating >= 40:
            result["flags"].append("tdiu_possible_combined_check")
            result["notes"].append(
                "TDIU may still apply if combined rating reaches 70%+. "
                "Ask your VSO to evaluate your combined rating for TDIU eligibility."
            )

        # SMC — Special Monthly Compensation
        if rating == 100 or profile.permanent_total:
            result["secondary_options"].append("SMC (Special Monthly Compensation) — if loss of use or need aid")
            result["flags"].append("smc_eval_recommended")
            result["notes"].append(
                "At 100% or P&T, SMC levels (K through R) may apply if you have "
                "loss of use of limbs, need regular aid and attendance, or are housebound. "
                "Request SMC evaluation through your VSO."
            )

        # Aid & Attendance
        if profile.caregiver_need:
            result["secondary_options"].append("Aid & Attendance — monthly supplement for in-home care needs")
            result["key_forms"].append("VA Form 21-2680 (Aid & Attendance / Housebound)")
            result["flags"].append("aid_and_attendance_candidate")

        # Caregiver Support Program (PCAFC)
        if profile.caregiver_need:
            result["secondary_options"].append(
                "Program of Comprehensive Assistance for Family Caregivers (PCAFC) — "
                "stipend + benefits for family caregiver"
            )
            result["notes"].append(
                "PCAFC requires a serious injury incurred or aggravated in the line of duty. "
                "Apply through your VA Caregiver Support Coordinator."
            )
            result["flags"].append("pcafc_candidate")

        # Dependency allowance
        if profile.has_dependents and rating >= 30:
            result["secondary_options"].append(
                "Dependency and Indemnity Compensation (DIC) allowance — add dependents to rating"
            )
            result["key_forms"].append("VA Form 21-686c (Add Dependents)")
            result["flags"].append("dependency_allowance_applicable")
            result["notes"].append(
                "At 30%+, adding dependents (spouse, children) increases monthly compensation. "
                "File VA Form 21-686c if not already done."
            )

        if not result["primary_path"]:
            result["primary_path"] = "VA Benefits Review — current rating and additional program check"
            result["next_action"] = "Contact a VSO to review full benefits picture based on current rating."

    # ── TRACK 5: MENTAL HEALTH SPECIFIC ──────────────────────────────────────
    if profile.ptsd or profile.tbi or profile.mst or "mental_health" in profile.need_branches:
        mh_programs = []

        if profile.mst:
            mh_programs.append("MST Coordinator at nearest VAMC — specialized counseling, no discharge barrier")
            result["flags"].append("mst_flagged")
            result["notes"].append(
                "MST-related mental health care is available regardless of discharge type or VA enrollment status. "
                "Every VA Medical Center has a designated MST Coordinator."
            )

        if profile.ptsd:
            mh_programs.append("VA PTSD programs — individual therapy, group therapy, residential (PTSD Clinical Teams)")
            mh_programs.append("Vet Centers — combat/trauma counseling, readjustment services")
            result["flags"].append("ptsd_flagged")

        if profile.tbi:
            mh_programs.append("VA Polytrauma / TBI Network — evaluation, rehabilitation, follow-up care")
            result["flags"].append("tbi_flagged")

        if mh_programs:
            if result["secondary_options"]:
                result["secondary_options"].extend(mh_programs)
            else:
                result["secondary_options"] = mh_programs

        if not result["primary_path"]:
            result["primary_path"] = "VA Mental Health Services — contact nearest VAMC or Vet Center"
            result["next_action"] = (
                "Call 1-800-827-1000 to reach your nearest VA and ask for Mental Health Services. "
                "Vet Centers (vetcenter.va.gov) are lower-barrier and open to OTH discharge. "
                "Crisis: call or text 988, then press 1."
            )

    # ── FALLBACK ──────────────────────────────────────────────────────────────
    if not result["primary_path"]:
        result["primary_path"] = "VA Benefits Review — contact a VSO for full eligibility check"
        result["next_action"] = (
            "Call 1-800-827-1000 or visit va.gov to connect with your nearest VA Regional Office. "
            "A VSO (DAV, VFW, American Legion) can review your full situation at no cost."
        )

    return result
