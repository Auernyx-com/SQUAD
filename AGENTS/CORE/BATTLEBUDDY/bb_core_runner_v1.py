from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from bb_truth_v1 import TruthAssessment, assess_truth


STAGES = {
    "STABILIZE",
    "CLARIFY",
    "LOCK_FACTS",
    "PICK_LANE",
    "PREP_OUTREACH",
    "TRACK_FOLLOW_UP",
}


@dataclass(frozen=True)
class BattleBuddyDraft:
    situation: str
    goal: str
    next_3_actions: List[str]
    evidence_needed: List[str]
    risks_traps: List[str]
    if_blocked_do_this: List[str]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_get(d: Dict[str, Any], path: List[str], default: Any = None) -> Any:
    cur: Any = d
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def _stage(input_env: Dict[str, Any]) -> str:
    stage = (input_env or {}).get("stage") or "CLARIFY"
    if stage not in STAGES:
        return "CLARIFY"
    return stage


def _extract_deadlines(case: Dict[str, Any]) -> List[Dict[str, Any]]:
    deadlines = case.get("deadlines") or []
    if not isinstance(deadlines, list):
        return []
    out: List[Dict[str, Any]] = []
    for d in deadlines:
        if isinstance(d, dict) and d.get("label") and d.get("date"):
            out.append(d)
    return out


def _privacy_warning_lines(flags: Dict[str, Any]) -> List[str]:
    if not flags:
        return []
    if not bool(flags.get("privacy_risk")):
        return []
    return [
        "Privacy: don’t share SSN, bank details, passwords/MFA codes, or full unredacted DD-214 in messages.",
        "Use redactions (last-4 only) when sharing documents or screenshots.",
    ]


def _fraud_warning_lines(flags: Dict[str, Any]) -> List[str]:
    if not flags:
        return []
    if not bool(flags.get("fraud_or_phishing_risk")):
        return []
    return [
        "Fraud risk: don’t send money (wire, gift cards, crypto) or sensitive info until you verify identity and ownership.",
        "If someone is pressuring you to pay to apply/view, treat it as a red flag and verify via independent channels.",
    ]


def _crisis_redirect_lines(flags: Dict[str, Any]) -> List[str]:
    if not flags:
        return []
    if not bool(flags.get("medical_or_crisis_support_needed")) and not bool(flags.get("immediate_safety_risk")):
        return []
    return [
        "If you’re in immediate danger, call your local emergency number now.",
        "If you’re in the U.S., you can call/text 988 for the Suicide & Crisis Lifeline.",
        "This part needs a human; prioritize safety over paperwork.",
    ]


def _goal_from_domain(domain: str, stage: str) -> str:
    if stage == "STABILIZE":
        return "Stabilize the immediate situation and protect deadlines."

    if domain == "HOUSING":
        return "Get to a safe, realistic housing plan with verified facts."
    if domain == "BENEFITS":
        return "Clarify the benefits path and collect proof before taking steps."
    if domain == "LEGAL":
        return "Protect your rights and avoid missing deadlines; verify before acting."

    return "Turn the situation into next steps and proof requirements."


def _situation_lines(case: Dict[str, Any], flags: Dict[str, Any], deadlines: List[Dict[str, Any]]) -> str:
    parts: List[str] = []

    narrative = (case.get("narrative") or "").strip()
    if narrative:
        trimmed = narrative.replace("\n", " ").strip()
        parts.append(trimmed[:280] + ("…" if len(trimmed) > 280 else ""))

    if deadlines:
        soon = sorted(deadlines, key=lambda d: str(d.get("date")))[:2]
        dl = ", ".join([f"{d.get('label')} ({d.get('date')})" for d in soon])
        parts.append(f"Deadlines noted: {dl}.")

    if flags and any(bool(flags.get(k)) for k in ["housing_instability", "deadline_risk", "fraud_or_phishing_risk"]):
        high = []
        if bool(flags.get("housing_instability")):
            high.append("housing risk")
        if bool(flags.get("deadline_risk")):
            high.append("deadline risk")
        if bool(flags.get("fraud_or_phishing_risk")):
            high.append("fraud risk")
        parts.append("Risk flags: " + ", ".join(high) + ".")

    if not parts:
        parts.append("No narrative provided yet; starting with clarification and proof gathering.")

    return "\n".join(parts[:3])


