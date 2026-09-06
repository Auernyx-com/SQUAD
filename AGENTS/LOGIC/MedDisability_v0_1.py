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


def check_qualification(discharge: str) -> dict:
    """
    GATE 1 — Qualification check. Always runs first.
    Discharge character determines what the veteran can access.
    Returns a qualification dict:
      status: "QUALIFIED" | "LIMITED" | "BLOCKED"
      access: what is still open to them
      blocked: what is not available
      upgrade_path: whether to pursue discharge upgrade
      notes: plain-language explanation
    """
    d = (discharge or "").lower().strip()

    if d == "dishonorable":
        return {
            "status": "BLOCKED",
            "access": [],
            "blocked": ["VA healthcare", "disability compensation", "most VA benefits"],
            "upgrade_path": True,
            "notes": (
                "A dishonorable discharge bars most VA benefits. "
                "This is not the end — a discharge upgrade may restore access. "
                "The Discharge Review Board (DRB) or Board for Correction of Military Records (BCMR) "
                "can review the discharge. Veterans law clinics provide this help at no cost."
            ),
        }

    if d == "other_than_honorable":
        return {
            "status": "LIMITED",
            "access": [
                "MST-related mental health care (no discharge barrier)",
                "Combat veteran 2-year healthcare window (if served in combat theater after 11/11/1998)",
                "Vet Centers (lower barrier — open to OTH for readjustment counseling)",
                "Discharge upgrade process (runs parallel to any claims)",
            ],
            "blocked": [
                "Standard VA healthcare enrollment (unless exceptions apply)",
                "Disability compensation (unless upgrade obtained)",
            ],
            "upgrade_path": True,
            "notes": (
                "OTH discharge limits access but does NOT close all doors. "
                "MST care and combat vet healthcare windows are open regardless. "
                "Pursue a discharge upgrade in parallel — DRB within 15 years of discharge, "
                "BCMR/BCNR at any time. Many OTH upgrades succeed, especially for PTSD/MST-related circumstances."
            ),
        }

    if d in ("honorable", "general", "unknown", ""):
        return {
            "status": "QUALIFIED",
            "access": ["Full VA healthcare and benefits access (standard eligibility rules apply)"],
            "blocked": [],
            "upgrade_path": False,
            "notes": (
                "Discharge type does not bar access. Standard eligibility rules apply. "
                "Specific program eligibility depends on service history, rating, and income."
            ) if d != "general" else (
                "General discharge qualifies for most VA benefits. "
                "A small number of programs require honorable — ask your VSO."
            ),
        }

    # Fallback
    return {
        "status": "QUALIFIED",
        "access": ["Assume standard access — verify discharge paperwork"],
        "blocked": [],
        "upgrade_path": False,
        "notes": "Discharge type unclear — proceed with standard routing. Verify DD-214.",
    }


