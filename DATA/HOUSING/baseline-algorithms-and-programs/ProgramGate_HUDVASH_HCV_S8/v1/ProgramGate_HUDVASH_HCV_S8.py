"""ProgramGate_HUDVASH_HCV_S8

Single authoritative module for HUD-VASH / HCV / Section 8 program rule integration.

Core principle:
HUD-VASH operates through the HCV framework via the PHA. Subsidy math + approval gates
apply the same way, with HUD-VASH-specific policy constraints layered on top.

This module:
- Normalizes voucher program inputs
- Resolves utility allowance (required for gross rent)
- Computes gross rent / tenant share estimates
- Applies hard program gates (40% initial cap, off-book side payments)
- Flags rent reasonableness risk (if provided)
- Emits standardized output + auto-generated "Ask PHA" action set when UNKNOWN

Local tweaks should go into PHAOverrides_<County/City>.json (see overrides template).

Version: v1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Mapping, Optional, Tuple


ProgramType = Literal["HUD-VASH", "HCV", "Section8", "Other"]
GateStatus = Literal["PASS", "FAIL", "UNKNOWN", "FAIL_PENDING_PHA"]
Responsibility = Literal["tenant", "owner", "ignore"]
RentReasonablenessRisk = Literal["LOW", "MED", "HIGH", "UNKNOWN"]
RentReasonablenessPolicy = Literal["FLAG_ONLY", "PENDING_IF_HIGH", "HARD_FAIL_IF_HIGH"]


class ProgramGateError(ValueError):
    pass


@dataclass(frozen=True)
class UtilityResponsibility:
    electric: Responsibility
    gas: Responsibility
    water: Responsibility
    sewer: Responsibility
    trash: Responsibility
    internet: Responsibility = "ignore"

    @staticmethod
    def from_mapping(data: Mapping[str, Any]) -> "UtilityResponsibility":
        def get(name: str, default: Responsibility) -> Responsibility:
            raw = data.get(name, default)
            if raw not in ("tenant", "owner", "ignore"):
                raise ProgramGateError(f"utilityResponsibility.{name} must be tenant|owner|ignore, got: {raw!r}")
            return raw  # type: ignore[return-value]

        return UtilityResponsibility(
            electric=get("electric", "owner"),
            gas=get("gas", "owner"),
            water=get("water", "owner"),
            sewer=get("sewer", "owner"),
            trash=get("trash", "owner"),
            internet=get("internet", "ignore"),
        )


@dataclass(frozen=True)
class ProgramGateInput:
    programType: ProgramType
    voucherBedroomSize: int
    zip: str
    rentToOwner: float

    # Actual listing/unit bedrooms (if known). This is NOT used for payment-standard math directly;
    # we instead use approvalBedroomCapSize (see below) to match the real-world "cap" rule.
    listingBedroomCount: Optional[int] = None

    # Bedroom-size used for payment standard / utility allowance lookup.
    # Real use case rule:
    # - studio listing -> 0
    # - any 1BR+ listing -> 1
    # If omitted, it will be derived from listingBedroomCount when available; otherwise a safe fallback is used.
    approvalBedroomCapSize: Optional[int] = None

    paymentStandardByZip: Optional[Mapping[str, Mapping[int, float]]] = None
    utilityResponsibility: Optional[UtilityResponsibility] = None
    utilityAllowanceSchedule: Optional[Mapping[str, Mapping[int, Mapping[str, float]]]] = None

    # If TTP is unknown, provide incomeAdjustedMonthly so we can at least compute burden if tenantShare exists.
    TTP: Optional[float] = None
    incomeAdjustedMonthly: Optional[float] = None

    # Policy / gating flags
    phaPolicyFlags: List[str] = field(default_factory=list)

    # Signals from caller/UI
    isInitialLeaseUp: bool = True
    offBookSidePayments: bool = False
    rentReasonablenessRisk: Optional[RentReasonablenessRisk] = None
    rentReasonablenessPolicy: RentReasonablenessPolicy = "FLAG_ONLY"


@dataclass
class ProgramGateOutput:
    programGateStatus: GateStatus

    grossRent: Optional[float]
    utilityAllowance: Optional[float]
    tenantShare: Optional[float]
    initialRentBurden: Optional[float]

    paymentStandardUsed: Optional[float]
    approvalBedroomCapSizeUsed: Optional[int]
    utilityAllowanceUsed: Optional[float]
    grossRentEstimate: Optional[float]
    tenantShareEstimate: Optional[float]
    initialRentBurdenEstimate: Optional[float]

    flags: Dict[str, Any]
    notes: List[str]
    actionsRequired: List[str]


# ----------------------------
# Utility Allowance Resolver
# ----------------------------

def _pattern_key_from_responsibility(resp: UtilityResponsibility) -> str:
    """Builds a stable key for utility allowance lookups.

    Schedule keys vary by PHA; this creates a predictable string the schedule can store.

    Format: "electric=tenant;gas=owner;water=tenant;sewer=owner;trash=tenant;internet=ignore"
    """

    parts = [
        f"electric={resp.electric}",
        f"gas={resp.gas}",
        f"water={resp.water}",
        f"sewer={resp.sewer}",
        f"trash={resp.trash}",
        f"internet={resp.internet}",
    ]
    return ";".join(parts)


def resolve_utility_allowance(
    *,
    zip: str,
    approvalBedroomCapSize: int,
    utilityResponsibility: UtilityResponsibility,
    utilityAllowanceSchedule: Mapping[str, Mapping[int, Mapping[str, float]]],
) -> Tuple[Optional[float], List[str]]:
    notes: List[str] = []

    zip_bucket = utilityAllowanceSchedule.get(zip)
    if not zip_bucket:
        notes.append(f"Utility allowance schedule missing for zip={zip!r}.")
        return None, notes

    bedroom_bucket = zip_bucket.get(approvalBedroomCapSize)
    if not bedroom_bucket:
        notes.append(
            f"Utility allowance schedule missing for bedroomCapSize={approvalBedroomCapSize} in zip={zip!r}."
        )
        return None, notes

    key = _pattern_key_from_responsibility(utilityResponsibility)
    if key in bedroom_bucket:
        ua = float(bedroom_bucket[key])
        notes.append(f"Utility allowance resolved via responsibility pattern: {key} -> {ua:.2f}.")
        return ua, notes

    # Fallback: allow schedule to omit internet dimension by matching a key with internet removed.
    key_no_internet = ";".join([p for p in key.split(";") if not p.startswith("internet=")])
    for candidate_key, candidate_value in bedroom_bucket.items():
        if candidate_key == key_no_internet:
            ua = float(candidate_value)
            notes.append(
                "Utility allowance resolved via fallback key without internet dimension: "
                f"{candidate_key} -> {ua:.2f}."
            )
            return ua, notes

    notes.append("Utility allowance not found for provided responsibility pattern.")
    notes.append(f"Expected key: {key}")
    notes.append(f"Bedroom bucket keys available: {sorted(bedroom_bucket.keys())}")
    return None, notes


# ----------------------------
# Voucher Math Engine
# ----------------------------

def _payment_standard_for(
    *,
    paymentStandardByZip: Mapping[str, Mapping[int, float]],
    zip: str,
    approvalBedroomCapSize: int,
) -> Optional[float]:
    zip_bucket = paymentStandardByZip.get(zip)
    if not zip_bucket:
        return None
    ps = zip_bucket.get(approvalBedroomCapSize)
    return float(ps) if ps is not None else None


def _derive_approval_bedroom_cap_size(data: ProgramGateInput) -> Tuple[Optional[int], List[str]]:
    notes: List[str] = []

    if data.approvalBedroomCapSize is not None:
        if data.approvalBedroomCapSize < 0:
            raise ProgramGateError("approvalBedroomCapSize must be >= 0")
        notes.append(f"Using provided approvalBedroomCapSize={data.approvalBedroomCapSize}.")
        return data.approvalBedroomCapSize, notes

    if data.listingBedroomCount is not None:
        if data.listingBedroomCount < 0:
            raise ProgramGateError("listingBedroomCount must be >= 0")
        cap = 0 if data.listingBedroomCount == 0 else 1
        notes.append(
            "Derived approvalBedroomCapSize from listingBedroomCount "
            f"(rule: studio->0, 1BR+->1): listingBedroomCount={data.listingBedroomCount} -> {cap}."
        )
        return cap, notes

    # Fallback: if we do not know listing bedrooms, derive a conservative cap from voucherBedroomSize.
    # This keeps the module usable even when upstream hasn't provided listing details yet.
    cap = 0 if data.voucherBedroomSize == 0 else 1
    notes.append(
        "Derived approvalBedroomCapSize from voucherBedroomSize due to missing listingBedroomCount "
        f"(fallback): voucherBedroomSize={data.voucherBedroomSize} -> {cap}."
    )
    return cap, notes


def compute_voucher_math(
    *,
    rentToOwner: float,
    utilityAllowance: float,
    paymentStandard: Optional[float],
    TTP: Optional[float],
) -> Tuple[Optional[float], Optional[float], List[str]]:
    """Returns (grossRent, tenantShare, notes).

    Uses a standard HCV approximation when PS and TTP are known:

    - grossRent = rentToOwner + utilityAllowance
    - HAP = max(0, min(paymentStandard, grossRent) - TTP)
    - tenantShare = grossRent - HAP

    If PS or TTP is missing, tenantShare is unknown (we still return grossRent).
    """

    notes: List[str] = []

    gross_rent = float(rentToOwner) + float(utilityAllowance)
    notes.append(f"grossRent = rentToOwner + utilityAllowance = {gross_rent:.2f}.")

    if paymentStandard is None:
        notes.append("paymentStandard is unknown; cannot compute HAP/tenantShare.")
        return gross_rent, None, notes

    if TTP is None:
        notes.append("TTP is unknown; cannot compute HAP/tenantShare.")
        return gross_rent, None, notes

    hap = max(0.0, min(float(paymentStandard), gross_rent) - float(TTP))
    tenant_share = gross_rent - hap

    notes.append(f"HAP = max(0, min(paymentStandard, grossRent) - TTP) = {hap:.2f}.")
    notes.append(f"tenantShare = grossRent - HAP = {tenant_share:.2f}.")

    return gross_rent, tenant_share, notes


# ----------------------------
# Hard Gate Evaluator
# ----------------------------

def evaluate_hard_gates(
    *,
    isInitialLeaseUp: bool,
    offBookSidePayments: bool,
    tenantShare: Optional[float],
    incomeAdjustedMonthly: Optional[float],
) -> Tuple[GateStatus, Optional[float], List[str]]:
    notes: List[str] = []

    if offBookSidePayments:
        notes.append("Hard FAIL: off-book side payments indicated (tenant pays landlord extra outside lease/HAP).")
        return "FAIL", None, notes

    if not isInitialLeaseUp:
        notes.append("Initial 40% lease-up cap not evaluated (isInitialLeaseUp=false).")
        return "PASS", None, notes

    if tenantShare is None:
        notes.append("Cannot evaluate 40% initial lease-up cap: tenantShare unknown.")
        return "UNKNOWN", None, notes

    if incomeAdjustedMonthly is None or incomeAdjustedMonthly <= 0:
        notes.append("Cannot evaluate 40% initial lease-up cap: adjusted monthly income unknown/invalid.")
        return "UNKNOWN", None, notes

    initial_burden = float(tenantShare) / float(incomeAdjustedMonthly)
    notes.append(f"initialRentBurden = tenantShare / adjustedMonthlyIncome = {initial_burden:.4f}.")

    if initial_burden > 0.40:
        notes.append("Hard FAIL: initial rent burden exceeds 40% at initial lease-up.")
        return "FAIL", initial_burden, notes

    return "PASS", initial_burden, notes


# ----------------------------
# Ask PHA Question Generator
# ----------------------------

def generate_ask_pha_actions(*, zip: str) -> List[str]:
    return [
        f"Ask PHA for payment standard by bedroom size (studio/1/2/3/4) for zip {zip}.",
        "Ask PHA for the utility allowance schedule and what counts as tenant-paid utilities.",
        "Ask PHA for your current TTP (Total Tenant Payment) or family share estimate.",
        "Ask PHA whether exception payment standard is possible and your eligibility.",
        "Ask PHA for target rent range to stay under the 40% initial lease-up cap.",
        "Ask HUD-VASH team / PHA for any HUD-VASH specific restrictions (e.g., no roommates).",
    ]


# ----------------------------
# Public API
# ----------------------------

def run_program_gate(data: ProgramGateInput) -> ProgramGateOutput:
    notes: List[str] = []
    actions: List[str] = []

    # Basic validation
    if data.voucherBedroomSize < 0:
        raise ProgramGateError("voucherBedroomSize must be >= 0")
    if data.listingBedroomCount is not None and data.listingBedroomCount < 0:
        raise ProgramGateError("listingBedroomCount must be >= 0")
    if data.rentToOwner < 0:
        raise ProgramGateError("rentToOwner must be >= 0")

    approval_bedroom_cap_size, cap_notes = _derive_approval_bedroom_cap_size(data)
    notes.extend(cap_notes)

    # Resolve payment standard
    payment_standard = None
    if data.paymentStandardByZip is not None:
        payment_standard = _payment_standard_for(
            paymentStandardByZip=data.paymentStandardByZip,
            zip=data.zip,
            approvalBedroomCapSize=approval_bedroom_cap_size,
        )
        if payment_standard is None:
            notes.append("Payment standard missing for provided zip/bedroom size.")

    # Resolve utility allowance
    utility_allowance = None
    ua_notes: List[str] = []

    if data.utilityResponsibility is None or data.utilityAllowanceSchedule is None:
        ua_notes.append("Utility responsibility or schedule missing; utility allowance cannot be resolved.")
    else:
        utility_allowance, ua_notes = resolve_utility_allowance(
            zip=data.zip,
            approvalBedroomCapSize=approval_bedroom_cap_size,
            utilityResponsibility=data.utilityResponsibility,
            utilityAllowanceSchedule=data.utilityAllowanceSchedule,
        )

    notes.extend(ua_notes)

    # If UA unknown, gross rent math is blocked.
    gross_rent = None
    tenant_share = None
    math_notes: List[str] = []

    if utility_allowance is None:
        math_notes.append("Utility allowance unknown; cannot compute gross rent or tenant share.")
    else:
        gross_rent, tenant_share, math_notes = compute_voucher_math(
            rentToOwner=data.rentToOwner,
            utilityAllowance=utility_allowance,
            paymentStandard=payment_standard,
            TTP=data.TTP,
        )

    notes.extend(math_notes)

    # Apply hard gates
    gate_status, initial_burden, gate_notes = evaluate_hard_gates(
        isInitialLeaseUp=data.isInitialLeaseUp,
        offBookSidePayments=data.offBookSidePayments,
        tenantShare=tenant_share,
        incomeAdjustedMonthly=data.incomeAdjustedMonthly,
    )
    notes.extend(gate_notes)

    # Rent reasonableness is flagged; caller can choose whether to treat as pending
    rr_risk: RentReasonablenessRisk = data.rentReasonablenessRisk or "UNKNOWN"
    rr_policy: RentReasonablenessPolicy = data.rentReasonablenessPolicy
    notes.append(f"Rent reasonableness risk flagged as {rr_risk} (policy={rr_policy}).")

    # UNKNOWN resolution and negotiation reality
    unknown_reasons: List[str] = []
    if payment_standard is None:
        unknown_reasons.append("paymentStandard")
    if data.TTP is None:
        unknown_reasons.append("TTP")
    if utility_allowance is None:
        unknown_reasons.append("utilityAllowance")

    if gate_status != "FAIL" and unknown_reasons:
        gate_status = "UNKNOWN"
        notes.append(f"programGateStatus=UNKNOWN due to missing: {', '.join(unknown_reasons)}.")
        actions.extend(generate_ask_pha_actions(zip=data.zip))

    # Rent reasonableness handling is policy-controlled.
    if gate_status == "PASS" and rr_risk == "HIGH":
        if rr_policy == "FLAG_ONLY":
            notes.append("Rent reasonableness HIGH is flagged only (no auto-escalation).")
        elif rr_policy == "PENDING_IF_HIGH":
            gate_status = "FAIL_PENDING_PHA"
            notes.append("Escalated to FAIL_PENDING_PHA due to HIGH rent reasonableness risk.")
        elif rr_policy == "HARD_FAIL_IF_HIGH":
            gate_status = "FAIL"
            notes.append("Hard FAIL due to HIGH rent reasonableness risk (policy=HARD_FAIL_IF_HIGH).")

    notes.append(
        "Negotiation is only valid inside PHA/HUD gates: cannot negotiate around payment standard math, "
        "rent reasonableness, HQS/HCV approvals, or the 40% initial cap."
    )

    flags: Dict[str, Any] = {
        "offBookSidePayments": bool(data.offBookSidePayments),
        "rentReasonablenessRisk": rr_risk,
    }

    return ProgramGateOutput(
        programGateStatus=gate_status,
        grossRent=gross_rent,
        utilityAllowance=utility_allowance,
        tenantShare=tenant_share,
        initialRentBurden=initial_burden,
        paymentStandardUsed=payment_standard,
        approvalBedroomCapSizeUsed=approval_bedroom_cap_size,
        utilityAllowanceUsed=utility_allowance,
        grossRentEstimate=gross_rent,
        tenantShareEstimate=tenant_share,
        initialRentBurdenEstimate=initial_burden,
        flags=flags,
        notes=notes,
        actionsRequired=actions,
    )


# ----------------------------
# Minimal example CLI
# ----------------------------


def _demo() -> None:
    payment_standards = {"81501": {0: 1050.0, 1: 1210.0, 2: 1535.0, 3: 1990.0, 4: 2200.0}}

    # Example schedule uses the module's pattern key format.
    ua_schedule = {
        "81501": {
            0: {
                "electric=tenant;gas=tenant;water=owner;sewer=owner;trash=tenant;internet=ignore": 118.0,
            },
            1: {
                "electric=tenant;gas=tenant;water=owner;sewer=owner;trash=tenant;internet=ignore": 142.0,
            }
        }
    }

    # Example 1: 2BR listing, but approval uses 1BR cap (your real-world rule).
    inp = ProgramGateInput(
        programType="HUD-VASH",
        voucherBedroomSize=1,
        listingBedroomCount=2,
        zip="81501",
        rentToOwner=1200.0,
        paymentStandardByZip=payment_standards,
        utilityResponsibility=UtilityResponsibility(
            electric="tenant",
            gas="tenant",
            water="owner",
            sewer="owner",
            trash="tenant",
            internet="ignore",
        ),
        utilityAllowanceSchedule=ua_schedule,
        TTP=420.0,
        incomeAdjustedMonthly=2400.0,
        phaPolicyFlags=["v1-demo"],
        isInitialLeaseUp=True,
        offBookSidePayments=False,
        rentReasonablenessRisk="MED",
    )

    out = run_program_gate(inp)
    print("--- Example 1 (2BR listing, 1BR cap) ---")
    print("programGateStatus:", out.programGateStatus)
    print("approvalBedroomCapSizeUsed:", out.approvalBedroomCapSizeUsed)
    print("grossRent:", out.grossRent)
    print("utilityAllowance:", out.utilityAllowance)
    print("tenantShare:", out.tenantShare)
    print("initialRentBurden:", out.initialRentBurden)
    print("actionsRequired:")
    for a in out.actionsRequired:
        print(" -", a)
    print("notes:")
    for n in out.notes[:12]:
        print(" -", n)

    # Example 2: Studio listing uses studio cap (0), not the 1BR cap.
    inp2 = ProgramGateInput(
        programType="HUD-VASH",
        voucherBedroomSize=1,
        listingBedroomCount=0,
        zip="81501",
        rentToOwner=980.0,
        paymentStandardByZip=payment_standards,
        utilityResponsibility=UtilityResponsibility(
            electric="tenant",
            gas="tenant",
            water="owner",
            sewer="owner",
            trash="tenant",
            internet="ignore",
        ),
        utilityAllowanceSchedule=ua_schedule,
        TTP=420.0,
        incomeAdjustedMonthly=2400.0,
        phaPolicyFlags=["v1-demo"],
        isInitialLeaseUp=True,
        offBookSidePayments=False,
        rentReasonablenessRisk="UNKNOWN",
    )

    out2 = run_program_gate(inp2)
    print("\n--- Example 2 (Studio listing, studio cap) ---")
    print("programGateStatus:", out2.programGateStatus)
    print("approvalBedroomCapSizeUsed:", out2.approvalBedroomCapSizeUsed)
    print("grossRent:", out2.grossRent)
    print("utilityAllowance:", out2.utilityAllowance)
    print("tenantShare:", out2.tenantShare)
    print("initialRentBurden:", out2.initialRentBurden)
    print("actionsRequired:")
    for a in out2.actionsRequired:
        print(" -", a)
    print("notes:")
    for n in out2.notes[:12]:
        print(" -", n)


if __name__ == "__main__":
    _demo()