def _default_actions(stage: str, case: Dict[str, Any], deadlines: List[Dict[str, Any]]) -> List[str]:
    unknowns = list(case.get("unknowns") or [])

    if stage == "STABILIZE":
        actions = [
            "Confirm what happens in the next 24–72 hours (shelter tonight, shutoff, lockout, court date).",
            "Find and write down the single most urgent deadline from any notice/email (date + what you must do).",
            "If you have an advocate/rep, contact them with a short summary and ask what they need to act.",
        ]
        return actions[:3]

    if stage in {"CLARIFY", "LOCK_FACTS"}:
        actions: List[str] = []
        if unknowns:
            actions.append("Answer the top 3 unknowns that block the next step (who/where/program/timeline).")
        else:
            actions.append("List the key facts we can verify from documents (dates, amounts, names, addresses).")

        if deadlines:
            actions.append("Open the notice(s) and confirm each deadline date and required action; record the exact wording.")
        else:
            actions.append("Check for any written deadlines (notice, email, portal message) and record dates.")

        actions.append("Collect the minimum proof set (see Evidence needed) and redact sensitive identifiers.")
        return actions[:3]

    if stage == "PICK_LANE":
        return [
            "Choose one priority lane for the next 7 days (stabilize, verification, outreach, or escalation).",
            "Pick 1–3 actions you can complete this week and assign owners (you vs advocate).",
            "Decide what you will NOT do yet (to avoid thrash) until facts are verified.",
        ]

    if stage == "PREP_OUTREACH":
        return [
            "Draft a short, factual outreach message (what you want + the minimum facts).",
            "Prepare your evidence attachments (redacted) and a 3-question list for the agency/landlord.",
            "Send or schedule outreach and set a follow-up checkpoint within 48–72 hours.",
        ]

    # TRACK_FOLLOW_UP
    return [
        "Record what happened (who said what, when) and save any replies as artifacts.",
        "If no response, do one follow-up and then switch to the next option (avoid waiting in limbo).",
        "Update the case with new facts and re-run the relevant module(s) if the situation changed.",
    ]


def _default_evidence(case: Dict[str, Any], artifacts: List[Dict[str, Any]]) -> List[str]:
    evidence: List[str] = []

    have_types = {str(a.get("type")) for a in artifacts if isinstance(a, dict) and a.get("type")}

    if "NOTICE_TO_VACATE" not in have_types:
        evidence.append("Any written notice(s) (eviction/termination/shutoff): photo/PDF with dates visible (redact identifiers).")

    if "LEASE" not in have_types:
        evidence.append("Lease or rental agreement (if applicable), redacted.")

    if "EMAIL_THREAD" not in have_types:
        evidence.append("Relevant email/text thread screenshots showing dates/requests (redact phone numbers if needed).")

    if (case.get("program") or {}).get("name"):
        evidence.append("Program documentation you have (letters, portal screenshots) that state the program name and status.")
    else:
        evidence.append("Any letter/screenshot that confirms the program involved (if any), or who you’re working with.")

    evidence.append("A one-page timeline: key dates, who you contacted, outcomes.")

    return evidence


def _default_risks(stage: str, flags: Dict[str, Any], deadlines: List[Dict[str, Any]], truth: TruthAssessment) -> List[str]:
    risks: List[str] = []

    if deadlines:
        risks.append("Missing a deadline can remove options; confirm dates from the source document.")

    if truth.unknowns:
        risks.append("Key unknowns can cause wasted effort; verify before making irreversible moves.")

    risks.extend(_fraud_warning_lines(flags))
    risks.extend(_privacy_warning_lines(flags))

    if stage == "PREP_OUTREACH":
        risks.append("Avoid implying guarantees; keep outreach factual and process-focused.")

    return risks


