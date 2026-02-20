"""Landlord_Outreach_Packet_v1

Deterministic template pack generator for landlord outreach.

Inputs are summaries + gate outputs (ProgramGate, ListingLegitimacy, HQS).
Outputs are ready-to-send factual templates and checklists.

Version: v1
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Mapping, Optional


ProgramType = Literal["HUD-VASH", "HCV", "Section8", "Other"]
GateStatus = Literal["PASS", "FAIL", "UNKNOWN", "FAIL_PENDING_PHA"]
LegitimacyStatus = Literal["LEGIT_LIKELY", "SCAM_LIKELY", "UNKNOWN", "NEEDS_VERIFICATION"]
HQSStatus = Literal["PASS_LIKELY", "FAIL_LIKELY", "UNKNOWN", "PASS_WITH_FIXES"]
UtilityPaidBy = Literal["tenant", "owner", "unknown"]


class LandlordOutreachError(ValueError):
    pass


@dataclass(frozen=True)
class OutreachPacket:
    landlordCallScript: str
    smsTemplate: str
    emailTemplate: str
    docChecklist: List[str]
    fixList: List[str]
    timeline: List[str]
    phaQuestions: List[str]
    notes: List[str]


def _as_mapping(name: str, value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise LandlordOutreachError(f"{name} must be an object")
    return value


def _as_str(name: str, value: Any, *, allow_empty: bool = False) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise LandlordOutreachError(f"{name} must be a string")
    if not allow_empty and not value.strip():
        raise LandlordOutreachError(f"{name} must be non-empty")
    return value.strip()


def _as_num(name: str, value: Any) -> float:
    if not isinstance(value, (int, float)):
        raise LandlordOutreachError(f"{name} must be a number")
    if float(value) < 0:
        raise LandlordOutreachError(f"{name} must be >= 0")
    return float(value)


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for item in items:
        if item not in seen:
            out.append(item)
            seen.add(item)
    return out


def _format_money(value: Optional[float]) -> str:
    if value is None:
        return "(unknown)"
    return f"${value:,.0f}"


def _utility_summary(utilities_paid_by: Mapping[str, Any]) -> str:
    def get(key: str) -> UtilityPaidBy:
        raw = utilities_paid_by.get(key, "unknown")
        if raw not in ("tenant", "owner", "unknown"):
            return "unknown"
        return raw  # type: ignore[return-value]

    parts = [
        f"Electric: {get('electric')}",
        f"Gas: {get('gas')}",
        f"Water: {get('water')}",
        f"Sewer: {get('sewer')}",
        f"Trash: {get('trash')}",
    ]
    internet = get("internet")
    if internet != "unknown":
        parts.append(f"Internet: {internet}")
    return "; ".join(parts)


def _doc_checklist(*, program_type: ProgramType) -> List[str]:
    # Keep generic and widely applicable; PHAs vary.
    base = [
        "W-9 (landlord/owner)",
        "Direct deposit / ACH form (or voided check)",
        "Proof of ownership or authority to lease (deed/tax record/management agreement)",
        "Proposed lease (or agree to PHA lease template)",
        "PHA Tenancy Addendum (HUD-required for HCV/HUD-VASH)",
        "Request for Tenancy Approval (RFTA) packet (PHA form)",
        "Lead-Based Paint disclosure (if pre-1978)",
        "Utilities responsibilities (who pays which utilities)",
        "Unit details needed for inspection scheduling (access instructions, lockbox, contacts)",
    ]

    if program_type == "HUD-VASH":
        base.append("Landlord W-9/ACH must match payee on HAP contract (PHA requirement)")

    return _dedupe_preserve_order(base)


def _timeline(*, program_type: ProgramType, hqs_status: HQSStatus, fix_list: List[str]) -> List[str]:
    pha_label = "PHA" if program_type != "HUD-VASH" else "PHA / HUD-VASH"

    items: List[str] = []
    items.append("1) Confirm unit basics (rent, utilities, availability) and schedule a showing or live walkthrough.")
    items.append(f"2) Submit RFTA to {pha_label} (starts rent reasonableness + paperwork flow).")
    items.append("3) Rent reasonableness review (PHA compares to similar units).")

    if hqs_status == "PASS_WITH_FIXES" and fix_list:
        items.append("4) Complete the fix list before inspection (avoids failed inspection and re-inspection delays).")
        items.append("5) HQS inspection scheduled once access is confirmed; re-inspection if needed.")
        items.append("6) Lease signing + HAP contract execution after pass.")
    else:
        items.append("4) HQS inspection scheduled once access is confirmed; re-inspection if needed.")
        items.append("5) Lease signing + HAP contract execution after pass.")

    items.append("7) Move-in / keys after paperwork is executed and tenant share is confirmed.")

    return items


def _pha_questions(program_gate: Mapping[str, Any]) -> List[str]:
    # Only include when the program gate indicates missing/unknowns and provides actions.
    status = program_gate.get("programGateStatus")
    actions = program_gate.get("actionsRequired", [])
    if status in ("UNKNOWN", "FAIL_PENDING_PHA") and isinstance(actions, list):
        return [str(x) for x in actions if str(x).strip()]
    return []


def _call_script(
    *,
    contact_name: str,
    contact_role: str,
    program_type: ProgramType,
    pha_name: str,
    unit_address: str,
    rent_to_owner: float,
    utility_summary: str,
    fix_list: List[str],
) -> str:
    greeter = f"Hi {contact_name}," if contact_name else "Hi,"
    who = "I'm calling about" if contact_role in ("owner", "property_manager", "agent") else "I'm calling regarding"

    pha_part = f" through {pha_name}" if pha_name else " through the local housing authority"

    fixes_line = ""
    if fix_list:
        fixes_line = (
            "We also have a short pre-inspection fix list we can share up front "
            "to help avoid inspection delays. "
        )

    return (
        f"{greeter} {who} the unit at {unit_address}. "
        f"I work with a tenant using a {program_type} housing voucher{pha_part}. "
        f"The rent advertised is {_format_money(rent_to_owner)} to owner. Utilities: {utility_summary}. "
        "If you're open to vouchers, the next step is just paperwork + an HQS inspection. "
        "I can text/email you a simple checklist (W-9, ACH, RFTA, lease/addendum) and coordinate scheduling. "
        f"{fixes_line}"
        "What's the best email/phone to send the packet, and when can we view the unit?"
    )


def _sms_template(
    *,
    contact_name: str,
    program_type: ProgramType,
    unit_address: str,
    rent_to_owner: float,
    pha_name: str,
) -> str:
    name = f" {contact_name}" if contact_name else ""
    pha_part = f" via {pha_name}" if pha_name else " via the local housing authority"
    return (
        f"Hi{name} — I'm interested in {unit_address}. I'm working with a tenant using a {program_type} voucher{pha_part}. "
        f"Rent to owner: {_format_money(rent_to_owner)}. If you accept vouchers, I can send the landlord packet (W-9/ACH, RFTA, lease/addendum) and schedule a tour."
    )


def _email_template(
    *,
    contact_name: str,
    program_type: ProgramType,
    unit_address: str,
    rent_to_owner: float,
    utility_summary: str,
    pha_name: str,
    fix_list: List[str],
    doc_checklist: List[str],
    timeline: List[str],
    pha_questions: List[str],
) -> str:
    greeting = f"Hi {contact_name}," if contact_name else "Hello,"
    pha_part = f" through {pha_name}" if pha_name else " through the local housing authority"

    lines: List[str] = []
    lines.append(greeting)
    lines.append("")
    lines.append(
        f"I'm reaching out about the unit at {unit_address}. I'm working with a tenant using a {program_type} housing voucher{pha_part}."
    )
    lines.append("")
    lines.append("Unit summary")
    lines.append(f"- Rent to owner: {_format_money(rent_to_owner)}")
    lines.append(f"- Utilities: {utility_summary}")
    lines.append("")
    lines.append("Landlord packet checklist")
    for item in doc_checklist:
        lines.append(f"- {item}")

    if fix_list:
        lines.append("")
        lines.append("Pre-inspection fix list (optional but recommended)")
        for item in fix_list:
            lines.append(f"- {item}")

    lines.append("")
    lines.append("Typical timeline")
    for item in timeline:
        lines.append(f"- {item}")

    if pha_questions:
        lines.append("")
        lines.append("Open items (PHA questions we’re confirming)")
        for q in pha_questions:
            lines.append(f"- {q}")

    lines.append("")
    lines.append("If you're open to vouchers, what's the best time to view the unit and the best email/phone to send the packet?")
    lines.append("")
    lines.append("Thank you,")
    lines.append("(Your name)")

    return "\n".join(lines)


def build_landlord_outreach_packet(payload: Mapping[str, Any]) -> OutreachPacket:
    unit = _as_mapping("unit", payload.get("unit"))
    program = _as_mapping("program", payload.get("program"))
    program_gate = _as_mapping("programGate", payload.get("programGate"))
    legitimacy = _as_mapping("legitimacy", payload.get("legitimacy"))
    hqs = _as_mapping("hqs", payload.get("hqs"))

    unit_address = _as_str("unit.address", unit.get("address"))
    rent_to_owner = _as_num("unit.rentToOwner", unit.get("rentToOwner"))

    utilities_paid_by = _as_mapping("unit.utilitiesPaidBy", unit.get("utilitiesPaidBy"))
    utility_summary = _utility_summary(utilities_paid_by)

    contact = _as_mapping("unit.contact", unit.get("contact"))
    contact_name = _as_str("unit.contact.name", contact.get("name"), allow_empty=True)
    contact_role = _as_str("unit.contact.role", contact.get("role"), allow_empty=True) or "unknown"

    program_type_raw = _as_str("program.programType", program.get("programType"))
    if program_type_raw not in ("HUD-VASH", "HCV", "Section8", "Other"):
        raise LandlordOutreachError(f"program.programType invalid: {program_type_raw!r}")
    program_type: ProgramType = program_type_raw  # type: ignore[assignment]

    pha_name = _as_str("program.phaName", program.get("phaName"), allow_empty=True)

    # Fix list only when PASS_WITH_FIXES
    hqs_status = _as_str("hqs.hqsStatus", hqs.get("hqsStatus"))
    if hqs_status not in ("PASS_LIKELY", "FAIL_LIKELY", "UNKNOWN", "PASS_WITH_FIXES"):
        raise LandlordOutreachError(f"hqs.hqsStatus invalid: {hqs_status!r}")
    hqs_status_t: HQSStatus = hqs_status  # type: ignore[assignment]

    fixable_items_raw = hqs.get("fixableItems", [])
    fixable_items = [str(x) for x in fixable_items_raw] if isinstance(fixable_items_raw, list) else []
    fix_list = _dedupe_preserve_order([x for x in fixable_items if x.strip()]) if hqs_status_t == "PASS_WITH_FIXES" else []

    doc_checklist = _doc_checklist(program_type=program_type)
    pha_questions = _pha_questions(program_gate)
    timeline = _timeline(program_type=program_type, hqs_status=hqs_status_t, fix_list=fix_list)

    # Notes remain internal-facing (for UI decisions); no persuasion content.
    notes: List[str] = []

    gate_status = program_gate.get("programGateStatus")
    if isinstance(gate_status, str):
        notes.append(f"programGateStatus={gate_status}")

    legitimacy_status = legitimacy.get("legitimacyStatus")
    if isinstance(legitimacy_status, str):
        notes.append(f"legitimacyStatus={legitimacy_status}")

    # If legitimacy indicates verification needed, keep it as an internal note only.
    if legitimacy_status in ("SCAM_LIKELY", "NEEDS_VERIFICATION"):
        notes.append("Legitimacy output indicates verification is required before sharing sensitive information.")

    landlord_call_script = _call_script(
        contact_name=contact_name,
        contact_role=contact_role,
        program_type=program_type,
        pha_name=pha_name,
        unit_address=unit_address,
        rent_to_owner=rent_to_owner,
        utility_summary=utility_summary,
        fix_list=fix_list,
    )

    sms_template = _sms_template(
        contact_name=contact_name,
        program_type=program_type,
        unit_address=unit_address,
        rent_to_owner=rent_to_owner,
        pha_name=pha_name,
    )

    email_template = _email_template(
        contact_name=contact_name,
        program_type=program_type,
        unit_address=unit_address,
        rent_to_owner=rent_to_owner,
        utility_summary=utility_summary,
        pha_name=pha_name,
        fix_list=fix_list,
        doc_checklist=doc_checklist,
        timeline=timeline,
        pha_questions=pha_questions,
    )

    return OutreachPacket(
        landlordCallScript=landlord_call_script,
        smsTemplate=sms_template,
        emailTemplate=email_template,
        docChecklist=doc_checklist,
        fixList=fix_list,
        timeline=timeline,
        phaQuestions=pha_questions,
        notes=_dedupe_preserve_order(notes),
    )


def _demo() -> None:
    with open("example_input.json", "r", encoding="utf-8-sig") as f:
        payload = json.load(f)

    packet = build_landlord_outreach_packet(payload)
    print(json.dumps(packet.__dict__, indent=2))


if __name__ == "__main__":
    _demo()
