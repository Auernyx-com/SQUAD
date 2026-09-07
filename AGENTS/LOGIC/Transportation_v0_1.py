"""
Transportation_v0_1.py
SQUAD BAT — Transportation Division routing engine.

Tracks:
  1. VA Beneficiary Travel   — BTSSS mileage reimbursement, special mode transport
  2. DAV Transportation      — free DAV van service to VA appointments
  3. Adaptive Vehicle Grants — VA automobile allowance, adaptive equipment
  4. Community / Rural       — volunteer driver programs, rural transit, Uber Health
  5. In-State Programs       — state-funded veteran transport programs
  6. Crisis Transport        — emergency transport for crisis situations

Gate: Transportation barriers never block access to care.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class VetTransportProfile:
    # What transport need(s) they have (multi-select)
    # "va_appointment" | "adaptive_vehicle" | "rural" | "daily_transit" |
    # "crisis" | "relocation"
    transport_needs: List[str] = field(default_factory=list)

    # Do they have a VA-rated service-connected disability?
    has_sc_disability: bool = False

    # Service-connected disability rating (0–100 or None)
    disability_rating: Optional[int] = None

    # Enrolled in VA health care
    enrolled_va_healthcare: bool = False

    # Rural or highly rural location
    is_rural: bool = False

    # Has personal vehicle
    has_vehicle: bool = True

    # Can drive (or has driver)
    can_drive: bool = True

    # Needs adaptive vehicle or equipment
    needs_adaptive_vehicle: bool = False

    # Location
    state: str = ""
    county: str = ""


# ── Main router ───────────────────────────────────────────────────────────────

def route_transportation(profile: VetTransportProfile) -> dict:
    result = {
        "primary_path": None,
        "secondary_options": [],
        "flags": [],
        "next_action": None,
        "key_resources": [],
        "key_forms": [],
        "notes": [],
    }

    needs = [n.lower() for n in profile.transport_needs]
    rating = profile.disability_rating or 0

    # Independent-audit finding (2026-09-06), round 3, critical: TRACK 6
    # (crisis, below) is correctly guarded (`result["primary_path"] or
    # (...)`, `if not result["next_action"]`) specifically so it never
    # clobbers whatever ran first -- but every earlier track (TRACK 1's
    # BTSSS guidance, and TRACK 2's DAV guidance once TRACK 1 stepped aside)
    # claims those same two fields unconditionally or with the same "first
    # to run wins" guard, so a veteran who also selected "crisis" got
    # ordinary transportation guidance as their primary_path/next_action,
    # with the crisis guidance ("Call 988 press 1... or 911. Do not wait.")
    # never reaching those two fields at all -- even though
    # crisis_transport_track correctly fired and crisis text was added to
    # secondary_options/key_resources further down. Confirmed with two
    # separate scenarios before this fix; patching TRACK 1 alone wasn't
    # enough (TRACK 2 has the identical latent bug, only masked by TRACK 1
    # until TRACK 1 was fixed). Fixed structurally instead of track-by-track:
    # crisis claims primary_path/next_action FIRST, before any other track
    # runs, so every later track's existing "don't clobber" guard correctly
    # no-ops on these two fields exactly as it was already written to.
    # TRACK 6 below still runs at its original position for its other
    # contributions (secondary_options/key_resources/notes/flags) -- this
    # does not change where those are added, only which track wins the
    # headline fields.
    if "crisis" in needs:
        result["primary_path"] = "Crisis Transport — Immediate Resources"
        result["next_action"] = "Call 988 press 1 (Veterans Crisis Line) or 911. Do not wait."

    # ── TRACK 1: VA BENEFICIARY TRAVEL (BTSSS) ────────────────────────────────
    if "va_appointment" in needs or profile.enrolled_va_healthcare:
        result["flags"].append("va_beneficiary_travel")
        result["primary_path"] = result["primary_path"] or "VA Beneficiary Travel — BTSSS Mileage Reimbursement"

        # Eligibility determination
        eligible_travel = (
            rating >= 30
            or profile.has_sc_disability  # any SC disability qualifies
        )

        if eligible_travel:
            result["secondary_options"].append(
                "BTSSS (Beneficiary Travel Self Service System) — submit mileage reimbursement claims "
                "online at va.gov/health-care/get-reimbursed-for-travel-pay. "
                "Rate: 41.5 cents/mile (subject to annual change), minus $3 deductible per trip "
                "($18/month max deductible). "
                "Submit within 30 days of appointment."
            )
            result["key_forms"].append("VA Form 10-3542 (Beneficiary Travel Claim — paper fallback)")
            result["key_resources"].append("BTSSS Portal — va.gov/health-care/get-reimbursed-for-travel-pay")
            result["flags"].append("btsss_eligible")
            result["next_action"] = result["next_action"] or (
                "Register for BTSSS at va.gov/health-care/get-reimbursed-for-travel-pay. "
                "Submit claims within 30 days of each appointment. "
                "You can submit at the VA facility kiosk or online."
            )
        else:
            result["notes"].append(
                "BTSSS mileage reimbursement generally requires a 30%+ SC disability rating or "
                "specific eligibility criteria (financial hardship, receiving VA pension, etc.). "
                "Ask your VA travel office — eligibility is broader than most veterans realize."
            )
            result["secondary_options"].append(
                "BTSSS Special Mode Transport — if you cannot drive due to medical condition, "
                "VA may cover ambulance, wheelchair van, or other transport regardless of rating. "
                "Requires VA pre-authorization. Contact your VA travel office."
            )

        # Special mode transport
        if not profile.can_drive or profile.needs_adaptive_vehicle:
            result["secondary_options"].append(
                "VA Special Mode Transportation — for veterans who cannot use personal vehicle "
                "due to medical condition. Covers ambulance, wheelchair van, stretcher van. "
                "Must be pre-authorized by VA. Contact your VA facility travel office."
            )
            result["flags"].append("special_mode_candidate")

    # ── TRACK 2: DAV TRANSPORTATION NETWORK ───────────────────────────────────
    if "va_appointment" in needs or "daily_transit" in needs:
        result["secondary_options"].append(
            "DAV (Disabled American Veterans) Transportation Network — "
            "free rides to and from VA medical appointments. "
            "Volunteer drivers, no cost to veteran. "
            "Contact your local DAV chapter: dav.org/find-a-chapter or call 1-800-424-3838."
        )
        result["key_resources"].append("DAV Transportation Network — dav.org/find-a-chapter")
        result["flags"].append("dav_transport_option")
        if not result["next_action"]:
            result["next_action"] = (
                "Call your local DAV chapter to schedule a ride: "
                "find chapters at dav.org/find-a-chapter or call 1-800-424-3838. "
                "Schedule at least 48–72 hours in advance."
            )

    # ── TRACK 3: ADAPTIVE VEHICLE GRANTS ──────────────────────────────────────
    if "adaptive_vehicle" in needs or profile.needs_adaptive_vehicle:
        result["flags"].append("adaptive_vehicle_track")
        result["primary_path"] = result["primary_path"] or "VA Adaptive Vehicle Benefits"

        if rating >= 0 and profile.has_sc_disability:
            result["secondary_options"].extend([
                "VA Automobile Allowance — one-time grant up to $22,426 (2024 rate, adjusts annually) "
                "for veterans with SC loss of use of hand/foot or severe visual impairment. "
                "Apply via VA Form 21-4502.",
                "Adaptive Equipment Grant — up to $24,239 (2024 rate) for adaptive equipment "
                "(hand controls, power steering, etc.) on top of automobile allowance. "
                "Can be used on a vehicle you already own.",
            ])
            result["key_forms"].extend([
                "VA Form 21-4502 (Automobile Allowance Application)",
                "VA Form 10-1394 (Adaptive Equipment)",
            ])
            result["notes"].append(
                "Automobile allowance is a one-time benefit. Adaptive equipment can be re-used "
                "on subsequent vehicles. Both require SC disability affecting driving ability. "
                "Work with a VA driver rehabilitation specialist first — they document the need."
            )
        else:
            result["notes"].append(
                "VA adaptive vehicle benefits require a service-connected disability affecting "
                "your ability to drive. Contact VA to establish service connection first if you haven't."
            )

        result["key_resources"].append("VA Adaptive Sports + Vehicles — va.gov/disability/eligibility/special-claims/automobile-allowance-adaptive-equipment")

    # ── TRACK 4: COMMUNITY & RURAL TRANSPORT ──────────────────────────────────
    if "rural" in needs or "daily_transit" in needs or profile.is_rural:
        result["flags"].append("rural_transport_track")
        result["primary_path"] = result["primary_path"] or "Community & Rural Transportation"

        result["secondary_options"].extend([
            "211.org — call or text 211 for local transportation resources including "
            "volunteer driver programs, senior/veteran transit, and rural options.",
            "VA Highly Rural Transport Grants (HRTG) — federally funded programs that provide "
            "free transport to highly rural veterans. Ask your VA facility social worker.",
            "Veterans Transportation Service (VTS) — VA-funded community transport in some areas. "
            "Check with your VA PACT Act navigator or social worker.",
            "State transit authority — many states have reduced-fare or free transit programs for veterans. "
            "Search '[your state] veteran transit discount'.",
        ])
        result["key_resources"].extend([
            "211.org — local transportation resources",
            "VA Rural Health Resource Center — ruralhealth.va.gov",
        ])

        if profile.is_rural:
            result["notes"].append(
                "VA designates rural and highly rural veterans for additional transport support. "
                "Ask your VA facility specifically about Highly Rural Transport Grant (HRTG) programs — "
                "these funds are underutilized because veterans don't ask."
            )

        if not result["next_action"]:
            result["next_action"] = (
                "Call 211 for immediate local transport options. "
                "Contact your VA facility's social worker about rural transport grants."
            )

    # ── TRACK 5: IN-STATE PROGRAMS ────────────────────────────────────────────
    state = (profile.state or "").upper()
    if state == "CO" or (state and ("daily_transit" in needs or "va_appointment" in needs)):
        result["flags"].append("state_transport_programs")

        if state == "CO":
            result["secondary_options"].extend([
                "Colorado Veterans Community Living Centers — transport included with residential care programs.",
                "CDOT Mobility Programs — Colorado Department of Transportation has reduced-fare options "
                "for veterans. Check cotrip.org or call 303-757-9011.",
                "Western Slope specific: RFTA (Roaring Fork Transit Authority) and "
                "Grand Valley Transit (GVT) offer reduced fares for disabled veterans. "
                "Contact your local transit authority.",
            ])
            result["notes"].append(
                "Western Slope Colorado has limited public transit. "
                "DAV van service and VA telehealth are often the most reliable options for remote veterans."
            )
        else:
            result["secondary_options"].append(
                f"Search '{state} veteran transportation assistance' for state-specific programs. "
                "Most states have a Department of Veterans Affairs with transport coordination."
            )

    # ── TRACK 6: CRISIS TRANSPORT ─────────────────────────────────────────────
    if "crisis" in needs:
        result["flags"].append("crisis_transport_track")
        result["primary_path"] = result["primary_path"] or "Crisis Transport — Immediate Resources"
        result["secondary_options"].extend([
            "Veterans Crisis Line — call 988, press 1; text 838255; chat at veteranscrisisline.net. "
            "They can coordinate transport to VA emergency care.",
            "911 — for immediate life-threatening emergencies; VA will cover the ambulance cost "
            "if you are transported to a VA facility.",
            "VA Emergency Care — if no VA facility nearby, VA covers emergency care at non-VA ERs "
            "for enrolled veterans with no other coverage. Notify VA within 72 hours.",
        ])
        result["notes"].append(
            "VA covers non-VA ER visits for enrolled veterans when the situation is a genuine emergency "
            "and no VA facility was reasonably available. Call VA within 72 hours to report the visit."
        )
        result["key_resources"].append("Veterans Crisis Line — 988 press 1 | text 838255")
        if not result["next_action"]:
            result["next_action"] = "Call 988 press 1 (Veterans Crisis Line) or 911. Do not wait."

    # ── TELEHEALTH NOTE (always relevant if VA-enrolled) ──────────────────────
    if profile.enrolled_va_healthcare or "va_appointment" in needs:
        result["notes"].append(
            "VA telehealth can eliminate the transport barrier entirely for many appointment types. "
            "Ask your VA care team what can be done via VA Video Connect — it's expanded significantly."
        )
        result["key_resources"].append("VA Video Connect (telehealth) — telehealth.va.gov")

    # ── FALLBACK ──────────────────────────────────────────────────────────────
    if not result["primary_path"]:
        result["primary_path"] = "Transportation Assistance — Multiple Resources Available"
        result["secondary_options"].extend([
            "211.org — local transportation resources by ZIP code",
            "DAV Transportation Network — dav.org/find-a-chapter",
            "VA Beneficiary Travel — va.gov/health-care/get-reimbursed-for-travel-pay",
        ])
        result["next_action"] = (
            "Call 211 for local options or contact your VA facility social worker."
        )

    return result
