"""
ToxicExposure_v0_1.py
SQUAD BAT — Toxic Exposure Division routing engine.

Tracks:
  1. Burn Pits / Airborne Hazards — PACT Act 2022 presumptive (OIF/OEF primary)
  2. Agent Orange               — Vietnam, Korea DMZ, Thailand, Blue Water Navy, C-123
  3. Camp Lejeune Water         — 1953–1987 contamination; veteran + family members
  4. Gulf War Syndrome          — undiagnosed illness, functional disorders, burn pits (Gulf War era)
  5. Radiation Exposure         — atomic veterans, RECA, Palomares, Enewetak
  6. PFAS / Forever Chemicals   — firefighting foam (AFFF) at military installations
  7. Registry                   — Airborne Hazards and Open Burn Pit Registry (always relevant)

CRITICAL DESIGN NOTE:
Most OIF/OEF veterans do not know their respiratory illness, rare cancer, or chronic
condition is connected to burn pit exposure — or that the PACT Act (2022) made it a
PRESUMPTIVE condition. They no longer need to prove the connection.
Previously denied claims can be refiled as Supplemental Claims.

Gate: Toxic exposure never blocks. Every veteran gets routed.
"""

from dataclasses import dataclass, field
from typing import List, Optional


# PACT Act covered locations (burn pit / airborne hazard presumptive)
PACT_ACT_LOCATIONS = {
    # Southwest Asia theater — on or after Aug 2, 1990
    "iraq", "kuwait", "saudi_arabia", "qatar", "bahrain",
    "uae", "united_arab_emirates", "oman", "jordan", "egypt",
    "turkey", "djibouti", "somalia", "yemen",
    # Afghanistan and others — on or after Sep 11, 2001
    "afghanistan", "syria", "uzbekistan", "kyrgyzstan",
    # General covered areas
    "southwest_asia", "persian_gulf",
}

# PACT Act presumptive cancer types (23 categories)
PACT_CANCERS = [
    "Bladder cancer",
    "Squamous cell carcinoma of the head or neck",
    "Reproductive cancers (cervical, ovarian, prostate, penile, testicular, uterine, vulvar)",
    "Squamous cell carcinoma of the esophagus",
    "Kidney cancer",
    "Melanoma",
    "Pancreatic cancer",
    "Salivary gland cancer",
    "Small intestine cancer",
    "Thyroid cancer",
    "Ureter cancer",
    "Any cancer the VA determines is as likely as not caused by service",
]

# Agent Orange presumptive conditions
AO_PRESUMPTIVES = [
    "AL amyloidosis",
    "Bladder cancer",
    "Chloracne (or other acneform disease similar to chloracne)",
    "Chronic B-cell leukemias (including hairy cell leukemia)",
    "Diabetes mellitus type 2",
    "Hodgkin's disease",
    "Hypertension (added by PACT Act 2022)",
    "Hypothyroidism (added by PACT Act 2022)",
    "Ischemic heart disease",
    "Monoclonal gammopathy of undetermined significance (MGUS) (added by PACT Act 2022)",
    "Multiple myeloma",
    "Non-Hodgkin's lymphoma",
    "Parkinson's disease / Parkinsonism (added by PACT Act 2022)",
    "Peripheral neuropathy, early onset",
    "Porphyria cutanea tarda",
    "Prostate cancer",
    "Respiratory cancers (lung, bronchus, larynx, trachea)",
    "Soft tissue sarcomas (excluding osteosarcoma, chondrosarcoma, Kaposi's sarcoma, mesothelioma)",
]

# Gulf War presumptive conditions
GULF_WAR_PRESUMPTIVES = [
    "Chronic fatigue syndrome",
    "Fibromyalgia",
    "Functional gastrointestinal disorders (IBS, functional dyspepsia, etc.)",
    "Undiagnosed illnesses with objective indications (medically unexplained symptoms)",
    "Infectious diseases: Brucellosis, Campylobacter jejuni, Coxiella burnetii (Q fever), "
    "Malaria, Mycobacterium tuberculosis, Nontyphoid Salmonella, Shigella, Visceral leishmaniasis, "
    "West Nile virus",
]

