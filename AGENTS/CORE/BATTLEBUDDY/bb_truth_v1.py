from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple


Confidence = str


@dataclass(frozen=True)
class TruthAssessment:
    confidence: Confidence
    unknowns: List[str]
    caveats: List[str]


def assess_truth(input_envelope: Dict[str, Any]) -> TruthAssessment:
    """Applies 'cite or caveat' discipline and returns confidence guidance.

    This function intentionally does not fetch external policy. It only uses fields
    present in the envelope (case facts, unknowns, artifacts, flags, module results).
    """

    case = (input_envelope or {}).get("case", {})
    unknowns = list(case.get("unknowns") or [])

    flags = (input_envelope or {}).get("flags") or {}
    fraud = bool(flags.get("fraud_or_phishing_risk"))
    deadline = bool(flags.get("deadline_risk"))
    crisis = bool(flags.get("medical_or_crisis_support_needed"))

    caveats: List[str] = []
    if unknowns:
        caveats.append("Key facts are missing; treat recommendations as verification steps.")
    if fraud:
        caveats.append("Fraud risk flagged; avoid sending money or sensitive info until verified.")
    if deadline:
        caveats.append("Deadline risk flagged; confirm dates from the notice/artifact.")
    if crisis:
        caveats.append("Crisis support may be needed; prioritize immediate safety.")

    if crisis:
        confidence: Confidence = "VERIFY_REQUIRED"
    elif unknowns or fraud or deadline:
        confidence = "VERIFY_REQUIRED"
    else:
        confidence = "MEDIUM"

    return TruthAssessment(confidence=confidence, unknowns=unknowns, caveats=caveats)


def summarize_known_vs_unknown(case: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    known = list((case or {}).get("known_facts") or [])
    unknown = list((case or {}).get("unknowns") or [])
    return known, unknown
