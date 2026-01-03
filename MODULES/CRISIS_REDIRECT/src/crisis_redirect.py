from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CrisisResult:
    status: str  # OK | CRISIS
    reason: str
    resources: List[Dict[str, str]]
    questions: List[str]
    audit: Dict[str, Any]


def _as_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _get_text(payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    raw = payload.get("text")
    return _as_str(raw).strip()


def _get_signals(payload: Dict[str, Any]) -> Dict[str, bool]:
    # Signals are optional, but allow upstream modules to pass explicit flags.
    # Keep schema permissive; treat unknown keys as false.
    if not isinstance(payload, dict):
        return {}
    signals = payload.get("signals")
    if not isinstance(signals, dict):
        return {}

    out: Dict[str, bool] = {}
    for k, v in signals.items():
        if isinstance(k, str):
            out[k] = bool(v)
    return out


def _contains_any(haystack: str, needles: List[str]) -> bool:
    h = haystack.lower()
    return any(n in h for n in needles)


def _detect_crisis(text: str, signals: Dict[str, bool]) -> Optional[str]:
    # Conservative trigger: only fire CRISIS for clear self-harm / suicide
    # intent or immediate danger. Otherwise, ask questions.

    if signals.get("immediate_danger") or signals.get("in_immediate_danger"):
        return "Signal indicates immediate danger."

    if signals.get("self_harm_intent") or signals.get("suicidal_intent"):
        return "Signal indicates self-harm intent."

    if not text:
        return None

    # High-signal phrases. Keep small and conservative.
    if _contains_any(
        text,
        [
            "i want to kill myself",
            "i'm going to kill myself",
            "im going to kill myself",
            "i will kill myself",
            "i want to die",
            "i'm going to die",
            "im going to die",
            "suicide",
            "end my life",
            "hurt myself",
            "self harm",
        ],
    ):
        return "Text indicates potential self-harm or suicide intent."

    if _contains_any(text, ["i have a gun", "i have a weapon", "i'm going to hurt", "im going to hurt"]):
        # Still conservative: only trigger if combined with self-harm/violence language.
        if _contains_any(text, ["myself", "them", "someone", "anyone", "kill", "shoot", "stab"]):
            return "Text indicates potential immediate violence risk."

    return None


def crisis_redirect(payload: Dict[str, Any]) -> CrisisResult:
    text = _get_text(payload)
    signals = _get_signals(payload)

    reason = _detect_crisis(text=text, signals=signals)

    resources: List[Dict[str, str]] = []
    questions: List[str] = []

    if reason is not None:
        # Provide widely applicable crisis resources; avoid jurisdiction assumptions beyond being explicit.
        resources = [
            {
                "label": "Emergency services",
                "detail": "If you’re in immediate danger, call your local emergency number now.",
            },
            {
                "label": "U.S. Suicide & Crisis Lifeline",
                "detail": "If you’re in the U.S., call or text 988 (or chat at 988lifeline.org).",
            },
        ]
        questions = [
            "Are you in immediate danger right now?",
            "Are you alone, or is someone with you who can help you get to safety?",
            "What country are you in (so we can give the right crisis contact)?",
        ]

        return CrisisResult(
            status="CRISIS",
            reason=reason,
            resources=resources,
            questions=questions,
            audit={
                "triggered": True,
                "signals": signals,
                "text_present": bool(text),
            },
        )

    # Not enough to trigger; ask minimal clarifying questions if there's any hint.
    if text and _contains_any(text, ["scared", "unsafe", "panic", "can't go on", "cant go on", "overwhelmed"]):
        questions = [
            "Are you safe right now?",
            "Is anyone threatening you or forcing you to do something?",
            "Do you have a safe place to stay tonight?",
        ]

    return CrisisResult(
        status="OK",
        reason="No clear crisis trigger detected.",
        resources=[],
        questions=questions,
        audit={
            "triggered": False,
            "signals": signals,
            "text_present": bool(text),
        },
    )


def crisis_redirect_to_dict(payload: Dict[str, Any]) -> Dict[str, Any]:
    r = crisis_redirect(payload)
    return {
        "status": r.status,
        "reason": r.reason,
        "resources": r.resources,
        "questions": r.questions,
        "audit": r.audit,
    }