# Camp Lejeune qualifying conditions (VA healthcare)
LEJEUNE_CONDITIONS = [
    "Bladder cancer",
    "Breast cancer",
    "Esophageal cancer",
    "Female infertility",
    "Hepatic steatosis (liver disease)",
    "Kidney cancer",
    "Leukemia",
    "Lung cancer",
    "Miscarriage",
    "Multiple myeloma",
    "Myelodysplastic syndromes",
    "Neurobehavioral effects",
    "Non-Hodgkin's lymphoma",
    "Renal toxicity (kidney damage)",
    "Scleroderma",
]


@dataclass
class ToxicExposureProfile:
    # Which exposure type(s) apply (multi-select)
    # "burn_pit" | "agent_orange" | "camp_lejeune" | "gulf_war_syndrome" |
    # "radiation" | "pfas" | "unknown"
    exposure_types: List[str] = field(default_factory=list)

    # Service era(s) — critical for routing
    # "post_9_11" | "gulf_war" | "vietnam" | "korea" | "cold_war" | "wwii" | "unknown"
    era: str = "unknown"

    # Where they served (normalized)
    locations_served: List[str] = field(default_factory=list)

    # Current health condition(s) they're dealing with
    # "respiratory" | "cancer" | "neurological" | "gi" | "chronic_fatigue" |
    # "skin" | "cardiac" | "reproductive" | "undiagnosed" | "none_yet"
    conditions: List[str] = field(default_factory=list)

    # Served near Camp Lejeune 1953–1987
    camp_lejeune: bool = False

    # Family member affected by Camp Lejeune (not the veteran)
    is_lejeune_family_member: bool = False

    # Has existing VA disability claim or rating
    has_existing_claim: bool = False

    # Was previously denied for a toxic exposure claim
    was_previously_denied: bool = False

    # Enrolled in VA health care
    enrolled_va_healthcare: bool = False

    # Discharge character
    discharge: str = "unknown"

    # Location
    state: str = ""
    county: str = ""


def _is_pact_covered(profile: ToxicExposureProfile) -> bool:
    """Determine if veteran likely qualifies for PACT Act burn pit presumptive."""
    era = (profile.era or "").lower()
    if era in ("post_9_11", "gulf_war"):
        return True
    locs = [l.lower().strip() for l in profile.locations_served]
    return any(loc in PACT_ACT_LOCATIONS for loc in locs)


