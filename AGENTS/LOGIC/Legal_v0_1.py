"""
Legal_v0_1.py
SQUAD BAT — Legal Division routing engine.

Tracks:
  1. Discharge Upgrade        — DRB, BCMR/BCNR, Character of Discharge review
  2. VA Benefits Appeals      — HLR, Supplemental Claim, BVA, CAVC
  3. Military Sexual Trauma   — MST legal resources, disability claims, discharge upgrade
  4. Civilian Legal Aid       — housing, employment, family law, consumer protection
  5. Records Correction       — DD-214 errors, military records
  6. Predatory Lending        — scam VSOs, benefits poachers, accredited rep access

Gate: Legal issues never block — every veteran gets a path.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class VetLegalProfile:
    # What legal issue(s) they face (multi-select)
    # "discharge_upgrade" | "va_appeal" | "mst" | "civilian_legal" |
    # "records_correction" | "predatory_lending" | "benefits_denial"
    legal_needs: List[str] = field(default_factory=list)

    # Discharge character — affects upgrade pathway
    discharge: str = "unknown"

    # Years since discharge (affects DRB vs BCMR availability)
    years_since_discharge: Optional[int] = None

    # Branch of service
    branch: str = "unknown"

    # VA claim denied or rated low
    has_denied_claim: bool = False

    # Which VA appeals lane they're in (if any)
    # "none" | "hlr" | "supplemental" | "bva" | "cavc" | "unknown"
    appeals_lane: str = "none"

    # Military Sexual Trauma
    has_mst: bool = False

    # Civilian legal issue type
    # "housing" | "employment" | "family" | "consumer" | "criminal_record" | "other"
    civilian_issue: str = ""

    # Was charged or faced NJP (affects discharge upgrade framing)
    has_ucmj_history: bool = False

    # Location
    state: str = ""
    county: str = ""


# ── Main router ───────────────────────────────────────────────────────────────

def route_legal(profile: VetLegalProfile) -> dict:
    result = {
        "primary_path": None,
        "secondary_options": [],
        "flags": [],
        "next_action": None,
        "key_resources": [],
        "key_forms": [],
        "notes": [],
    }

    needs = [n.lower() for n in profile.legal_needs]

    # ── TRACK 1: DISCHARGE UPGRADE ────────────────────────────────────────────
    if "discharge_upgrade" in needs or profile.discharge in ("other_than_honorable", "dishonorable"):
        discharge = (profile.discharge or "").lower()
        years = profile.years_since_discharge

        result["primary_path"] = "Discharge Upgrade — DRB or BCMR/BCNR"
        result["flags"].append("discharge_upgrade_track")

        # DRB — available within 15 years
        if years is None or years <= 15:
            result["secondary_options"].append(
                "Discharge Review Board (DRB) — available within 15 years of discharge. "
                "Can upgrade character of discharge. Cannot change reason for separation. "
                "Free to file. Apply at milconnect.dmdc.osd.mil or mail DD Form 293."
            )
            result["key_forms"].append("DD Form 293 (DRB Application)")

        # BCMR/BCNR — available any time
        result["secondary_options"].append(
            "Board for Correction of Military/Naval Records (BCMR/BCNR) — available ANY time after discharge. "
            "Can correct errors, change reason for separation, upgrade character. "
            "Stronger board — use this if DRB is unavailable or denied. "
            "Apply at DD Form 149."
        )
        result["key_forms"].append("DD Form 149 (BCMR/BCNR Application)")

        # MST connection
        if profile.has_mst or "mst" in needs:
            result["notes"].append(
                "MST-related discharges are subject to heightened scrutiny under DoD policy. "
                "Boards must give 'liberal consideration' to upgrade requests connected to MST, PTSD, or TBI. "
                "Document the connection clearly in your application."
            )
            result["flags"].append("mst_discharge_upgrade")

        result["key_resources"].extend([
            "National Veterans Legal Services Program (NVLSP) — nvlsp.org — free legal help",
            "Swords to Plowshares — swords-to-plowshares.org — West Coast focus",
            "National Lawyers Guild Military Law Task Force — nlg-mltf.org",
            "Your state's Legal Aid organization — search at lawhelp.org",
        ])
        result["next_action"] = (
            "Contact NVLSP or a veterans law clinic before filing — "
            "a lawyer reviewing your records can significantly improve your outcome. "
            "All listed resources are free to veterans."
        )
        result["notes"].append(
            "Discharge upgrade is not just about VA benefits — it affects housing, employment, "
            "and federal contracting eligibility. Even a partial upgrade (reason for separation) "
            "can restore access to programs."
        )

    # ── TRACK 2: VA BENEFITS APPEALS ──────────────────────────────────────────
    if "va_appeal" in needs or "benefits_denial" in needs or profile.has_denied_claim:
        lane = (profile.appeals_lane or "none").lower()

        if lane == "none" or lane == "unknown":
            result["primary_path"] = result["primary_path"] or "VA Appeals — Three Lanes Available"
            result["secondary_options"].extend([
                "Supplemental Claim — submit new and relevant evidence; VA must reconsider. "
                "Best first step if you have new medical records, buddy statements, or nexus letters.",
                "Higher-Level Review (HLR) — senior VA reviewer re-examines the same evidence. "
                "No new evidence allowed. Use if you believe VA made a clear error.",
                "Board of Veterans Appeals (BVA) — formal appeal to the Board. "
                "Three options: Direct Review, Evidence Submission, or Hearing. "
                "Can take 1–5 years. Get a VSO or accredited attorney before filing.",
            ])
            result["key_forms"].extend([
                "VA Form 20-0995 (Supplemental Claim)",
                "VA Form 20-0996 (Higher-Level Review)",
                "VA Form 10182 (BVA Appeal — Notice of Disagreement)",
            ])
            result["flags"].append("appeals_lane_not_selected")
            result["notes"].append(
                "You generally have 1 year from a VA decision to appeal without losing your effective date. "
                "The supplemental claim lane is fastest if you have new evidence. "
                "Talk to an accredited VSO or attorney before choosing — the lane affects your timeline and rights."
            )
        elif lane == "bva":
            result["primary_path"] = result["primary_path"] or "BVA Appeal in Progress"
            result["notes"].append(
                "BVA appeals can take years. Consider filing a Supplemental Claim in parallel "
                "if new evidence becomes available — it does not affect your BVA appeal."
            )
            result["secondary_options"].append(
                "U.S. Court of Appeals for Veterans Claims (CAVC) — "
                "if BVA denies, you have 120 days to appeal to CAVC. "
                "This requires an accredited attorney — free representation available through NVLSP."
            )
        elif lane == "cavc":
            result["primary_path"] = result["primary_path"] or "CAVC Appeal — Accredited Attorney Required"
            result["key_resources"].append(
                "NVLSP (nvlsp.org) — free CAVC representation for veterans"
            )
            result["flags"].append("cavc_track_attorney_required")

        result["key_resources"].extend([
            "VA.gov Appeals Status — va.gov/decision-reviews",
            "DAV (Disabled American Veterans) — free VSO representation — va.gov/ogc/apps/accreditation/",
            "VFW National Veterans Service — vfw.org",
        ])
        if not result["next_action"]:
            result["next_action"] = (
                "Contact an accredited VSO or veterans law clinic before your appeal deadline. "
                "Find accredited representatives at va.gov/ogc/apps/accreditation/."
            )

    # ── TRACK 3: MILITARY SEXUAL TRAUMA ───────────────────────────────────────
    if "mst" in needs or profile.has_mst:
        result["flags"].append("mst_track")
        result["primary_path"] = result["primary_path"] or "MST — Legal + Benefits Support"

        result["secondary_options"].extend([
            "VA MST Coordinator — every VA facility has one; free, confidential, no report required to access care. "
            "Call 1-800-827-1000 to connect with your local coordinator.",
            "MST-related PTSD/disability claim — VA presumes service connection for conditions related to MST; "
            "does not require an in-service report. Evidence: buddy statements, behavioral changes, medical records.",
            "Safe Helpline — 1-800-773-7927 — DoD confidential sexual assault support",
            "DoD SAPRO — sapr.mil — resources for active duty and veterans",
        ])
        result["key_resources"].extend([
            "VA MST Support — va.gov/health-care/health-needs-conditions/military-sexual-trauma",
            "Protect Our Defenders — protectourdefenders.com — advocacy + legal resources",
            "Service Women's Action Network — servicewomen.org",
        ])
        result["notes"].append(
            "VA treats all veterans for MST-related conditions at no cost, regardless of discharge status. "
            "No formal report is required. You do not need to have reported it in service."
        )
        if not result["next_action"]:
            result["next_action"] = (
                "Contact your VA facility's MST Coordinator — they are your first, safest point of contact. "
                "Call 1-800-827-1000 and ask specifically for the MST Coordinator."
            )

    # ── TRACK 4: CIVILIAN LEGAL AID ───────────────────────────────────────────
    if "civilian_legal" in needs or profile.civilian_issue:
        issue = (profile.civilian_issue or "").lower()
        result["flags"].append("civilian_legal_track")
        result["primary_path"] = result["primary_path"] or "Civilian Legal Aid — Free Resources Available"

        if issue == "housing":
            result["secondary_options"].extend([
                "Legal Aid housing attorneys — find at lawhelp.org or 211.org — eviction, lease disputes, code violations",
                "HUD-approved housing counselors — 1-800-569-4287 — foreclosure prevention, tenant rights",
                "VA Legal Services — va.gov/housing-assistance — foreclosure avoidance for VA loan holders",
            ])
            result["flags"].append("housing_legal_issue")

        elif issue == "employment":
            result["secondary_options"].extend([
                "EEOC (Equal Employment Opportunity Commission) — eeoc.gov — discrimination, harassment, retaliation",
                "USERRA (Uniformed Services Employment and Reemployment Rights Act) — "
                "protects your job when called up. File complaint at dol.gov/agencies/vets/programs/userra",
                "DOL Veterans Employment and Training Service (VETS) — free employment law guidance",
            ])
            result["flags"].append("employment_legal_issue")

        elif issue == "family":
            result["secondary_options"].extend([
                "Legal Aid family law services — lawhelp.org — divorce, custody, child support",
                "Military OneSource — 1-800-342-9647 — family law consultations for active duty and recently separated",
                "State bar lawyer referral services — many offer reduced-fee initial consultations",
            ])
            result["flags"].append("family_legal_issue")

        elif issue == "criminal_record":
            result["secondary_options"].extend([
                "Veterans Treatment Courts — many jurisdictions have specialized courts for veteran criminal matters; "
                "focus on treatment over incarceration. Find at justiceforvets.org",
                "Expungement / record sealing — eligibility varies by state; "
                "Legal Aid can advise. Many states have veterans-specific expungement provisions.",
                "NVLSP — nvlsp.org — criminal record issues affecting VA benefits",
            ])
            result["flags"].append("criminal_record_track")

        elif issue == "consumer":
            result["secondary_options"].extend([
                "CFPB (Consumer Financial Protection Bureau) — consumerfinance.gov — "
                "predatory lending, debt collection, credit reporting",
                "SCRA (Servicemembers Civil Relief Act) — protects against predatory lending, "
                "eviction, foreclosure while on active duty; also covers recently separated",
                "State Attorney General consumer protection office — search your state AG website",
            ])
            result["flags"].append("consumer_legal_issue")

        else:
            result["secondary_options"].extend([
                "lawhelp.org — free legal aid directory by state",
                "211.org — connect to local legal services",
                "State Bar Lawyer Referral Service — reduced-fee consultations",
            ])

        result["key_resources"].extend([
            "American Bar Association Veterans Legal Services Initiative — abavetslegalservices.org",
            "Law school veterans clinics — many offer free representation to veterans",
            "211.org — local legal aid organizations",
        ])
        if not result["next_action"]:
            result["next_action"] = (
                "Start at lawhelp.org — enter your state to find free legal aid in your area. "
                "For immediate help: call 211."
            )

    # ── TRACK 5: RECORDS CORRECTION ───────────────────────────────────────────
    if "records_correction" in needs:
        result["flags"].append("records_correction_track")
        result["primary_path"] = result["primary_path"] or "Military Records Correction"
        result["secondary_options"].extend([
            "DD-214 correction — errors in your discharge document affect benefits, employment, and housing. "
            "Correct via BCMR/BCNR (DD Form 149) for substantive errors, or "
            "National Archives (NPRC) for administrative errors: archives.gov/veterans",
            "OMPF (Official Military Personnel File) access — request at milconnect.dmdc.osd.mil",
            "Medical records — submit SF 180 to NPRC for records predating electronic storage",
        ])
        result["key_forms"].extend([
            "DD Form 149 (BCMR/BCNR — substantive corrections)",
            "SF 180 (Request for Military Records)",
        ])
        result["key_resources"].append(
            "NPRC (National Personnel Records Center) — archives.gov/veterans"
        )
        if not result["next_action"]:
            result["next_action"] = (
                "Request your DD-214 and OMPF first to identify all errors before filing any correction. "
                "Use milconnect.dmdc.osd.mil or SF 180 to request records."
            )

    # ── TRACK 6: PREDATORY LENDING / SCAM VSOs ───────────────────────────────
    if "predatory_lending" in needs:
        result["flags"].append("predatory_lending_track")
        result["primary_path"] = result["primary_path"] or "Predatory Practices — Report + Free Help"
        result["secondary_options"].extend([
            "VA-accredited representatives are FREE — anyone charging upfront fees for VA claims is violating federal law. "
            "Verify accreditation at va.gov/ogc/apps/accreditation/",
            "Report predatory VSOs to VA OIG: 1-800-488-8244 or va.gov/oig",
            "Report benefits scams to FTC: reportfraud.ftc.gov",
            "CFPB — consumerfinance.gov/complaint — predatory lending targeted at veterans",
            "SCRA protections — if you were on active duty, additional protections apply; "
            "servicememberlegalcenter.org for free legal help",
        ])
        result["key_resources"].extend([
            "VA OIG Hotline — 1-800-488-8244",
            "FTC ReportFraud — reportfraud.ftc.gov",
            "Servicemember Legal Center — 1-800-342-9647",
        ])
        if not result["next_action"]:
            result["next_action"] = (
                "Stop paying any unauthorized fee immediately. "
                "File a complaint with VA OIG and the FTC. "
                "Contact a free, accredited VSO to take over your claim."
            )
        result["notes"].append(
            "It is illegal to charge veterans a fee for preparing, presenting, or prosecuting "
            "a VA benefits claim before the VA issues a final decision. Period."
        )

    # ── FALLBACK ──────────────────────────────────────────────────────────────
    if not result["primary_path"]:
        result["primary_path"] = "Veterans Legal Services — Free Help Available"
        result["secondary_options"].append(
            "NVLSP (nvlsp.org) — national veterans legal services"
        )
        result["secondary_options"].append(
            "lawhelp.org — state-level free legal aid directory"
        )
        result["next_action"] = (
            "Contact NVLSP at nvlsp.org or call 211 for local legal aid. "
            "All listed resources are free to veterans."
        )

    return result