def _default_if_blocked(flags: Dict[str, Any], deadlines: List[Dict[str, Any]]) -> List[str]:
    blocked: List[str] = []

    if deadlines:
        blocked.append("If you can’t confirm a deadline, ask a human advocate/rep to review the notice and restate the deadline in plain language.")

    blocked.extend(_crisis_redirect_lines(flags))

    if not blocked:
        blocked.append("If you get stuck, collect the missing document or ask the responsible agency for the exact requirement in writing.")

    return blocked


def build_battle_buddy_plan(input_env: Dict[str, Any]) -> Tuple[BattleBuddyDraft, TruthAssessment]:
    case = (input_env or {}).get("case") or {}
    flags = (input_env or {}).get("flags") or {}
    artifacts = (input_env or {}).get("artifacts") or []

    deadlines = _extract_deadlines(case)

    stage = _stage(input_env)
    domain = (case.get("domain") or "UNKNOWN").upper()

    truth = assess_truth(input_env)

    situation = _situation_lines(case=case, flags=flags, deadlines=deadlines)
    goal = _goal_from_domain(domain=domain, stage=stage)
    next_3_actions = _default_actions(stage=stage, case=case, deadlines=deadlines)
    evidence_needed = _default_evidence(case=case, artifacts=artifacts)
    risks_traps = _default_risks(stage=stage, flags=flags, deadlines=deadlines, truth=truth)
    if_blocked_do_this = _default_if_blocked(flags=flags, deadlines=deadlines)

    return (
        BattleBuddyDraft(
            situation=situation,
            goal=goal,
            next_3_actions=next_3_actions,
            evidence_needed=evidence_needed,
            risks_traps=risks_traps,
            if_blocked_do_this=if_blocked_do_this,
        ),
        truth,
    )


def _build_output_envelope(stage: str, plan: BattleBuddyDraft, truth: TruthAssessment) -> Dict[str, Any]:
    return {
        "stage": stage,
        "confidence": truth.confidence,
        "updates": truth.caveats,
        "tasks": [],
        "evidence": [],
        "scripts": [],
        "warnings": [],
        "handoffs": [],
        "battle_buddy_plan": {
            "situation": plan.situation,
            "goal": plan.goal,
            "next_3_actions": plan.next_3_actions,
            "evidence_needed": plan.evidence_needed,
            "risks_traps": plan.risks_traps,
            "if_blocked_do_this": plan.if_blocked_do_this,
        },
    }


def run(input_path: Path, output_path: Optional[Path] = None) -> Dict[str, Any]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))

    contract_id = payload.get("contract_id")
    schema_version = payload.get("schema_version")
    if contract_id != "AUERNYX.BattleBuddy.Contract.v1" or schema_version != 1:
        raise ValueError("Input is not AUERNYX.BattleBuddy.Contract.v1")

    input_env = payload.get("input") or {}
    stage = _stage(input_env)

    plan, truth = build_battle_buddy_plan(input_env)

    out = {
        "contract_id": "AUERNYX.BattleBuddy.Contract.v1",
        "schema_version": 1,
        "timestamp": _now_iso(),
        "input": input_env,
        "output": _build_output_envelope(stage=stage, plan=plan, truth=truth),
    }

    if output_path is not None:
        output_path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Auernyx BattleBuddy BB-Core minimal runner (v1).")
    parser.add_argument("input", help="Path to Contract v1 JSON (input envelope)")
    parser.add_argument("--out", help="Write output Contract v1 JSON to this path")

    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.out).expanduser().resolve() if args.out else None

    run(input_path=input_path, output_path=output_path)


if __name__ == "__main__":
    main()
