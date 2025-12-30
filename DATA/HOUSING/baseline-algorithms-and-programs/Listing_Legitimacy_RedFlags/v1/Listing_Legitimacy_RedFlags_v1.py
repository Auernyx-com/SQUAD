"""Listing_Legitimacy_RedFlags_v1

Deterministic pre-screen for common rental-listing legitimacy red flags.

This module is intentionally rules-only (no web calls, no ML).

Version: v1
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Mapping, Optional


YesNoUnknown = Literal["yes", "no", "unknown"]
RiskLevel = Literal["LOW", "MED", "HIGH"]
LegitimacyStatus = Literal["LEGIT_LIKELY", "SCAM_LIKELY", "UNKNOWN", "NEEDS_VERIFICATION"]
Severity = Literal["LOW", "MED", "HIGH"]


class ListingLegitimacyError(ValueError):
    pass


@dataclass(frozen=True)
class RedFlag:
    code: str
    severity: Severity
    evidence: str


@dataclass(frozen=True)
class ListingLegitimacyOutput:
    legitimacyStatus: LegitimacyStatus
    riskLevel: RiskLevel
    riskScore: int
    redFlags: List[Dict[str, str]]
    nextSteps: List[str]
    notes: List[str]


def _yn(name: str, value: Any) -> YesNoUnknown:
    if value not in ("yes", "no", "unknown"):
        raise ListingLegitimacyError(f"{name} must be yes|no|unknown, got: {value!r}")
    return value  # type: ignore[return-value]


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _add_step_unique(steps: List[str], step: str) -> None:
    if step not in steps:
        steps.append(step)


def _score_to_level(score: int) -> RiskLevel:
    if score >= 70:
        return "HIGH"
    if score >= 35:
        return "MED"
    return "LOW"


def _status_from(score: int, has_high_sev: bool, unknown_count: int) -> LegitimacyStatus:
    # Conservative classification:
    # - If any HIGH severity indicator or score is very high -> SCAM_LIKELY.
    # - If score is medium and we have many unknowns -> NEEDS_VERIFICATION.
    # - If score is low -> LEGIT_LIKELY.
    # - Otherwise -> UNKNOWN.
    if has_high_sev or score >= 85:
        return "SCAM_LIKELY"

    if score <= 20 and unknown_count <= 2:
        return "LEGIT_LIKELY"

    if score >= 35 and unknown_count >= 4:
        return "NEEDS_VERIFICATION"

    if score >= 55:
        return "NEEDS_VERIFICATION"

    return "UNKNOWN"


def evaluate_listing_legitimacy(data: Mapping[str, Any]) -> ListingLegitimacyOutput:
    """Evaluates listing legitimacy red flags.

    Expected input matches schema_Listing_Legitimacy_RedFlags_v1.json.
    """

    listing = data.get("listing")
    if not isinstance(listing, Mapping):
        raise ListingLegitimacyError("Input must contain object: listing")

    notes: List[str] = []
    red_flags: List[RedFlag] = []
    next_steps: List[str] = []

    # ---- Pull common fields ----
    platform = _safe_str(listing.get("platform")).strip() or "unknown"

    location = listing.get("location")
    if not isinstance(location, Mapping):
        raise ListingLegitimacyError("listing.location must be an object")
    address_or_area = _safe_str(location.get("addressOrArea")).strip()

    price = listing.get("price")
    if not isinstance(price, Mapping):
        raise ListingLegitimacyError("listing.price must be an object")
    rent_monthly_raw = price.get("rentMonthly")
    if not isinstance(rent_monthly_raw, (int, float)):
        raise ListingLegitimacyError("listing.price.rentMonthly must be a number")
    rent_monthly = float(rent_monthly_raw)

    rent_far_below_market = _yn("listing.price.rentSeemsFarBelowMarket", price.get("rentSeemsFarBelowMarket"))

    contact = listing.get("contact")
    if not isinstance(contact, Mapping):
        raise ListingLegitimacyError("listing.contact must be an object")
    identity_clear = _yn("listing.contact.identityClear", contact.get("identityClear"))

    contact_methods_raw = contact.get("contactMethods")
    contact_methods: List[str] = []
    if isinstance(contact_methods_raw, list):
        contact_methods = [str(x) for x in contact_methods_raw]

    payment = listing.get("paymentSignals")
    if not isinstance(payment, Mapping):
        raise ListingLegitimacyError("listing.paymentSignals must be an object")

    upfront_before_viewing = _yn(
        "listing.paymentSignals.requestsUpfrontPaymentBeforeViewing",
        payment.get("requestsUpfrontPaymentBeforeViewing"),
    )
    deposit_hold_no_lease = _yn(
        "listing.paymentSignals.requestsDepositToHoldWithoutLease",
        payment.get("requestsDepositToHoldWithoutLease"),
    )
    app_fee_before_tour = _yn(
        "listing.paymentSignals.requestsApplicationFeeBeforeTour",
        payment.get("requestsApplicationFeeBeforeTour", "unknown"),
    )
    asks_ssn_id_before_tour = _yn(
        "listing.paymentSignals.asksForSocialSecurityOrIDBeforeTour",
        payment.get("asksForSocialSecurityOrIDBeforeTour", "unknown"),
    )

    payment_method = _safe_str(payment.get("paymentMethodRequested")).strip() or "unknown"
    cashapp_venmo_zelle_only = _yn(
        "listing.paymentSignals.requestsCashAppVenmoZelleOnly",
        payment.get("requestsCashAppVenmoZelleOnly"),
    )

    comms = listing.get("communicationSignals")
    if not isinstance(comms, Mapping):
        raise ListingLegitimacyError("listing.communicationSignals must be an object")

    pushes_off_platform = _yn(
        "listing.communicationSignals.pushesOffPlatformCommunication",
        comms.get("pushesOffPlatformCommunication"),
    )
    urgency_pressure = _yn(
        "listing.communicationSignals.createsUrgencyPressure",
        comms.get("createsUrgencyPressure"),
    )
    refuses_live_call = _yn(
        "listing.communicationSignals.refusesLiveCallOrVideoTour",
        comms.get("refusesLiveCallOrVideoTour"),
    )
    avoids_in_person = _yn(
        "listing.communicationSignals.avoidsInPersonShowing",
        comms.get("avoidsInPersonShowing"),
    )
    out_of_state_story = _yn(
        "listing.communicationSignals.claimsOutOfStateOrMissionaryOrMilitaryStory",
        comms.get("claimsOutOfStateOrMissionaryOrMilitaryStory", "unknown"),
    )

    content = listing.get("contentSignals")
    if not isinstance(content, Mapping):
        raise ListingLegitimacyError("listing.contentSignals must be an object")

    has_exact_address = _yn("listing.contentSignals.hasExactAddress", content.get("hasExactAddress"))
    has_interior_photos = _yn("listing.contentSignals.hasInteriorPhotos", content.get("hasInteriorPhotos"))
    photo_count_raw = content.get("photoCount")
    if not isinstance(photo_count_raw, int):
        raise ListingLegitimacyError("listing.contentSignals.photoCount must be an integer")
    photo_count = photo_count_raw

    typos_generic = _yn(
        "listing.contentSignals.descriptionHasManyTyposOrGenericText",
        content.get("descriptionHasManyTyposOrGenericText"),
    )
    no_checks_claim = _yn(
        "listing.contentSignals.claimsNoBackgroundCheckNoCreditCheck",
        content.get("claimsNoBackgroundCheckNoCreditCheck"),
    )

    # ---- Rule scoring ----
    # Scoring is additive; cap at 100.
    score = 0

    def add_flag(*, code: str, severity: Severity, points: int, evidence: str, step: Optional[str] = None) -> None:
        nonlocal score
        red_flags.append(RedFlag(code=code, severity=severity, evidence=evidence))
        score = min(100, score + points)
        if step:
            _add_step_unique(next_steps, step)

    def count_unknown(values: List[YesNoUnknown]) -> int:
        return sum(1 for v in values if v == "unknown")

    unknown_count = count_unknown(
        [
            rent_far_below_market,
            identity_clear,
            upfront_before_viewing,
            deposit_hold_no_lease,
            app_fee_before_tour,
            asks_ssn_id_before_tour,
            cashapp_venmo_zelle_only,
            pushes_off_platform,
            urgency_pressure,
            refuses_live_call,
            avoids_in_person,
            out_of_state_story,
            has_exact_address,
            has_interior_photos,
            typos_generic,
            no_checks_claim,
        ]
    )

    # HIGH severity: payment fraud patterns
    if payment_method in ("gift_cards", "crypto", "wire"):
        add_flag(
            code="PAYMENT_METHOD_HIGH_RISK",
            severity="HIGH",
            points=45,
            evidence=f"Payment method requested: {payment_method}.",
            step="Do not send any money; stop and verify ownership/agency identity first.",
        )

    if upfront_before_viewing == "yes":
        add_flag(
            code="UPFRONT_PAYMENT_BEFORE_VIEWING",
            severity="HIGH",
            points=40,
            evidence="Requested payment before viewing/tour.",
            step="Refuse upfront payments; require an in-person tour or live video walkthrough at the unit.",
        )

    if deposit_hold_no_lease == "yes":
        add_flag(
            code="DEPOSIT_TO_HOLD_WITHOUT_LEASE",
            severity="HIGH",
            points=35,
            evidence="Requested deposit to hold the unit without a signed lease.",
            step="Require a written lease or holding agreement with verified owner/agent identity.",
        )

    if asks_ssn_id_before_tour == "yes":
        add_flag(
            code="ASKS_SSN_ID_BEFORE_TOUR",
            severity="HIGH",
            points=30,
            evidence="Asked for SSN/ID before any verified showing.",
            step="Do not provide SSN; use minimal identity info until legitimacy is verified.",
        )

    # MED severity: pressure + evasion + identity ambiguity
    if identity_clear == "no":
        add_flag(
            code="CONTACT_IDENTITY_UNCLEAR",
            severity="MED",
            points=20,
            evidence="Contact identity/role not clear.",
            step="Ask for full legal name, company (if any), and a verifiable office phone + license/registration where applicable.",
        )

    if pushes_off_platform == "yes":
        add_flag(
            code="PUSHES_OFF_PLATFORM",
            severity="MED",
            points=15,
            evidence=f"Pushed communication off-platform (contact methods: {contact_methods}).",
            step="Keep communication on-platform until the unit and identity are verified.",
        )

    if refuses_live_call == "yes":
        add_flag(
            code="REFUSES_LIVE_CALL_OR_VIDEO",
            severity="MED",
            points=15,
            evidence="Refused live call or live video tour.",
            step="Request a live video tour showing street, building entry, and inside the unit in one continuous call.",
        )

    if avoids_in_person == "yes":
        add_flag(
            code="AVOIDS_IN_PERSON_SHOWING",
            severity="MED",
            points=15,
            evidence="Avoided in-person showing.",
            step="Only proceed after a verified showing with access to the actual unit.",
        )

    if urgency_pressure == "yes":
        add_flag(
            code="URGENCY_PRESSURE",
            severity="MED",
            points=10,
            evidence="Created urgency pressure (""many applicants"", ""pay now"", etc.).",
            step="Slow down: verify unit ownership and terms before paying or sharing sensitive info.",
        )

    if out_of_state_story == "yes":
        add_flag(
            code="OUT_OF_STATE_STORY",
            severity="MED",
            points=10,
            evidence="Used common ""out of state"" / ""military"" / ""missionary"" story.",
            step="Ask for a local licensed property manager or verified representative for showings and lease signing.",
        )

    if app_fee_before_tour == "yes":
        add_flag(
            code="APPLICATION_FEE_BEFORE_TOUR",
            severity="MED",
            points=12,
            evidence="Requested application fee before any verified tour.",
            step="Do not pay application fees until you have toured and verified the unit and landlord identity.",
        )

    if cashapp_venmo_zelle_only == "yes":
        add_flag(
            code="PAYMENT_APP_ONLY",
            severity="MED",
            points=15,
            evidence="Requested payment via cash-app only (CashApp/Venmo/Zelle-only).",
            step="If any payment is legitimate later, use traceable methods tied to a verified business/owner and a written agreement.",
        )

    # LOW/MED severity: listing content signals
    if has_exact_address == "no":
        add_flag(
            code="NO_EXACT_ADDRESS",
            severity="MED",
            points=12,
            evidence=f"Address not provided (addressOrArea={address_or_area!r}).",
            step="Get the exact address and verify it independently before proceeding.",
        )

    if has_interior_photos == "no":
        add_flag(
            code="NO_INTERIOR_PHOTOS",
            severity="LOW",
            points=8,
            evidence="No interior photos provided.",
            step="Request interior photos and a live walkthrough; compare details to the address/unit.",
        )

    if photo_count <= 2:
        add_flag(
            code="VERY_FEW_PHOTOS",
            severity="LOW",
            points=6,
            evidence=f"Very few photos provided (photoCount={photo_count}).",
            step="Request additional photos including kitchen, bath, bedrooms, entry, and exterior.",
        )

    if typos_generic == "yes":
        add_flag(
            code="GENERIC_OR_TYPO_HEAVY_DESCRIPTION",
            severity="LOW",
            points=6,
            evidence="Description appears generic/typo-heavy.",
        )

    if no_checks_claim == "yes":
        add_flag(
            code="CLAIMS_NO_CHECKS",
            severity="MED",
            points=12,
            evidence="Claims no background check / no credit check.",
            step="Be cautious; verify the landlord/agent and ensure the lease is real and enforceable.",
        )

    if rent_far_below_market == "yes" and rent_monthly > 0:
        add_flag(
            code="PRICE_TOO_GOOD_TO_BE_TRUE",
            severity="MED",
            points=15,
            evidence=f"Rent appears far below market (rentMonthly={rent_monthly:.2f}).",
            step="Compare rent to 3–5 similar units nearby; treat large gaps as a verification trigger.",
        )

    # Baseline next steps for all cases
    _add_step_unique(next_steps, "Verify ownership/management: look up the property on official county/assessor or recorder sources (or a trusted property database).")
    _add_step_unique(next_steps, "Never send money or SSN before verifying the unit, identity, and paperwork.")

    has_high_sev = any(r.severity == "HIGH" for r in red_flags)
    risk_level = _score_to_level(score)
    legitimacy_status = _status_from(score, has_high_sev, unknown_count)

    notes.append(f"platform={platform!r}")
    notes.append(f"riskScore={score} (capped 0-100)")
    notes.append(f"unknownSignals={unknown_count}")

    # Emit as plain JSON-serializable dicts
    red_flags_out: List[Dict[str, str]] = [
        {"code": r.code, "severity": r.severity, "evidence": r.evidence} for r in red_flags
    ]

    return ListingLegitimacyOutput(
        legitimacyStatus=legitimacy_status,
        riskLevel=risk_level,
        riskScore=score,
        redFlags=red_flags_out,
        nextSteps=next_steps,
        notes=notes,
    )


def _demo() -> None:
    with open("example_input.json", "r", encoding="utf-8") as f:
        payload = json.load(f)

    result = evaluate_listing_legitimacy(payload)
    print(json.dumps(result.__dict__, indent=2))


if __name__ == "__main__":
    _demo()