def route_med_disability(profile: VetMedProfile) -> dict:
    """
    Primary routing engine for medical and disability needs.
    Gate 1 always runs first: discharge qualification check.
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
        "qualification": None,  # always populated
    }

    discharge_lower = (profile.discharge or "").lower()

    # ── GATE 1: QUALIFICATION CHECK — ALWAYS FIRST ───────────────────────────
    qualification = check_qualification(profile.discharge)
    result["qualification"] = qualification

    if qualification["status"] == "BLOCKED":
        result["primary_path"] = "Discharge Upgrade Review — required before VA benefits access"
        result["secondary_options"] = [
            "Discharge Review Board (DRB) — within 15 years of discharge",
            "Board for Correction of Military/Naval Records (BCMR/BCNR) — any time",
            "National Veterans Legal Services Program (NVLSP) — free legal help",
            "Veterans law clinic through a law school near you",
        ]
        result["flags"].append("dishonorable_hard_block")
        result["next_action"] = (
            "Contact a veterans law clinic or NVLSP (nvlsp.org) to start discharge upgrade. "
            "This is step one — no other VA process can move forward until discharge is upgraded."
        )
        result["notes"].append(qualification["notes"])
        return result

    if qualification["status"] == "LIMITED":
        result["flags"].append("oth_discharge_limited_eligibility")
        result["notes"].append(qualification["notes"])
        # Add upgrade path as a secondary but don't stop routing
        result["secondary_options"].append(
            "Discharge Upgrade (DRB or BCMR) — pursue in parallel to unlock full access"
        )

    # ── GATE 2 and beyond: full routing (only reached if QUALIFIED or LIMITED) ─

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
        # No early return — mental health track still runs below if flags set

    # ── TRACK 2: ENROLLED, NO RATING — FILE INITIAL CLAIM ────────────────────
    elif profile.va_status == "enrolled_no_rating" or "initial_claim" in profile.need_branches:
        # Independent-audit finding (2026-09-06), round 2: this track runs
        # BEFORE Track 3 (appeals) below and used to claim primary_path/
        # next_action unconditionally. Track 3's own assignment is correctly
        # guarded (`result[...] or (...)`) specifically so it never clobbers
        # whatever ran first -- but that's exactly what silently defeated it
        # here: this track already claimed both fields unconditionally, so
        # Track 3's guard always short-circuited to THIS track's value. The
        # comment on Track 3 below already claimed this track's guidance is
        # "preserved... this only adds the appeal-specific guidance on top"
        # -- true for secondary_options/key_forms/flags, false for
        # primary_path/next_action, which is the headline text a veteran
        # sees first. Confirmed with a probe: a denied veteran with new
        # evidence still got "file an initial claim" as primary_path, with
        # the Supplemental Claim guidance (no time limit) only ever
        # mentioned in notes[], after the wrong action was already given.
        # Fixed by not claiming primary_path/next_action here when
        # recent_denial is true, letting Track 3 claim them instead --
        # secondary_options/key_forms/flags/notes below are untouched by
        # this fix; they were never the bug, and VSO help / DD-214 matter
        # for an appeal too.
        if not profile.recent_denial:
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
        if not profile.recent_denial:
            result["next_action"] = (
                "File at va.gov/disability/file-disability-claim or visit your nearest VA Regional Office. "
                "Contact a VSO first — they are free and dramatically improve approval rates."
            )
        result["notes"].append(
            "Filing date matters — your effective date is the date VA receives your claim. "
            "File as soon as possible, even with incomplete evidence. You can add evidence later."
        )
        # No early return — mental health track still runs below if flags set

    # ── TRACK 3: HAS RATING — INCREASE / APPEALS ─────────────────────────────
    # recent_denial is an explicit OR here, not folded into va_status: a
    # veteran whose va_history is "denied" maps to va_status
    # "enrolled_no_rating" (they don't have a confirmed rating), which is
    # honest and correct -- but it meant this track, and the critical
    # "you have ONE YEAR from your decision letter" appeal-deadline warning
    # inside it, could only ever fire for someone who already has a rating.
    # A previously-denied veteran got Track 2's "file an initial claim"
    # guidance instead, with no mention of the appeal deadline at all.
    # Additive, not a replacement: Track 2 still runs for the same veteran
    # (va_status == "enrolled_no_rating") and its guidance is preserved
    # under this file's guarded result[...] = result[...] or (...)
    # convention -- this only adds the appeal-specific guidance on top.
    if profile.va_status in ("has_rating", "100_percent_PT") or profile.recent_denial:
        rating = profile.disability_rating or 0

        # Appeals track
        if "appeal" in profile.need_branches or profile.recent_denial:
            if profile.has_new_evidence:
                result["primary_path"] = result["primary_path"] or "Supplemental Claim (new evidence)"
                result["key_forms"].append("VA Form 20-0995 (Supplemental Claim)")
                result["next_action"] = result["next_action"] or (
                    "Submit new evidence (nexus letter, buddy statement, new diagnosis) "
                    "with VA Form 20-0995. No time limit."
                )
            else:
                result["primary_path"] = result["primary_path"] or "Higher-Level Review (HLR) — same evidence, senior reviewer"
                result["key_forms"].append("VA Form 20-0996 (Higher-Level Review)")
                result["next_action"] = result["next_action"] or (
                    "Request HLR within 1 year of denial with VA Form 20-0996. "
                    "No new evidence required — a senior reviewer re-examines the file."
                )
            # extend, never overwrite -- a veteran can simultaneously need
            # healthcare enrollment (Track 1) or an initial claim (Track 2)
            # AND an appeal; wiping their secondary_options here silently
            # dropped that earlier guidance (verified against the pre-fix
            # code: healthcare_enrollment + appeal together lost every
            # enrollment-related secondary_option and next_action, even
            # though "not_enrolled" stayed in flags and VA Form 10-10EZ
            # stayed orphaned in key_forms with nothing telling the veteran
            # what to do with it).
            result["secondary_options"].extend([
                "Board of Veterans Appeals (BVA) — direct review, evidence, or hearing lanes",
                "Accredited VA attorney or claims agent (fee only on back pay if you win)",
                "Veterans Service Organization (VSO) — free representation at BVA",
            ])
            result["flags"].append("appeals_track")
            result["notes"].append(
                "You have one year from your decision letter to request HLR or appeal to BVA. "
                "Supplemental Claim has no time limit if new evidence exists."
            )

        # Increase track
        elif "increase_claim" in profile.need_branches:
            result["primary_path"] = result["primary_path"] or "Rating Increase — Supplemental Claim or direct increase request"
            result["secondary_options"].extend([
                "VSO review of your current rating decision",
                "Private C&P exam (nexus letter strengthens increase)",
                "Buddy statements documenting worsening condition",
            ])
            result["key_forms"].append("VA Form 20-0995 or VA Form 21-526EZ (for new conditions)")
            result["flags"].append("increase_track")
            result["next_action"] = result["next_action"] or (
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
