"""
WomenVeterans_v0_1.py
SQUAD BAT — Women Veterans Division routing engine.

Tracks:
  1. Women's Health Care    — VA women's health programs, primary care, specialty
  2. Maternity & Newborn    — pregnancy coverage, delivery, newborn care period
  3. MST-Specific           — dedicated MST care, no report required
  4. Mental Health          — MST-related PTSD, gender-responsive programs
  5. Reproductive Health    — contraception, fertility, menopause, cancer screenings
  6. Housing & Homelessness — women veteran-specific housing programs
  7. Childcare Access       — childcare during VA appointments
  8. Women Veterans Orgs    — advocacy, peer support, VSOs specific to women

Design note: VA historically underserved women veterans. Every path here leads
to a specific resource — no generic "contact VA" without a named program.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class WomenVetProfile:
    # What she needs (multi-select)
    # "healthcare" | "maternity" | "mst" | "mental_health" | "reproductive_health" |
    # "housing" | "childcare" | "peer_support" | "benefits_help"
    needs: List[str] = field(default_factory=list)

    # Enrolled in VA health care
    enrolled_va_healthcare: bool = False

    # Currently pregnant
    is_pregnant: bool = False

    # Has children under 12 (childcare relevance)
    has_young_children: bool = False

    # MST survivor
    has_mst: bool = False

    # Mental health flags
    has_ptsd: bool = False
    has_depression_anxiety: bool = False

    # Housing situation
    # "stable" | "at_risk" | "homeless" | "unknown"
    housing_situation: str = "unknown"

    # Disability rating
    disability_rating: Optional[int] = None

    # Discharge character
    discharge: str = "unknown"

    # Location
    state: str = ""
    county: str = ""


# ── Main router ───────────────────────────────────────────────────────────────

def route_women_veterans(profile: WomenVetProfile) -> dict:
    result = {
        "primary_path": None,
        "secondary_options": [],
        "flags": [],
        "next_action": None,
        "key_resources": [],
        "key_forms": [],
        "notes": [],
    }

    needs = [n.lower() for n in profile.needs]

    # ── ALWAYS: WOMEN VETERANS PROGRAM MANAGER ────────────────────────────────
    # Every VA facility has one — this is the universal first contact
    result["key_resources"].append(
        "Women Veterans Program Manager (WVPM) — every VA facility has one. "
        "Your advocate inside the system. Ask for them by name at your VA."
    )
    result["key_resources"].append(
        "Women Veterans Call Center — 1-855-829-6636 (M–F 8am–10pm ET, Sat 8am–6:30pm ET). "
        "Direct line, trained specifically for women veterans."
    )

    # ── TRACK 6 (evaluated early): HOUSING & HOMELESSNESS ─────────────────────
    # Runs BEFORE the healthcare-enrollment nudge below on purpose: a veteran
    # who is currently homeless needs "call the homeless hotline now" as her
    # next_action, not "call to enroll in VA healthcare" — a genuine crisis
    # must win the shared next_action/primary_path fields regardless of code
    # order. (Previously Track 1 ran first and set both fields unconditionally,
    # so an unenrolled + currently-homeless veteran silently got the
    # enrollment nudge as next_action instead of the homeless hotline —
    # verified against the pre-fix code before this reorder.)
    if "housing" in needs or profile.housing_situation in ("homeless", "at_risk"):
        result["flags"].append("housing_track")
        result["primary_path"] = result["primary_path"] or "Women Veterans Housing"

        result["secondary_options"].extend([
            "HUD-VASH — VA-supported housing voucher program. Women veterans are eligible. "
            "Single women with children receive priority consideration at many CoCs. "
            "Contact your VA social worker or call 1-877-4AID-VET (1-877-424-3838).",
            "SSVF (Supportive Services for Veteran Families) — "
            "specifically designed for veteran families including single mothers. "
            "Rapid rehousing and prevention funds. Find grantees at va.gov/homeless/ssvf",
            "Women veteran-specific shelters — VA has expanded women-only shelter capacity. "
            "Call 1-877-424-3838 (VA homeless hotline) and specifically ask for women-only options.",
            "Childcare support in transitional housing — if you have children, ask specifically "
            "about programs that accommodate families. Many VA transitional housing programs do.",
        ])
        result["key_resources"].extend([
            "VA Homeless Veterans Hotline — 1-877-424-3838",
            "SSVF Grantee Finder — va.gov/homeless/ssvf",
        ])
        if profile.housing_situation == "homeless":
            result["flags"].append("homeless_urgent")
            result["next_action"] = result["next_action"] or (
                "Call VA Homeless Veterans Hotline NOW: 1-877-424-3838. "
                "Ask specifically for women veteran services and whether women-only shelter is available."
            )

    # ── TRACK 1: WOMEN'S HEALTH CARE ──────────────────────────────────────────
    if "healthcare" in needs or not profile.enrolled_va_healthcare:
        result["flags"].append("womens_healthcare_track")

        if not profile.enrolled_va_healthcare:
            result["primary_path"] = result["primary_path"] or "VA Women's Health Care — Enroll First"
            result["secondary_options"].append(
                "VA enrollment for women veterans: va.gov/health-care/apply — "
                "same eligibility rules as all veterans. "
                "Once enrolled, request a Women's Health primary care provider specifically — "
                "VA has designated Women's Health PCPs at most facilities."
            )
            result["key_forms"].append("VA Form 10-10EZ (VA Health Care Application)")
            result["next_action"] = result["next_action"] or (
                "Call the Women Veterans Call Center (1-855-829-6636) to start enrollment — "
                "they can walk you through the process and connect you to your facility's WVPM."
            )
        else:
            result["primary_path"] = result["primary_path"] or "VA Women's Health Services"
            result["secondary_options"].append(
                "VA Women's Health primary care — request a provider trained in women's health specifically. "
                "VA policy requires that every enrolled woman veteran be offered a designated WHPCP."
            )
            result["notes"].append(
                "You have the right to request a same-sex provider for sensitive exams. "
                "Ask your WVPM if you experience any barrier to this."
            )

        result["secondary_options"].append(
            "Telehealth for women's health — VA's Women's Health Telehealth Hubs connect rural "
            "women veterans to women's health specialists remotely. Ask your WVPM."
        )

    # ── TRACK 2: MATERNITY & NEWBORN ──────────────────────────────────────────
    if "maternity" in needs or profile.is_pregnant:
        result["flags"].append("maternity_track")
        result["primary_path"] = result["primary_path"] or "VA Maternity Care"

        result["secondary_options"].extend([
            "VA maternity care — VA covers pregnancy care, delivery (at non-VA facility if needed), "
            "and newborn care for 7 days after birth. Enrolled veterans receive this at no cost. "
            "Notify your VA provider immediately upon learning you are pregnant.",
            "Community Care maternity — VA contracts with OB/GYN providers in your community "
            "if VA cannot provide care directly or you prefer a community provider.",
            "Newborn care — VA covers newborn care for 7 days post-delivery at no cost to the veteran. "
            "After 7 days, newborn must be covered by other insurance or CHAMPVA if applicable.",
        ])
        result["key_resources"].append(
            "VA Maternity Care Coordination — va.gov/health-care/health-needs-conditions/reproductive-health/maternity-care"
        )
        result["notes"].append(
            "Maternity care coordinator — every VA facility with a significant women veteran population "
            "has a Maternity Care Coordinator. Request one through your WVPM or Women's Health PCP. "
            "They navigate the VA/community care interface so you don't have to."
        )
        if not result["next_action"]:
            result["next_action"] = (
                "Contact your VA Women's Health primary care provider immediately. "
                "If not enrolled, call 1-855-829-6636 (Women Veterans Call Center) today."
            )

    # ── TRACK 3: MST ──────────────────────────────────────────────────────────
    if "mst" in needs or profile.has_mst:
        result["flags"].append("mst_track")
        result["primary_path"] = result["primary_path"] or "MST — Care Without Report"

        result["secondary_options"].extend([
            "VA MST care — free, confidential, NO in-service report required. "
            "This is federal law. No co-pays for conditions related to MST. "
            "Access through any VA facility — ask for the MST Coordinator.",
            "Safe Helpline — 1-800-773-7927 — confidential DoD support for sexual assault survivors. "
            "Available 24/7, staffed by trained advocates.",
            "MST outpatient programs — VA has MST-specialized outpatient mental health programs "
            "at many facilities. Residential programs also exist for severe PTSD related to MST.",
            "Disability claim for MST-related conditions — VA presumes PTSD related to MST "
            "is service-connected without requiring corroborating in-service evidence. "
            "Buddy statements, behavioral changes, medical records, and your own statement can suffice.",
        ])
        result["key_resources"].extend([
            "VA MST Support — va.gov/health-care/health-needs-conditions/military-sexual-trauma",
            "Safe Helpline — 1-800-773-7927",
            "Protect Our Defenders — protectourdefenders.com",
            "Service Women's Action Network — servicewomen.org",
        ])
        result["notes"].append(
            "You do not need to have reported the MST in service. "
            "You do not need a buddy statement, but it helps. "
            "Your own statement, combined with documented behavioral changes, is often sufficient. "
            "Get a VSO who specializes in MST claims — it matters."
        )
        if not result["next_action"]:
            result["next_action"] = (
                "Contact your VA facility's MST Coordinator — "
                "ask for them by name at any VA medical center. "
                "Alternatively call the Women Veterans Call Center: 1-855-829-6636."
            )

    # ── TRACK 4: MENTAL HEALTH ────────────────────────────────────────────────
    if "mental_health" in needs or profile.has_ptsd or profile.has_depression_anxiety:
        result["flags"].append("mental_health_track")
        result["primary_path"] = result["primary_path"] or "Women Veterans Mental Health"

        result["secondary_options"].extend([
            "VA Women's Mental Health — gender-responsive, trauma-informed programs. "
            "Request a women-only group or women's mental health specialist specifically — "
            "this makes a documented difference in outcomes.",
            "Vet Centers — community-based, less clinical, often more accessible than VA hospitals. "
            "Veterans do not need to be enrolled in VA health care to use Vet Centers. "
            "Find at va.gov/find-locations (select Vet Center).",
            "Crisis line — 988, press 1. Text 838255. Chat at veteranscrisisline.net.",
            "Women Veterans Interactive Network (WoVeN) — peer support from other women veterans. "
            "va.gov/WOMEN VETERANS/ProgramOverview.asp",
        ])
        if profile.has_ptsd:
            result["secondary_options"].append(
                "PTSD treatment — VA's National Center for PTSD (ptsd.va.gov) has evidence-based "
                "treatment programs. CPT (Cognitive Processing Therapy) and PE (Prolonged Exposure) "
                "are gold standard. Women-only groups available at many facilities."
            )
            result["flags"].append("ptsd_track")

        result["key_resources"].append("VA National Center for PTSD — ptsd.va.gov")
        if not result["next_action"]:
            result["next_action"] = (
                "Contact your VA facility or local Vet Center. "
                "For immediate support: 988 press 1, text 838255."
            )

    # ── TRACK 5: REPRODUCTIVE HEALTH ──────────────────────────────────────────
    if "reproductive_health" in needs:
        result["flags"].append("reproductive_health_track")
        result["primary_path"] = result["primary_path"] or "VA Reproductive Health Services"

        result["secondary_options"].extend([
            "Cervical cancer screening (Pap smear) — covered, no co-pay for enrolled veterans.",
            "Mammography — covered for enrolled women veterans, schedule through your WHPCP.",
            "Contraception — VA provides contraceptive counseling and supplies at no cost.",
            "Fertility / infertility — VA covers certain fertility treatments for veterans with "
            "SC reproductive injury. Ask your WHPCP about eligibility.",
            "Menopause care — hormone therapy, counseling, and management through WHPCP.",
            "Ovarian and uterine cancer screening — discuss risk-based screening with your WHPCP. "
            "PACT Act expanded toxic exposure benefits may be relevant if you served near burn pits.",
        ])
        result["notes"].append(
            "PACT Act (2022) expanded cancer-related benefits significantly. "
            "If you have or had reproductive cancer and served after 1990, ask about PACT Act eligibility."
        )
        if not result["next_action"]:
            result["next_action"] = (
                "Request an appointment with a VA Women's Health Primary Care Provider. "
                "Call 1-855-829-6636 (Women Veterans Call Center) if you need help getting scheduled."
            )

    # ── TRACK 7: CHILDCARE ACCESS ─────────────────────────────────────────────
    if "childcare" in needs or profile.has_young_children:
        result["flags"].append("childcare_track")
        result["secondary_options"].extend([
            "VA Caregiver Support — if your child has special needs or you are also a caregiver, "
            "VA has support programs. Ask your WVPM.",
            "Child Care Aware of America — childcareaware.org — "
            "military/veteran childcare subsidy programs and Child Development Centers.",
            "DoD Child Development Centers — if near a military installation, some have spaces "
            "for veterans' children. Check Military OneSource: militaryonesource.mil",
            "VA appointment childcare — some VA facilities offer waiting room childcare. "
            "Ask your WVPM if this is available at your facility.",
        ])
        result["notes"].append(
            "Childcare during VA appointments is a documented barrier for women veterans. "
            "Your WVPM can sometimes advocate for telehealth or alternate scheduling to reduce this burden."
        )

    # ── TRACK 8: PEER SUPPORT & ORGS ──────────────────────────────────────────
    if "peer_support" in needs:
        result["flags"].append("peer_support_track")
        result["primary_path"] = result["primary_path"] or "Women Veterans Peer Support & Advocacy"
        result["secondary_options"].extend([
            "Service Women's Action Network (SWAN) — servicewomen.org — "
            "advocacy, legal resources, peer community for active duty and veteran women.",
            "Final Salute Inc. — finalsaluteinc.org — housing and support specifically for women veterans.",
            "Women Veterans Interactive (WoVeN) — VA-run peer support network for women veterans.",
            "Veteran Women Igniting the Spirit of Entrepreneurship (VWISE) — "
            "Syracuse IVmF business training for women veteran entrepreneurs.",
            "American Legion Women Veterans programs — legion.org",
            "DAV Women Veterans programs — dav.org",
        ])
        result["key_resources"].append("Service Women's Action Network — servicewomen.org")

    # ── BENEFITS HELP ──────────────────────────────────────────────────────────
    if "benefits_help" in needs:
        result["flags"].append("benefits_help_track")
        result["secondary_options"].extend([
            "Women-veteran-knowledgeable VSOs — specifically ask for a VSO who has experience "
            "with women veteran claims (MST-related, reproductive injury, etc.). "
            "Not all VSO reps have this background — advocate for yourself.",
            "NVLSP — nvlsp.org — legal help for VA benefits denials, including MST claims.",
            "VA Regional Office — request women veteran services specifically.",
        ])

    # ── FALLBACK ──────────────────────────────────────────────────────────────
    if not result["primary_path"]:
        result["primary_path"] = "Women Veterans Services — Dedicated Support Available"
        result["next_action"] = (
            "Call the Women Veterans Call Center: 1-855-829-6636. "
            "Ask for your facility's Women Veterans Program Manager."
        )

    return result
