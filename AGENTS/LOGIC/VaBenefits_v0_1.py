"""
VaBenefits_v0_1.py
SQUAD BAT — VA Benefits Division routing engine.
Covers non-medical, non-housing VA programs.

Tracks:
  1. Education & Training     — GI Bill, VR&E/Ch.31, VET TEC, Yellow Ribbon
  2. Employment & Transition  — TAP, SkillBridge, Job Centers, VA Work Study
  3. Home Loans & Adaptive    — VA Home Loan, SAH/SHA grants
  4. Financial & Pension      — VA Pension, VGLI, S-DVI life insurance
  5. Survivor & Dependent     — DIC, CHAMPVA, Fry Scholarship, Ch.35 DEA
  6. Burial & Memorial        — National Cemetery, burial allowance, headstone

Gate 1 (discharge) always runs first.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class VaBenefitsProfile:
    # Discharge character — gate 1
    # "honorable" | "general" | "other_than_honorable" | "dishonorable" | "unknown"
    discharge: str

    # Service era — affects GI Bill chapter eligibility
    # "post_9_11" | "gulf_war" | "vietnam" | "korea" | "peacetime" | "unknown"
    era: str = "unknown"

    # What they need help with (multi-select)
    # "education" | "voc_rehab" | "employment" | "transition" |
    # "home_loan" | "adaptive_housing" | "pension" | "life_insurance" |
    # "survivor_benefits" | "burial"
    need_branches: List[str] = field(default_factory=list)

    # Currently separating from active duty
    is_transitioning: bool = False

    # Service-connected disability rating (0–100 or None)
    disability_rating: Optional[int] = None

    # Wartime service (required for VA Pension)
    wartime_service: bool = False

    # Monthly income (for pension eligibility check)
    income_monthly: Optional[int] = None

    # Has dependents
    has_dependents: bool = False

    # Is a surviving spouse or dependent (for DIC, CHAMPVA, Fry)
    is_survivor_or_dependent: bool = False

    # Months since separation (affects VGLI enrollment window — must enroll within 1 yr)
    months_since_separation: Optional[int] = None

    # Location
    state: str = ""
    county: str = ""


# ── Qualification gate ────────────────────────────────────────────────────────

def check_qualification(discharge: str) -> dict:
    """Same gate pattern as MedDisability — discharge determines access level."""
    d = (discharge or "").lower().strip()

    if d == "dishonorable":
        return {
            "status": "BLOCKED",
            "notes": (
                "Dishonorable discharge bars access to most VA benefits including education, "
                "home loans, pension, and burial benefits. "
                "Discharge upgrade through DRB or BCMR/BCNR is the required first step. "
                "Free help: National Veterans Legal Services Program (nvlsp.org)."
            ),
        }
    if d == "other_than_honorable":
        return {
            "status": "LIMITED",
            "notes": (
                "OTH discharge limits access to many VA benefits. "
                "GI Bill, home loan, and pension typically require honorable or general discharge. "
                "Some programs remain accessible — VR&E may be available with SC disability. "
                "Discharge upgrade worth pursuing in parallel (DRB within 15 yrs, BCMR any time)."
            ),
        }
    return {
        "status": "QUALIFIED",
        "notes": (
            "Discharge type does not bar access. Eligibility determined by program-specific criteria."
            if d != "general"
            else "General discharge qualifies for most benefits. A small number require honorable — ask your VSO."
        ),
    }


# ── Main router ───────────────────────────────────────────────────────────────

def route_va_benefits(profile: VaBenefitsProfile) -> dict:
    result = {
        "primary_path": None,
        "secondary_options": [],
        "flags": [],
        "next_action": None,
        "key_forms": [],
        "notes": [],
        "qualification": None,
    }

    # ── GATE 1: DISCHARGE ─────────────────────────────────────────────────────
    qual = check_qualification(profile.discharge)
    result["qualification"] = qual

    if qual["status"] == "BLOCKED":
        result["primary_path"] = "Discharge Upgrade Required — most VA benefits inaccessible"
        result["secondary_options"] = [
            "Discharge Review Board (DRB) — within 15 years of discharge",
            "Board for Correction of Military/Naval Records (BCMR/BCNR) — any time",
            "National Veterans Legal Services Program (NVLSP) — nvlsp.org",
        ]
        result["flags"].append("dishonorable_hard_block")
        result["next_action"] = "Contact NVLSP or a veterans law clinic before any other step."
        result["notes"].append(qual["notes"])
        return result

    if qual["status"] == "LIMITED":
        result["flags"].append("oth_limited_eligibility")
        result["notes"].append(qual["notes"])
        result["secondary_options"].append(
            "Discharge Upgrade (DRB or BCMR) — pursue in parallel to restore full access"
        )

    rating = profile.disability_rating or 0

    # ── TRACK 1: EDUCATION & TRAINING ─────────────────────────────────────────
    if "education" in profile.need_branches or "voc_rehab" in profile.need_branches:

        # VR&E (Chapter 31) check FIRST — often more valuable than GI Bill
        if "voc_rehab" in profile.need_branches or (rating >= 10):
            result["secondary_options"].append(
                "VR&E / Chapter 31 — Veteran Readiness & Employment: "
                "pays tuition + monthly housing allowance + books, no GI Bill entitlement used. "
                "Available at 10%+ SC rating with employment barrier."
            )
            result["key_forms"].append("VA Form 28-1900 (VR&E Application)")
            result["flags"].append("vre_candidate")
            result["notes"].append(
                "VR&E (Ch.31) is often overlooked and more valuable than GI Bill for rated veterans — "
                "it pays full costs and does not draw down your 36-month GI Bill entitlement. "
                "Ask your VSO to compare both before choosing."
            )

        # GI Bill routing by era
        if "education" in profile.need_branches:
            era = (profile.era or "").lower()
            if era == "post_9_11" or era == "unknown":
                result["primary_path"] = "Post-9/11 GI Bill (Chapter 33) — tuition + housing allowance + books"
                result["secondary_options"].insert(0,
                    "Yellow Ribbon Program — if attending private school or out-of-state public; "
                    "fills gap above GI Bill cap at participating schools"
                )
                result["key_forms"].append("VA Form 22-1990 (Education Benefits Application)")
                result["flags"].append("ch33_candidate")
                result["next_action"] = (
                    "Apply at va.gov/education/apply-for-education-benefits. "
                    "Check if your school participates in Yellow Ribbon if costs exceed GI Bill cap. "
                    "Compare with VR&E if you have a SC rating — may be the better choice."
                )
            else:
                result["primary_path"] = "Montgomery GI Bill (Chapter 30) — check entitlement remaining"
                result["key_forms"].append("VA Form 22-1990 (Education Benefits Application)")
                result["flags"].append("ch30_candidate")
                result["next_action"] = (
                    "Apply at va.gov/education/apply-for-education-benefits. "
                    "If you served post-9/11 even briefly, check Ch.33 eligibility — it may be available."
                )

            result["secondary_options"].append(
                "VET TEC — tech-focused training (coding, data, IT, cybersecurity). "
                "Uses GI Bill entitlement but high-paying field outcomes. "
                "Program list at va.gov/education/about-gi-bill-benefits/how-to-use-benefits/vettec-high-tech-program"
            )

        # Survivors / dependents education
        if profile.is_survivor_or_dependent:
            result["secondary_options"].append(
                "Chapter 35 DEA (Dependents' Educational Assistance) — for dependents of 100% rated or deceased vets"
            )
            result["secondary_options"].append(
                "Fry Scholarship — for children/spouses of service members who died in the line of duty"
            )
            result["flags"].append("dependent_education_programs")

    # ── TRACK 2: EMPLOYMENT & TRANSITION ──────────────────────────────────────
    if "employment" in profile.need_branches or "transition" in profile.need_branches:

        if profile.is_transitioning:
            result["primary_path"] = result["primary_path"] or "TAP (Transition Assistance Program) + SkillBridge"
            result["secondary_options"].append(
                "SkillBridge — work with a civilian employer for up to 180 days before separation, "
                "while still receiving military pay and benefits"
            )
            result["secondary_options"].append(
                "TAP (Transition Assistance Program) — mandatory pre-separation program; "
                "use it, don't skip the optional sessions"
            )
            result["flags"].append("transitioning_service_member")
            result["next_action"] = result["next_action"] or (
                "Connect with your installation's TAP office immediately. "
                "Apply for SkillBridge at skillbridge.osd.mil — many programs are remote."
            )
        else:
            result["primary_path"] = result["primary_path"] or "American Job Center — priority service for veterans"
            result["secondary_options"].append(
                "American Job Centers (careeronestop.org/veterans) — "
                "free job search, training funds, resume help; veterans receive priority service"
            )
            result["secondary_options"].append(
                "DOL VETS programs — Homeless Veterans' Reintegration Program (HVRP), "
                "Transition Employment Assistance for Military (TEAM)"
            )
            result["secondary_options"].append(
                "VA Work Study — paid work at VA facilities while in school on GI Bill"
            )
            result["flags"].append("employment_track")
            result["next_action"] = result["next_action"] or (
                "Find your nearest American Job Center at careeronestop.org and ask specifically "
                "for the veterans employment representative (LVER or DVOP)."
            )
            result["notes"].append(
                "Ask specifically for the LVER (Local Veterans Employment Representative) or "
                "DVOP (Disabled Veterans Outreach Program specialist) at your Job Center — "
                "they have access to resources the general staff do not."
            )

    # ── TRACK 3: HOME LOANS & ADAPTIVE HOUSING ────────────────────────────────
    if "home_loan" in profile.need_branches or "adaptive_housing" in profile.need_branches:

        if "home_loan" in profile.need_branches:
            result["primary_path"] = result["primary_path"] or "VA Home Loan Guarantee — 0% down, no PMI"
            result["secondary_options"].append(
                "VA Home Loan — no down payment, no private mortgage insurance, "
                "competitive rates, reusable benefit (can use multiple times)"
            )
            result["key_forms"].append("VA Form 26-1880 (Certificate of Eligibility)")
            result["flags"].append("home_loan_candidate")
            result["next_action"] = result["next_action"] or (
                "Request your Certificate of Eligibility (COE) at va.gov/housing-assistance/home-loans "
                "or through any VA-approved lender. The lender can often pull it directly."
            )
            result["notes"].append(
                "The VA Home Loan benefit is reusable — most vets don't know this. "
                "If you had a VA loan before, you may have remaining or restored entitlement."
            )

        if "adaptive_housing" in profile.need_branches or rating >= 50:
            result["secondary_options"].append(
                "SAH Grant (Specially Adapted Housing) — up to $109,986 to build or modify a home "
                "for veterans with severe service-connected disability"
            )
            result["secondary_options"].append(
                "SHA Grant (Special Home Adaptation) — up to $22,036 for less severe adaptation needs"
            )
            result["key_forms"].append("VA Form 26-4555 (Adaptive Housing Grant Application)")
            result["flags"].append("adaptive_housing_candidate")

    # ── TRACK 4: FINANCIAL & PENSION ──────────────────────────────────────────
    if "pension" in profile.need_branches or "life_insurance" in profile.need_branches:

        # VA Pension — non-SC, low income, wartime service
        if "pension" in profile.need_branches:
            if profile.wartime_service and (profile.income_monthly is None or profile.income_monthly < 2000):
                result["primary_path"] = result["primary_path"] or "VA Pension — non-service-connected, wartime, low income"
                result["key_forms"].append("VA Form 21P-527EZ (VA Pension Application)")
                result["flags"].append("pension_candidate")
                result["next_action"] = result["next_action"] or (
                    "Apply at va.gov/pension/apply-for-veteran-pension or visit your VA Regional Office. "
                    "Contact a VSO first — pension claims are complex and VSOs are free."
                )
                result["notes"].append(
                    "VA Pension is based on financial need, NOT service-connected disability. "
                    "Wartime service required (does not mean combat — defined by service dates). "
                    "Aid & Attendance supplement available if you need help with daily activities."
                )
            else:
                result["secondary_options"].append(
                    "VA Pension — worth checking eligibility even if income seems above threshold; "
                    "unreimbursed medical expenses can reduce countable income significantly"
                )
                result["flags"].append("pension_check_recommended")

        # Life insurance
        if "life_insurance" in profile.need_branches:
            months = profile.months_since_separation
            if months is not None and months <= 12:
                result["primary_path"] = result["primary_path"] or "VGLI — Veterans Group Life Insurance (enroll NOW — 1-year window)"
                result["flags"].append("vgli_window_open")
                result["notes"].append(
                    "VGLI enrollment window is 1 year from separation. "
                    "No medical exam required if enrolled within 240 days. "
                    "Do not miss this window — it closes permanently."
                )
                result["key_forms"].append("VGLI Application — online at benefits.va.gov/insurance/vgli.asp")
            elif months is not None and months > 12:
                result["secondary_options"].append(
                    "VGLI enrollment window has passed (1 year from separation). "
                    "S-DVI (Service-Disabled Veterans Life Insurance) may still be available "
                    "if you have a new SC disability — apply within 2 years of rating."
                )
                result["flags"].append("vgli_window_closed")
            else:
                result["secondary_options"].append(
                    "VGLI (Veterans Group Life Insurance) — convert from SGLI within 1 year of separation. "
                    "S-DVI available for rated veterans within 2 years of SC disability rating."
                )

    # ── TRACK 5: SURVIVOR & DEPENDENT BENEFITS ────────────────────────────────
    if "survivor_benefits" in profile.need_branches or profile.is_survivor_or_dependent:
        result["primary_path"] = result["primary_path"] or "Survivor & Dependent Benefits Review"
        result["secondary_options"].extend([
            "DIC (Dependency and Indemnity Compensation) — monthly payment to surviving spouse/children "
            "if veteran died from SC condition or was 100% P&T for 10+ years before death",
            "CHAMPVA — health insurance for dependents of 100% rated or deceased veterans; "
            "covers 75% of costs after deductible",
            "Survivors Pension — for surviving spouses of wartime veterans with limited income",
            "Chapter 35 DEA — education benefits for dependents",
            "Fry Scholarship — for children/spouses of members who died in line of duty",
        ])
        result["key_forms"].extend([
            "VA Form 21P-534EZ (Survivors Pension / DIC)",
            "VA Form 10-10d (CHAMPVA Application)",
        ])
        result["flags"].append("survivor_dependent_track")
        result["next_action"] = result["next_action"] or (
            "Contact your nearest VA Regional Office or a VSO immediately. "
            "DIC has no time limit but Survivors Pension income thresholds change annually — file promptly."
        )

    # ── TRACK 6: BURIAL & MEMORIAL ────────────────────────────────────────────
    if "burial" in profile.need_branches:
        result["primary_path"] = result["primary_path"] or "National Cemetery Burial Eligibility"
        result["secondary_options"].extend([
            "National Cemetery burial — veteran and eligible dependents; no cost for burial in national cemetery",
            "Presidential Memorial Certificate — formal recognition, apply at va.gov",
            "Burial allowance — if veteran died of SC condition or while receiving VA care: "
            "up to $796 burial + $796 plot allowance (rates change annually)",
            "Headstone or marker — government-furnished, any cemetery; apply at va.gov/burials-memorials",
            "Pre-need eligibility determination — establish eligibility before it's needed; "
            "spares family the process at worst moment",
        ])
        result["key_forms"].extend([
            "VA Form 40-10007 (Pre-need Eligibility)",
            "VA Form 21P-530EZ (Burial Benefits Application)",
        ])
        result["flags"].append("burial_track")
        result["next_action"] = result["next_action"] or (
            "Call the National Cemetery Scheduling Office: 1-800-535-1117. "
            "For burial allowance, file within 2 years of burial. "
            "Pre-need determination can be done now at va.gov/burials-memorials."
        )
        result["notes"].append(
            "Discharge must be honorable or general for national cemetery burial. "
            "OTH discharge bars national cemetery burial but not all memorial benefits."
        )

    # ── FALLBACK ──────────────────────────────────────────────────────────────
    if not result["primary_path"]:
        result["primary_path"] = "VA Benefits Review — contact a VSO for full eligibility check"
        result["next_action"] = (
            "Call 1-800-827-1000 or visit va.gov to connect with your VA Regional Office. "
            "A VSO (DAV, VFW, American Legion) reviews your full picture at no cost."
        )

    return result
