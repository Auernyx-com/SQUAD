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


# Apostrophe/quote variants that iOS, Android, and most word processors
# auto-substitute for a plain "'" by default (smart/curly quotes, and a
# couple of look-alikes people paste from other apps). Without normalizing
# these, "I'm going to kill myself" (straight apostrophe, matched) and
# "I’m going to kill myself" (curly apostrophe — what a phone keyboard
# actually produces when someone types a straight one) were NOT equivalent:
# the phrase list only had straight-apostrophe and no-apostrophe variants of
# each phrase, so a genuine self-harm statement typed completely normally on
# a phone silently fell through to status="OK". Confirmed with a direct
# probe against the pre-fix code before this change.
_APOSTROPHE_VARIANTS = ["’", "‘", "`", "´"]


def _normalize_apostrophes(text: str) -> str:
    for variant in _APOSTROPHE_VARIANTS:
        text = text.replace(variant, "'")
    return text


def _contains_any(haystack: str, needles: List[str]) -> bool:
    h = _normalize_apostrophes(haystack.lower())
    return any(_normalize_apostrophes(n) in h for n in needles)


def _detect_crisis(text: str, signals: Dict[str, bool]) -> Optional[str]:
    # Conservative trigger: only fire CRISIS for clear self-harm / suicide
    # intent or immediate danger. Otherwise, ask questions.

    if signals.get("immediate_danger") or signals.get("in_immediate_danger"):
        return "Signal indicates immediate danger."

    if signals.get("self_harm_intent") or signals.get("suicidal_intent"):
        return "Signal indicates self-harm intent."

    if not text:
        return None

    # Independent-audit finding (2026-09-06), same gap found and fixed in
    # pathfinder-worker's identical JS port of this list: the original list
    # only matched "kill myself"/"die" preceded by a handful of exact
    # prefixes, and had no entries at all for extremely common real-world
    # ideation phrasing ("don't want to live anymore", "no point in going
    # on", "overdose", "took a bunch of pills", etc). Verified directly:
    # every phrase below returned None against the pre-fix list. Broadened
    # to the substrings that matter, deliberately still NOT chasing generic
    # phrases like "can't do this anymore" -- those false-positive
    # constantly on ordinary frustration with paperwork/appeals in this
    # specific domain, and crisis detection here has a real false-positive
    # cost too (a banner people learn to tune out), not just a
    # false-negative one. Keep both surfaces (this file and
    # pathfinder-worker's worker.js) in sync when either list changes.
    if _contains_any(
        text,
        [
            "i want to kill myself",
            "i'm going to kill myself",
            "im going to kill myself",
            "i will kill myself",
            "kill myself",
            "killing myself",
            "i want to die",
            "i'm going to die",
            "im going to die",
            "wish i was dead",
            "wish i were dead",
            "suicide",
            "suicidal",
            "end my life",
            "ending my life",
            "end it all",
            "hurt myself",
            "self harm",
            "self-harm",
            "better off dead",
            "better off without me",
            "better without me",
            "no point in living",
            "no point living",
            "no reason to live",
            "no reason to keep living",
            "no point in going on",
            "no point going on",
            "don't want to live anymore",
            "dont want to live anymore",
            "don't want to be here anymore",
            "dont want to be here anymore",
            "disappear for good",
            "overdose",
            "took a bunch of pills",
            "took all my pills",
            "jump off a bridge",
            "jump off the bridge",
            "jump off a building",
            "jump off the building",
            "jump in front of a train",
            "jump in front of the train",
            # Round 2 (2026-09-06), same gap independently found and fixed
            # in pathfinder-worker's identical JS port: these name a
            # suicide method directly and are unambiguous on their own --
            # they don't need the weapon+violence-word AND-gate below the
            # way a bare "shoot"/"stab" does, since "shoot myself"/"hang
            # myself" have no other plausible reading. Verified directly:
            # these fell through both branches before this addition (no
            # literal weapon noun present, so the weapon AND-gate never
            # fired for "shoot myself"/"hang myself").
            "shoot myself",
            "hang myself",
            "hanging myself",
            "cutting myself",
            "not worth living",
            "don't want to wake up",
            "dont want to wake up",
            "overdosing",
        ],
    ):
        return "Text indicates potential self-harm or suicide intent."

    # Broadened from exact "i have a gun"-style phrases to bare weapon
    # nouns -- the combined check below still requires an explicit
    # violence-target word in the same text, so "I have a gun safe I need
    # to register" (no violence word) still correctly does not trigger.
    if _contains_any(
        text,
        ["i have a gun", "i have a weapon", "i'm going to hurt", "im going to hurt", "gun", "weapon", "rifle", "pistol", "firearm"],
    ):
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
