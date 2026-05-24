"""
Legal_v0_1.py
SQUAD BAT — Legal Division routing engine.

Tracks:
  1. Discharge Upgrade            — DRB, BCMR/BCNR, Character of Discharge review
  2. VA Benefits Appeals          — HLR, Supplemental Claim, BVA, CAVC
  3. Military Sexual Trauma       — MST legal resources, disability claims, discharge upgrade
  4. Civilian Legal Aid           — housing, employment, family law, consumer protection
  5. Records Correction           — DD-214 errors, military records
  6. Predatory Lending            — scam VSOs, benefits poachers, accredited rep access
  7. Veterans Treatment Court     — criminal diversion for veterans with service-connected conditions
  8. Medical Retirement Dispute   — VA post-discharge causation error when DoD medically retired
  9. Active Criminal Defense      — DV, assault, other charges; PTSD/TBI mitigation; self-defense framing

Gate: Legal issues never block — every veteran gets a path.
Design law: Multi-domain crises run in parallel. Criminal case does not stop benefits routing.
Benefits routing does not stop housing routing. Everything runs.
"""

from dataclasses import dataclass, field
from typing import List, Optional

# ---------------------------------------------------------------------------
# Hardcoded contact numbers — verified before inclusion.
# Phone numbers are never LLM-generated. If a number is unverified, it is
# marked VERIFY_BEFORE_PRODUCTION and must not be surfaced to veterans.
#
# Last reviewed: 2026-05-24
# ---------------------------------------------------------------------------

# Always-available VA numbers — surfaced regardless of track
_VA_MAIN_LINE             = "1-800-827-1000"
_VA_HOMELESS_VETERANS     = "1-877-4AID-VET (1-877-424-3838)"   # 24/7 homeless veteran support
_VETERANS_CRISIS_LINE     = "988, press 1"

# Branch-specific emergency resources — hardcoded per branch
_BRANCH_EMERGENCY = {
    "marine_corps": [
        "Semper Fi & America's Fund — 760-725-3680 — emergency financial assistance for Marines and their families. Same-week response for verified cases.",
        "Marine Corps Wounded Warrior Regiment — 1-877-487-6299 — recovery support, benefits navigation for injured/ill Marines.",
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
        "NOTE: Coast Guard veterans are routinely and incorrectly told they are ineligible for VA benefits. They are fully eligible. Escalate any denial.",
    ],
    "army_national_guard": [
        "Army Emergency Relief (AER) — 1-866-878-6378 — Title 10 activation required for full AER eligibility; Title 32 may qualify for state programs.",
        "State National Guard Family Assistance Center — contact your state Adjutant General's office.",
    ],
    "air_national_guard": [
        "Air Force Aid Society — 1-800-769-8951",
        "State National Guard Family Assistance Center — contact your state Adjutant General's office.",
    ],
}

# Track-specific verified numbers
_CONTACT_NUMBERS = {
    "dav":                   "1-800-741-4990",        # DAV service line
    "cohen_veterans":        "1-855-204-5784",        # mental health + legal support
    "va_homeless":           _VA_HOMELESS_VETERANS,
    "va_main":               _VA_MAIN_LINE,
    "crisis":                _VETERANS_CRISIS_LINE,
    # VERIFY_BEFORE_PRODUCTION — do not surface until confirmed:
    # "vtc_nadcp":           "VERIFY_BEFORE_PRODUCTION",
    # "nvlsp_direct":        "VERIFY_BEFORE_PRODUCTION",
    # "amvets_service":      "VERIFY_BEFORE_PRODUCTION",
}