def route_toxic_exposure(profile: ToxicExposureProfile) -> dict:
    result = {
        "primary_path": None,
        "secondary_options": [],
        "flags": [],
        "next_action": None,
        "key_resources": [],
        "key_forms": [],
        "notes": [],
        "presumptive_conditions": [],
    }

    types = [t.lower() for t in profile.exposure_types]
    conditions = [c.lower() for c in profile.conditions]
    era = (profile.era or "").lower()

    # Independent-audit finding (2026-09-06), round 3, high: `discharge` was
    # never read anywhere in this function -- a dishonorable-discharge
    # veteran got byte-identical routing to an honorably-discharged one,
    # including being told to file VA Form 21-526EZ (Disability
    # Compensation), with zero mention that dishonorable discharge bars
    # most VA disability compensation (as this codebase's own
    # MedDisability_v0_1.py/VaBenefits_v0_1.py/BusinessOpportunity_v0_1.py
    # state explicitly for the same field value). Fixed with additive,
    # honest disclosure rather than a hard block: this file's own module
    # docstring states "Gate: Toxic exposure never blocks. Every veteran
    # gets routed" -- registry enrollment, Camp Lejeune family-member
    # claims, and presumptive-condition healthcare access don't require
    # honorable discharge the way standard disability compensation does,
    # so a MedDisability-style BLOCKED early-return would violate this
    # router's own stated design law, not fix a bug. The veteran still
    # gets full routing; they now also get an accurate caveat instead of
    # a silent, misleading omission.
    discharge_lower = (profile.discharge or "").lower().strip()
    if discharge_lower in ("dishonorable", "other_than_honorable"):
        result["flags"].append("discharge_limits_compensation")
        result["notes"].append(
            "Discharge note: a dishonorable or Other Than Honorable discharge limits access to "
            "standard VA disability compensation (VA Form 21-526EZ) for the conditions below -- it "
            "does NOT block Airborne Hazards Registry enrollment, Camp Lejeune family-member claims, "
            "or MST-related care. A discharge upgrade (DRB or BCMR) is the path to unlock full "
            "compensation eligibility. Talk to a VSO or veterans law clinic about pursuing both "
            "in parallel."
        )

    # ── ALWAYS: AIRBORNE HAZARDS REGISTRY ────────────────────────────────────
    # Every veteran with any toxic exposure should register — it builds the data record
    result["key_resources"].append(
        "Airborne Hazards and Open Burn Pit Registry — register even if you feel fine now. "
        "Your registry entry documents your exposure and strengthens any future claim. "
        "Register at va.gov/disability/eligibility/hazardous-materials-exposure/airborne-hazards-open-burn-pit-registry"
    )
    result["flags"].append("registry_enrollment_recommended")

    # ── TRACK 1: BURN PITS / PACT ACT (PRIMARY for OIF/OEF) ──────────────────
    if "burn_pit" in types or "unknown" in types or _is_pact_covered(profile):
        result["flags"].append("pact_act_candidate")

        # Era-specific framing
        if era == "post_9_11" or _is_pact_covered(profile):
            result["primary_path"] = (
                "PACT Act (2022) — Burn Pit / Airborne Hazard Presumptive Claim"
            )
            result["notes"].append(
                "THE KEY FACT most OIF/OEF veterans don't know: "
                "You no longer have to prove your condition was caused by burn pits. "
                "The PACT Act (2022) made burn pit exposure a PRESUMPTIVE service connection "
                "for veterans who served in covered locations. "
                "If VA denied you before 2022 — YOU CAN REFILE. "
                "A denial before the PACT Act is not final."
            )
            result["secondary_options"].append(
                "PACT Act presumptive coverage applies if you served in: Iraq, Afghanistan, "
                "Kuwait, Qatar, Djibouti, Syria, Bahrain, Saudi Arabia, UAE, Oman, Jordan, "
                "Somalia, Turkey, or other covered Southwest Asia / post-9/11 locations. "
                "On or after August 2, 1990 (Gulf War era) or September 11, 2001 (OEF era)."
            )
            result["presumptive_conditions"].extend(PACT_CANCERS)
            result["secondary_options"].append(
                "Respiratory conditions are now presumptive under PACT Act — "
                "constrictive bronchiolitis, constrictive pericarditis, and other "
                "airborne hazard-related conditions. If you have chronic breathing issues "
                "from service, file now."
            )

        elif era == "gulf_war":
            result["primary_path"] = (
                "Gulf War / PACT Act — Burn Pit + Gulf War Syndrome Presumptive"
            )
            result["notes"].append(
                "Gulf War veterans qualify for BOTH Gulf War Syndrome presumptives "
                "AND PACT Act burn pit/airborne hazard coverage. "
                "You may have two separate pathways to service connection."
            )

        if profile.was_previously_denied:
            result["flags"].append("refile_candidate")
            result["notes"].append(
                "REFILE YOUR CLAIM. If you were denied for a condition now covered by PACT Act, "
                "file a Supplemental Claim (VA Form 20-0995) with the PACT Act as new and relevant evidence. "
                "Your previous denial does not close the door — the law changed."
            )
            result["key_forms"].append("VA Form 20-0995 (Supplemental Claim — PACT Act refile)")

        result["key_forms"].extend([
            "VA Form 21-526EZ (Disability Compensation — check 'toxic exposure' section)",
            "VA Form 10-10EZRF (Airborne Hazards and Open Burn Pit Registry enrollment)",
        ])
        result["key_resources"].extend([
            "PACT Act information — va.gov/pact-act-information",
            "VA Toxic Exposure screening — ask your VA primary care provider for a free toxic exposure screening",
        ])
        result["next_action"] = (
            "Step 1: Register in the Airborne Hazards and Open Burn Pit Registry now — "
            "it documents your exposure before you file. "
            "Step 2: Request a toxic exposure screening at your VA facility (free, no claim needed). "
            "Step 3: File or refile VA Form 21-526EZ — check the toxic exposure section. "
            "Get a VSO to review your service record and condition list first."
        )
        result["notes"].append(
            "You do not need a diagnosis to enroll in the registry or to request a screening. "
            "Even if you feel fine now, register. Burn pit-related conditions can appear years later."
        )

    # ── TRACK 2: AGENT ORANGE ─────────────────────────────────────────────────
    if "agent_orange" in types or era in ("vietnam", "korea"):
        result["flags"].append("agent_orange_track")
        result["primary_path"] = result["primary_path"] or "Agent Orange — Presumptive Service Connection"

        # Location-specific routing
        ao_routes = []
        locs = [l.lower() for l in profile.locations_served]

        if era == "vietnam" or "vietnam" in locs or "republic_of_vietnam" in locs:
            ao_routes.append(
                "Vietnam veterans: Agent Orange presumptive applies if you served in Vietnam "
                "(including inland waterways) between January 9, 1962 and May 7, 1975."
            )
        if "korea" in locs or era == "korea":
            ao_routes.append(
                "Korea: Veterans who served near the Korean DMZ between September 1, 1967 "
                "and August 31, 1971 qualify for Agent Orange presumptive."
            )
        if any(loc in ("thailand", "utapao", "ubon", "nakhon_phanom") for loc in locs):
            ao_routes.append(
                "Thailand: Veterans who served at Royal Thai Air Force Bases during the Vietnam era "
                "and had significant contact with security perimeters may qualify. "
                "Requires specific duty assignment documentation."
            )
        if "c123" in locs or "c-123" in locs:
            ao_routes.append(
                "C-123 Aircraft crews: veterans who flew or worked on C-123 aircraft used to "
                "spray Agent Orange are covered — even those who served post-Vietnam."
            )
        if "blue_water" in locs or "offshore" in locs or not ao_routes:
            ao_routes.append(
                "Blue Water Navy: veterans who served offshore Vietnam on ships (not just inland) "
                "are NOW covered since 2019. If you were denied before 2019, refile."
            )

        result["secondary_options"].extend(ao_routes)
        result["presumptive_conditions"].extend(AO_PRESUMPTIVES)
        result["secondary_options"].append(
            f"Agent Orange presumptive conditions include {len(AO_PRESUMPTIVES)} recognized illnesses. "
            "Key ones added by PACT Act 2022: hypertension, hypothyroidism, Parkinsonism, MGUS. "
            "If you were denied for any of these before 2022 — REFILE."
        )
        result["key_forms"].append("VA Form 21-526EZ (Disability Compensation — note Agent Orange exposure)")
        result["key_resources"].append(
            "VA Agent Orange information — va.gov/disability/eligibility/hazardous-materials-exposure/agent-orange"
        )
        if not result["next_action"]:
            result["next_action"] = (
                "Contact your VSO and request a review of ALL your conditions against "
                "the full Agent Orange presumptive list — it expanded significantly in 2022. "
                "Many veterans who were denied years ago now qualify."
            )
        result["notes"].append(
            "The PACT Act 2022 added conditions to the Agent Orange presumptive list. "
            "Hypertension alone — which many Vietnam veterans have — is now presumptive. "
            "If you have any of the listed conditions and served in a covered location, "
            "you may have a valid claim you don't know about."
        )

    # ── TRACK 3: CAMP LEJEUNE ─────────────────────────────────────────────────
    if "camp_lejeune" in types or profile.camp_lejeune or profile.is_lejeune_family_member:
        result["flags"].append("camp_lejeune_track")
        result["primary_path"] = result["primary_path"] or "Camp Lejeune — PACT Act / Justice Act"

        if profile.is_lejeune_family_member:
            result["flags"].append("lejeune_family_member")
            result["secondary_options"].extend([
                "Camp Lejeune Justice Act (2022) — family members who lived at Camp Lejeune "
                "between August 1, 1953 and December 31, 1987 for 30+ days can file a tort claim "
                "against the U.S. government for covered conditions. "
                "File in U.S. District Court, Eastern District of North Carolina. "
                "You need an attorney for this — search 'Camp Lejeune attorney' for contingency-fee counsel.",
                "VA health care for family members — also available under the PACT Act "
                "if you meet eligibility criteria.",
            ])
        else:
            result["secondary_options"].extend([
                "VA health care — veterans who served at Camp Lejeune between August 1, 1953 "
                "and December 31, 1987 for at least 30 cumulative days qualify for FREE VA health care "
                "for 15 qualifying conditions. No co-pays. No need to prove service connection.",
                f"15 qualifying conditions for VA healthcare include: "
                f"{', '.join(LEJEUNE_CONDITIONS[:7])}, and more. "
                "Full list at va.gov/disability/eligibility/hazardous-materials-exposure/camp-lejeune-water-contamination.",
                "Camp Lejeune Justice Act tort claim — you may also sue the U.S. government "
                "separately for damages. This requires an attorney and is filed in federal court. "
                "VA benefits and tort claim are independent — you can pursue both.",
                "Disability claim — service connection for Camp Lejeune-related conditions "
                "is available through the standard VA disability process. "
                "File VA Form 21-526EZ, note Camp Lejeune water contamination.",
            ])

        result["key_forms"].extend([
            "VA Form 10-10068 (Camp Lejeune Family Member Application — if family member)",
            "VA Form 21-526EZ (Disability Compensation — if veteran)",
        ])
        result["key_resources"].append(
            "VA Camp Lejeune information — va.gov/disability/eligibility/hazardous-materials-exposure/camp-lejeune-water-contamination"
        )
        if not result["next_action"]:
            result["next_action"] = (
                "Call 1-866-606-8198 (VA Camp Lejeune helpline) or go to va.gov/Camp-Lejeune. "
                "Gather any documentation of your time at Camp Lejeune — orders, housing records, unit records. "
                "Even approximate dates are enough to start."
            )
        result["key_resources"].append("VA Camp Lejeune helpline — 1-866-606-8198")

    # ── TRACK 4: GULF WAR SYNDROME ────────────────────────────────────────────
    if "gulf_war_syndrome" in types or (era == "gulf_war" and "burn_pit" not in types):
        result["flags"].append("gulf_war_syndrome_track")
        result["primary_path"] = result["primary_path"] or "Gulf War Syndrome — Presumptive Service Connection"

        result["secondary_options"].extend([
            "Gulf War Syndrome is a recognized group of presumptive conditions for veterans "
            "who served in the Southwest Asia theater on or after August 2, 1990. "
            "You do NOT need to prove what caused your symptoms — you only need to have "
            "served in a covered location and have a qualifying condition.",
            f"Presumptive conditions include: {', '.join(GULF_WAR_PRESUMPTIVES[:4])}. "
            "Critically: 'undiagnosed illness with objective indications' is a category — "
            "meaning symptoms that can't be explained by a specific diagnosis still qualify.",
            "Gulf War Illness Research Program — VA actively funds research and the findings "
            "continue to expand the presumptive list. If denied before, watch for updates.",
        ])
        result["key_forms"].append("VA Form 21-526EZ (note 'Gulf War' service and specific symptoms)")
        result["key_resources"].append(
            "Gulf War Veterans' Medically Unexplained Illnesses — va.gov/disability/eligibility/hazardous-materials-exposure/gulf-war-illness"
        )
        result["notes"].append(
            "Gulf War veterans: If you have chronic, unexplained fatigue, pain, GI issues, "
            "or neurological symptoms — these may qualify as Gulf War Illness even if no "
            "specific diagnosis has been made. 'Medically unexplained' is itself a valid category. "
            "Do not let doctors telling you 'we can't find anything wrong' stop your claim."
        )
        if not result["next_action"]:
            result["next_action"] = (
                "Contact a VSO and list ALL your symptoms — even the ones you think are unrelated. "
                "Gulf War Illness claims are broader than most veterans realize. "
                "Request Gulf War Registry health exam at va.gov/disability/eligibility/hazardous-materials-exposure/gulf-war-illness."
            )

    # ── TRACK 5: RADIATION ────────────────────────────────────────────────────
    if "radiation" in types:
        result["flags"].append("radiation_track")
        result["primary_path"] = result["primary_path"] or "Radiation Exposure — Atomic Veterans + RECA"

        result["secondary_options"].extend([
            "Radiation-Risk Activity presumptive — veterans who participated in atmospheric "
            "nuclear testing, occupied Hiroshima or Nagasaki after WWII, were POWs in Japan, "
            "or were exposed at certain facilities qualify for presumptive service connection "
            "for a list of radiogenic cancers.",
            "RECA (Radiation Exposure Compensation Act) — separate Department of Justice program "
            "for uranium miners, millers, ore transporters, and downwinders from Nevada Test Site. "
            "Provides lump-sum compensation in addition to VA benefits. "
            "Apply at justice.gov/civil/common/reca.",
            "Palomares, Spain (1966) and Enewetak Atoll (1977–1980) cleanup veterans "
            "have specific eligibility. VA has a Radiation Dose Assessment program.",
        ])
        result["key_forms"].append("VA Form 21-526EZ (Disability — note radiation exposure activity)")
        result["key_resources"].extend([
            "VA Radiation Exposure — va.gov/disability/eligibility/hazardous-materials-exposure/radiation-exposure",
            "RECA — Department of Justice — justice.gov/civil/common/reca",
        ])
        if not result["next_action"]:
            result["next_action"] = (
                "Contact the VA Radiation Dose Assessment team through your VA Regional Office. "
                "They reconstruct your estimated radiation dose from your service records — "
                "this is required for radiation-related claims."
            )

    # ── TRACK 6: PFAS / FOREVER CHEMICALS ────────────────────────────────────
    if "pfas" in types:
        result["flags"].append("pfas_track")
        result["primary_path"] = result["primary_path"] or "PFAS / Firefighting Foam — Contaminated Installations"

        result["secondary_options"].extend([
            "PFAS (per- and polyfluoroalkyl substances) contamination from AFFF (aqueous film-forming foam) "
            "used at military airfields and fire training areas. Linked to: kidney cancer, testicular cancer, "
            "thyroid disease, ulcerative colitis, high cholesterol, pregnancy-induced hypertension.",
            "No VA presumptive list yet for PFAS specifically — but individual service connection claims "
            "are possible if you can document exposure (duty station records, proximity to flight lines "
            "or fire training areas) and have a qualifying condition.",
            "EWG (Environmental Working Group) military PFAS database — check if your installation "
            "is listed at ewg.org/interactive-maps/2019_pfas/. Installation lists can support your claim.",
            "Congressional pressure is building for PFAS presumptive status — file now to establish "
            "your effective date before a presumptive is added. A filed claim preserves your date.",
        ])
        result["key_forms"].append("VA Form 21-526EZ (Document duty station, proximity to fire training areas, AFFF contact)")
        result["key_resources"].extend([
            "EWG Military PFAS Database — ewg.org/interactive-maps/2019_pfas/",
            "Agency for Toxic Substances and Disease Registry — atsdr.cdc.gov (PFAS health effects)",
        ])
        result["notes"].append(
            "PFAS claims require more documentation than PACT Act presumptive claims. "
            "File NOW to lock in your effective date — even if the claim is initially denied. "
            "A presumptive rule may come; your filing date determines your back pay."
        )
        if not result["next_action"]:
            result["next_action"] = (
                "Document your installation and proximity to fire training areas in your service records. "
                "File VA Form 21-526EZ now to lock in your effective date. "
                "Contact NVLSP (nvlsp.org) — they have PFAS-specific claim expertise."
            )

    # ── PREVIOUSLY DENIED — REFILE NOTE (UNIVERSAL) ───────────────────────────
    if profile.was_previously_denied:
        result["flags"].append("previously_denied_refile")
        if "refile_candidate" not in result["flags"]:
            result["notes"].append(
                "YOUR DENIAL MAY NOT BE FINAL. The PACT Act (2022) and other policy changes "
                "have opened claims that were previously impossible to win. "
                "File a Supplemental Claim (VA Form 20-0995) citing the PACT Act as new and relevant evidence. "
                "A VSO can review your denial letter and tell you exactly what changed."
            )
            result["key_forms"].append("VA Form 20-0995 (Supplemental Claim — cite PACT Act or policy change)")

    # ── HEALTHCARE ENROLLMENT NOTE ─────────────────────────────────────────────
    if not profile.enrolled_va_healthcare:
        result["secondary_options"].append(
            "Enroll in VA health care first — PACT Act expanded eligibility. "
            "Veterans with toxic exposure service may now qualify even if previously denied healthcare. "
            "Apply at va.gov/health-care/apply or call 1-800-827-1000."
        )
        result["notes"].append(
            "VA healthcare enrollment unlocks the free toxic exposure health screening — "
            "a baseline exam that documents your current health status and can support future claims."
        )

    # ── UNIVERSAL RESOURCES ───────────────────────────────────────────────────
    result["key_resources"].extend([
        "PACT Act information — va.gov/pact-act-information",
        "VA Toxic Exposure claims — va.gov/disability/eligibility/hazardous-materials-exposure",
        "DAV PACT Act assistance — dav.org/pact-act (free claims help)",
        "Burn Pits 360 — burnpits360.org — veteran-led burn pit advocacy + claims support",
        "NVLSP — nvlsp.org — free legal help for toxic exposure claims",
    ])

    # ── FALLBACK ──────────────────────────────────────────────────────────────
    if not result["primary_path"]:
        result["primary_path"] = "Toxic Exposure Review — PACT Act May Apply"
        result["next_action"] = (
            "Call 1-800-827-1000 and ask specifically about PACT Act eligibility and "
            "the Airborne Hazards and Open Burn Pit Registry. "
            "Contact a VSO for a full toxic exposure review."
        )

    return result
