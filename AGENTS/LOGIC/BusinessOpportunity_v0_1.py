"""
BusinessOpportunity_v0_1.py
SQUAD BAT — Business & Opportunity Division routing engine.

The federal government is REQUIRED by law to award a percentage of contracts
to veteran-owned and service-disabled veteran-owned small businesses.
Most veterans who qualify have no idea this exists or how to access it.
GSA surplus auctions give veterans priority access to government equipment
and property that would otherwise go to the highest bidder.

This division cuts through the red tape.

Tracks:
  1. Certification       — SDVOSB / VOSB (federal + VA), Colorado CDVBE (state)
  2. Federal Contracting — SAM.gov, set-asides, capability statements, eBuy
  3. SBA Programs        — loans, training, mentorship, VetCert
  4. GSA Surplus         — auctions, excess property, priority access
  5. Startup Resources   — Bunker Labs, SCORE, SBDCs, veteran accelerators
  6. Colorado Specific   — PTAP, CDVBE, state set-asides

Gate 1 (discharge) always runs first.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class BusinessOpportunityProfile:
    # Discharge character — gate 1
    discharge: str

    # Service-connected disability? Determines SDVOSB vs VOSB eligibility
    service_connected_disability: bool = False

    # Disability rating (0–100 or None) — SDVOSB requires SC disability, any rating
    disability_rating: Optional[int] = None

    # Where they are in business journey
    # "idea" | "startup" | "existing"
    business_stage: str = "idea"

    # What they need help with (multi-select)
    # "certification" | "contracting" | "financing" | "surplus_access" |
    # "mentorship" | "training" | "state_programs"
    need_branches: List[str] = field(default_factory=list)

    # Business entity type (if known)
    # "sole_prop" | "llc" | "corporation" | "partnership" | "none_yet"
    entity_type: str = "none_yet"

    # Veteran owns 51%+ of business (required for all certifications)
    owns_51_percent: bool = True

    # Veteran controls day-to-day operations (required for certification)
    controls_operations: bool = True

    # Location
    state: str = ""
    county: str = ""

    # Annual revenue (approximate, for SBA size standard check)
    annual_revenue: Optional[int] = None

    # Number of employees
    employee_count: Optional[int] = None


# ── Qualification gate ────────────────────────────────────────────────────────

def check_qualification(discharge: str) -> dict:
    d = (discharge or "").lower().strip()
    if d == "dishonorable":
        return {
            "status": "BLOCKED",
            "notes": (
                "Dishonorable discharge may impact some veteran-specific business certifications. "
                "VA SDVOSB/VOSB certification requires honorable conditions discharge. "
                "Discharge upgrade through DRB or BCMR is the first step. "
                "Some SBA programs and GSA surplus access may still be available as a veteran "
                "entrepreneur regardless — explore those tracks while pursuing upgrade."
            ),
        }
    if d == "other_than_honorable":
        return {
            "status": "LIMITED",
            "notes": (
                "OTH discharge may limit VA-specific SDVOSB/VOSB certification. "
                "SBA programs, GSA auctions, SCORE mentorship, and Bunker Labs are generally open. "
                "Pursue discharge upgrade in parallel to unlock full certification access."
            ),
        }
    return {
        "status": "QUALIFIED",
        "notes": "Discharge does not bar access to veteran business programs.",
    }


# ── Certification eligibility check ──────────────────────────────────────────

def check_certification_eligibility(profile: BusinessOpportunityProfile) -> dict:
    """
    Determines which certifications the veteran likely qualifies for.
    Does NOT guarantee approval — certification bodies make final determination.
    """
    certs = []
    flags = []
    notes = []

    if not profile.owns_51_percent:
        flags.append("ownership_threshold_not_met")
        notes.append(
            "All veteran business certifications require the veteran to own at least 51% of the business. "
            "Restructuring ownership may be required before applying."
        )
        return {"certs": [], "flags": flags, "notes": notes}

    if not profile.controls_operations:
        flags.append("control_requirement_not_met")
        notes.append(
            "Certifications require the veteran to control day-to-day management decisions. "
            "A non-veteran cannot be the de facto decision-maker."
        )

    # SDVOSB — requires service-connected disability
    if profile.service_connected_disability:
        certs.append({
            "name": "SDVOSB — Service-Disabled Veteran-Owned Small Business",
            "scope": "Federal contracts + VA set-asides (highest priority category)",
            "certifier": "SBA VetCert at vetcert.sba.gov",
            "note": "Requires SC disability of any rating. VA used to run CVE separately — now consolidated under SBA VetCert.",
        })
        flags.append("sdvosb_eligible")

    # VOSB — any veteran
    certs.append({
        "name": "VOSB — Veteran-Owned Small Business",
        "scope": "Federal contracts (VA set-asides)",
        "certifier": "SBA VetCert at vetcert.sba.gov",
        "note": "No disability requirement. SDVOSB is higher priority — if SC eligible, pursue both.",
    })
    flags.append("vosb_eligible")

    # Colorado CDVBE — state level
    if (profile.state or "").upper() in ("CO", "COLORADO"):
        if profile.service_connected_disability:
            certs.append({
                "name": "Colorado CDVBE — Disabled Veteran Business Enterprise",
                "scope": "Colorado state contracts and procurement set-asides",
                "certifier": "Colorado DOIT / Department of Personnel & Administration",
                "note": "State-level equivalent of SDVOSB. Unlocks CO state government contracts separately from federal.",
            })
            flags.append("cdvbe_eligible")

    return {"certs": certs, "flags": flags, "notes": notes}


# ── Main router ───────────────────────────────────────────────────────────────

def route_business_opportunity(profile: BusinessOpportunityProfile) -> dict:
    result = {
        "primary_path": None,
        "secondary_options": [],
        "flags": [],
        "next_action": None,
        "key_resources": [],
        "notes": [],
        "qualification": None,
        "certifications": [],
    }

    # ── GATE 1: DISCHARGE ─────────────────────────────────────────────────────
    qual = check_qualification(profile.discharge)
    result["qualification"] = qual

    if qual["status"] == "BLOCKED":
        result["primary_path"] = "Discharge Upgrade + Pursue Open Tracks"
        result["secondary_options"] = [
            "SBA programs, SCORE mentorship, and Bunker Labs are open regardless of discharge",
            "GSA Auctions account (gsaauctions.gov) — access not always discharge-dependent",
            "Pursue discharge upgrade via DRB/BCMR to unlock VOSB/SDVOSB certification",
        ]
        result["flags"].append("discharge_limited")
        result["notes"].append(qual["notes"])
        # Don't fully block — some tracks still open

    if qual["status"] == "LIMITED":
        result["flags"].append("oth_limited")
        result["notes"].append(qual["notes"])

    # ── TRACK 1: CERTIFICATION — always runs ─────────────────────────────────
    # Certification eligibility is fundamental — every veteran business owner
    # should know what they qualify for regardless of what they came in asking.
    if True:
        cert_check = check_certification_eligibility(profile)
        result["certifications"] = cert_check["certs"]
        result["flags"].extend(cert_check["flags"])
        result["notes"].extend(cert_check["notes"])

        if cert_check["certs"]:
            top = cert_check["certs"][0]
            result["primary_path"] = result["primary_path"] or f"Get Certified: {top['name']}"
            result["key_resources"].append(f"SBA VetCert: vetcert.sba.gov — certifies VOSB and SDVOSB for federal contracting")
            result["next_action"] = result["next_action"] or (
                "Start at vetcert.sba.gov to apply for VOSB/SDVOSB certification. "
                "You'll need: DD-214, business formation documents, proof of ownership, "
                "and if SDVOSB, your VA SC disability rating letter. "
                "The SBA reviews and approves — no cost to apply."
            )
            result["notes"].append(
                "Certification is the key that unlocks set-aside contracts. "
                "The federal government is LEGALLY REQUIRED to award a percentage of contracts "
                "to SDVOSB/VOSB businesses. Without certification, you cannot access those contracts "
                "regardless of how qualified you are."
            )

    # ── TRACK 2: FEDERAL CONTRACTING ─────────────────────────────────────────
    if "contracting" in profile.need_branches:
        result["primary_path"] = result["primary_path"] or "Federal Contracting — SAM.gov Registration"
        result["secondary_options"].extend([
            "SAM.gov (sam.gov) — System for Award Management; required registration before bidding any federal contract",
            "USASpending.gov — research what agencies are buying in your industry, who currently holds contracts",
            "GSA eBuy (ebuy.gsa.gov) — federal marketplace for quotes; certified VOSBs can respond to RFQs",
            "beta.SAM.gov contract opportunities — search by NAICS code for your industry",
            "Capability Statement — 1-page document every federal buyer expects; must have before outreach",
        ])
        result["key_resources"].extend([
            "SAM.gov — register your business (free, required)",
            "NAICS code lookup: census.gov/naics — find your industry code for set-aside searches",
            "Colorado PTAP (coloradoptap.com) — free help navigating federal contracting process",
        ])
        result["flags"].append("contracting_track")
        result["notes"].append(
            "The single most important document for federal contracting is your Capability Statement. "
            "It is a 1-page summary of what you do, your NAICS codes, certifications, past performance, "
            "and contact info. Contracting officers see dozens of these — it must be clean and specific."
        )

    # ── TRACK 3: SBA PROGRAMS ────────────────────────────────────────────────
    if "financing" in profile.need_branches or "training" in profile.need_branches:
        result["primary_path"] = result["primary_path"] or "SBA Programs for Veterans"
        result["secondary_options"].extend([
            "SBA 7(a) Loan — most common SBA loan; Veterans Advantage reduces fees",
            "SBA 504 Loan — for major equipment or real estate purchases",
            "SBA Boots to Business — free 2-day entrepreneurship training for transitioning vets and families",
            "SCORE Mentorship (score.org) — free one-on-one mentoring from retired executives; veteran chapter network",
            "Small Business Development Centers (SBDCs) — free consulting, financials, business plans; "
            "Colorado has 9 centers statewide",
        ])
        result["key_resources"].extend([
            "SBA Veterans programs: sba.gov/business-guide/grow-your-business/veteran-owned-businesses",
            "Boots to Business: sbavets.force.com/s",
            "SCORE veteran resources: score.org/veteran",
            "Colorado SBDC: coloradosbdc.org",
        ])
        result["flags"].append("sba_track")
        if (profile.state or "").upper() in ("CO", "COLORADO"):
            result["secondary_options"].append(
                "Colorado PTAP (Procurement Technical Assistance Program) — "
                "free, specialized help with the federal contracting process specifically; "
                "different from SBDC, more contracting-focused"
            )
            result["key_resources"].append("Colorado PTAP: coloradoptap.com — call before doing anything else in contracting")
            result["flags"].append("co_ptap_available")

    # ── TRACK 4: GSA SURPLUS & AUCTIONS ──────────────────────────────────────
    if "surplus_access" in profile.need_branches:
        result["primary_path"] = result["primary_path"] or "GSA Surplus & Auctions — Priority Access for Veterans"
        result["secondary_options"].extend([
            "GSA Auctions (gsaauctions.gov) — surplus federal property: vehicles, equipment, electronics, furniture. "
            "Veteran-owned businesses get priority bidding status.",
            "GSA Xcess (gsaxcess.gov) — excess federal property transferred to eligible organizations; "
            "nonprofits and government entities get first access before public auction",
            "1033 Program — DoD surplus equipment to law enforcement; note: not for general veteran use",
            "Property at auction often includes: vehicles, office equipment, IT hardware, lab equipment, "
            "construction equipment, furniture — often well below market value",
        ])
        result["key_resources"].extend([
            "GSA Auctions: gsaauctions.gov — register, then search by category or location",
            "GSA personal property disposal: gsa.gov/real-estate/other-government-assets/personal-property-for-sale",
        ])
        result["flags"].append("gsa_surplus_track")
        result["next_action"] = result["next_action"] or (
            "Register at gsaauctions.gov — free account, takes 10 minutes. "
            "Set up alerts for categories relevant to your business or personal use. "
            "Bring your DD-214 documentation when registering to flag veteran status for priority access."
        )
        result["notes"].append(
            "GSA Auctions is one of the most underutilized veteran benefits in existence. "
            "The federal government regularly disposes of functional equipment at a fraction of market cost. "
            "Veteran-owned businesses with active SAM.gov registration get priority. "
            "This is not common knowledge — spread it."
        )

    # ── TRACK 5: STARTUP RESOURCES ───────────────────────────────────────────
    if "mentorship" in profile.need_branches or profile.business_stage == "idea":
        result["primary_path"] = result["primary_path"] or "Veteran Startup Resources — Bunker Labs + SCORE"
        result["secondary_options"].extend([
            "Bunker Labs (bunkerlabs.org) — veteran entrepreneur network, accelerator programs, "
            "CEO Bootcamp, annual conference; specifically for veteran founders",
            "American Corporate Partners (acp-usa.org) — free 1-year mentorship from corporate executives "
            "specifically for transitioning veterans",
            "Warrior-Scholar Project — academic prep for vets returning to school; bridges military to academic mindset",
            "V-WISE (Veteran Women Igniting the Spirit of Entrepreneurship) — SBA program for women veteran entrepreneurs",
            "Hirepurpose — veteran talent network; both job placement and entrepreneurship resources",
        ])
        result["key_resources"].append("Bunker Labs: bunkerlabs.org — start here for veteran founder community")
        result["flags"].append("startup_track")

    # ── TRACK 6: COLORADO SPECIFIC ───────────────────────────────────────────
    if "state_programs" in profile.need_branches or (profile.state or "").upper() in ("CO", "COLORADO"):
        co_programs = [
            "Colorado CDVBE certification — state contracts set-asides for disabled veteran businesses; "
            "apply at colorado.gov/pacific/dpa/vendor-certification",
            "Colorado PTAP — free procurement technical assistance; helps win government contracts at all levels",
            "Minority Business Office (MBO Colorado) — small business development resources including veteran programs",
            "Colorado Office of Economic Development (OEDIT) — business loans, grants, and incentives",
        ]
        if (profile.state or "").upper() in ("CO", "COLORADO"):
            result["secondary_options"].extend(co_programs)
            result["flags"].append("colorado_programs_available")
            result["notes"].append(
                "Colorado has some of the most veteran-friendly state procurement policies in the country. "
                "CDVBE certification is separate from federal SDVOSB — you need both to access all set-asides. "
                "Colorado PTAP is free and specifically focused on helping small businesses win government contracts."
            )

    # ── FALLBACK ──────────────────────────────────────────────────────────────
    if not result["primary_path"]:
        result["primary_path"] = "Veteran Business Programs Overview — start with SBA VetCert + SCORE"
        result["next_action"] = (
            "Get certified at vetcert.sba.gov (VOSB/SDVOSB). "
            "Register at SAM.gov to access federal contracting. "
            "Connect with SCORE (score.org/veteran) for free mentorship. "
            "Check GSA Auctions (gsaauctions.gov) for surplus access."
        )

    return result