@dataclass
class VetLegalProfile:
    # What legal issue(s) they face (multi-select)
    # "discharge_upgrade" | "va_appeal" | "mst" | "civilian_legal" |
    # "records_correction" | "predatory_lending" | "benefits_denial" |
    # "criminal_defense" | "medical_retirement_dispute" | "veterans_treatment_court"
    legal_needs: List[str] = field(default_factory=list)

    # Discharge character — affects upgrade pathway
    discharge: str = "unknown"

    # Medical discharge sub-type
    # "severance" | "chapter_61_retirement" | "tdrl" | "ides" | "unknown"
    medical_discharge_type: str = "unknown"

    # Years since discharge (affects DRB vs BCMR availability)
    years_since_discharge: Optional[int] = None

    # Branch of service
    branch: str = "unknown"

    # VA claim denied or rated low
    has_denied_claim: bool = False

    # VA claiming conditions are post-discharge when DoD medically retired for same conditions
    medical_retirement_va_dispute: bool = False

    # Extensive military medical records exist (e.g. long treatment history before discharge)
    has_extensive_military_medical_records: bool = False

    # Which VA appeals lane they're in (if any)
    # "none" | "hlr" | "supplemental" | "bva" | "cavc" | "unknown"
    appeals_lane: str = "none"

    # Military Sexual Trauma
    has_mst: bool = False

    # Active criminal case
    active_criminal_case: bool = False

    # Type of criminal charge
    # "dv" | "assault" | "drug" | "property" | "other" | ""
    criminal_case_type: str = ""

    # Claiming self-defense (affects VTC routing and defense strategy)
    claiming_self_defense: bool = False

    # Civilian legal issue type
    # "housing" | "employment" | "family" | "consumer" | "criminal_record" | "other"
    civilian_issue: str = ""

    # Was charged or faced NJP (affects discharge upgrade framing)
    has_ucmj_history: bool = False

    # Homelessness — chronic flag (6+ months or repeat episodes)
    is_chronically_homeless: bool = False

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

    # ── TRACK 7: VETERANS TREATMENT COURT ────────────────────────────────────
    if (
        "veterans_treatment_court" in needs or
        "criminal_defense" in needs or
        profile.active_criminal_case
    ):
        result["flags"].append("vtc_track")
        result["primary_path"] = result["primary_path"] or "Veterans Treatment Court — Diversion Before Incarceration"

        result["secondary_options"].extend([
            "Veterans Treatment Court (VTC) — specialized courts that divert veteran criminal cases "
            "into treatment tracks rather than incarceration when service-connected conditions "
            "(PTSD, TBI, MST, substance use) are a factor. Over 500 courts nationally. "
            "Find your local VTC at justiceforvets.org — TIME SENSITIVE, request VTC diversion immediately.",

            f"VTC Court Advocates — DAV ({_CONTACT_NUMBERS['dav']}), AMVETS, and American Legion "
            "have trained court advocates who accompany veterans to VTC proceedings. "
            "Call DAV or contact your local AMVETS chapter before your next court date.",

            f"Cohen Veterans Network — {_CONTACT_NUMBERS['cohen_veterans']} — "
            "mental health support and legal navigation for veterans in the justice system.",

            f"VA National Call Center for Homeless Veterans — {_VA_HOMELESS_VETERANS} — "
            "24/7 line. If homelessness and a criminal case are both active, "
            "this line can coordinate across both tracks.",
        ])

        if profile.active_criminal_case and profile.criminal_case_type == "dv":
            result["flags"].append("dv_criminal_case")
            result["notes"].append(
                "DV charges with a veteran defendant require a defense attorney familiar with "
                "PTSD, hypervigilance, and combat-trained responses. These are recognized mitigating "
                "factors in veteran criminal cases. VTC is the priority routing — request it at arraignment."
            )
            if profile.claiming_self_defense:
                result["flags"].append("self_defense_claim")
                result["notes"].append(
                    "Self-defense claim in a DV case: the combat-trained response dynamic is documented "
                    "legal territory. An attorney experienced in veteran cases can frame the PTSD "
                    "hypervigilance response within self-defense. Do not navigate this without counsel."
                )
                result["notes"].append(
                    "CRITICAL — if VA has service-connected PTSD documented, that record directly "
                    "supports the defense. If VA is disputing service connection, resolving the VA "
                    "appeal and the criminal defense are legally connected. Both tracks must run."
                )

        # Branch-specific emergency resources — surfaced immediately for multi-domain crisis
        branch_key = (profile.branch or "").lower().replace(" ", "_").replace("-", "_")
        branch_resources = _BRANCH_EMERGENCY.get(branch_key, [])
        if branch_resources:
            result["flags"].append("branch_emergency_resources_available")
            result["notes"].append(
                "BRANCH-SPECIFIC EMERGENCY RESOURCES — available now, separate from VA:"
            )
            result["notes"].extend(branch_resources)

        result["key_resources"].extend([
            "Justice For Vets (VTC locator) — justiceforvets.org",
            f"DAV service line — {_CONTACT_NUMBERS['dav']}",
            f"Cohen Veterans Network — {_CONTACT_NUMBERS['cohen_veterans']}",
            f"VA main line — {_VA_MAIN_LINE}",
        ])
        result["key_forms"].extend([
            "Request VTC diversion at arraignment — ask your attorney to file immediately",
        ])
        if not result["next_action"]:
            result["next_action"] = (
                f"Call VA National Call Center for Homeless Veterans: {_VA_HOMELESS_VETERANS} — 24/7. "
                "Find your local Veterans Treatment Court at justiceforvets.org — request VTC diversion "
                "at your next court appearance. Do not appear without an attorney familiar with veteran cases."
            )

    # ── TRACK 8: MEDICAL RETIREMENT VA DISPUTE ────────────────────────────────
    if (
        "medical_retirement_dispute" in needs or
        profile.medical_retirement_va_dispute or
        (profile.discharge == "medical" and profile.has_denied_claim)
    ):
        result["flags"].append("medical_retirement_dispute_track")
        result["primary_path"] = result["primary_path"] or (
            "Medical Retirement VA Dispute — DoD Records ARE the Evidence"
        )

        result["secondary_options"].extend([
            "Military medical records from active duty are your primary evidence. "
            "If DoD medically retired you FOR a condition, VA claiming that condition is "
            "post-service directly contradicts DoD's own finding. "
            "Request ALL military treatment records — these are separate from service records.",

            "Military treatment records request: submit to the Military Treatment Facility (MTF) "
            "where you received care, OR request through milConnect (milconnect.dmdc.osd.mil). "
            "Post-2015 records may be in MHS GENESIS. Pre-digital records: SF 180 to NPRC.",

            "Physical Evaluation Board (PEB) decision letter — this document states the DoD's "
            "finding that you were unfit for duty due to a specific condition. "
            "It is the cornerstone of your VA appeal. Get it before anything else moves.",

            "File a Supplemental Claim (VA Form 20-0995) with the PEB decision letter and "
            "military treatment records as new and relevant evidence. "
            "If you went through IDES, the joint DoD-VA rating should have established service "
            "connection — VA contradicting it is grounds for a stronger appeal.",

            "Accredited claims agent or veterans attorney — this case needs representation, "
            "not just a VSO intake. Find accredited attorneys at va.gov/ogc/apps/accreditation/. "
            "Many work on contingency (no win, no fee).",
        ])

        if profile.has_extensive_military_medical_records:
            result["flags"].append("strong_records_appeal_grounds")
            result["notes"].append(
                "Extensive military medical records significantly strengthen this appeal. "
                "The volume and duration of documented in-service treatment directly contradicts "
                "a VA post-discharge causation finding. An accredited attorney reviewing those "
                "records before filing can build a much stronger case than a standard VSO intake."
            )

        if profile.medical_discharge_type in ("chapter_61_retirement", "ides"):
            result["flags"].append("chapter_61_ides_strong_grounds")
            result["notes"].append(
                "Chapter 61 medical retirement and IDES both involve formal DoD determination "
                "of unfitness for duty due to a specific condition. VA contradicting that determination "
                "is the strongest appeal scenario. The DoD's own paperwork is the evidence — "
                "no nexus letter needed when the military already documented the connection."
            )

        # Branch-specific resources if not already surfaced
        branch_key = (profile.branch or "").lower().replace(" ", "_").replace("-", "_")
        branch_resources = _BRANCH_EMERGENCY.get(branch_key, [])
        if branch_resources and "branch_emergency_resources_available" not in result["flags"]:
            result["flags"].append("branch_emergency_resources_available")
            result["notes"].append("BRANCH-SPECIFIC EMERGENCY RESOURCES — available now, separate from VA:")
            result["notes"].extend(branch_resources)

        result["key_resources"].extend([
            f"VA main line — {_VA_MAIN_LINE} — ask for Benefits line",
            "VA Form 20-0995 (Supplemental Claim) — submit with PEB letter + MTF records",
            "milConnect — milconnect.dmdc.osd.mil — military records access",
            "NVLSP — nvlsp.org — free legal representation including contested ratings",
            "National Organization of Veterans Advocates (NOVA) — veteransadvocates.org — accredited attorneys",
        ])
        result["key_forms"].extend([
            "VA Form 20-0995 (Supplemental Claim — new and relevant evidence)",
            "SF 180 (Military Records Request)",
            "PEB Decision Letter (obtain from branch Physical Evaluation Board)",
        ])
        if not result["next_action"]:
            result["next_action"] = (
                f"Call VA main line: {_VA_MAIN_LINE} — ask for the Benefits line and request your "
                "claims file (C-file) and any existing rating decisions. "
                "Step 2: Request your PEB decision letter and all military treatment records "
                "before filing anything. "
                "Step 3: Contact an accredited veterans attorney — not just a VSO — "
                "to review those records. Find attorneys at va.gov/ogc/apps/accreditation/ or nvlsp.org."
            )
        result["notes"].append(
            "IMPORTANT: If an active criminal case is also in progress and service-connected PTSD "
            "or TBI is a factor in both — the VA appeal and the criminal defense are legally connected. "
            "Resolving VA service connection strengthens the criminal mitigation argument. "
            "An attorney who understands both tracks is the goal."
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
