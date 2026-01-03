"""BattleBuddyHandshake module (v1).

Purpose:
- Strict handshake / intake-shaping helper.
- Emits observations + questions only.
- No advice, no eligibility determinations, no medical interpretation, no rating predictions.

Design constraints:
- Stdlib-only (no sklearn).
- Conservative refusals based on intent patterns (not mere condition keywords).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


@dataclass(frozen=True)
class BBOutput:
    observations: str
    questions: list[str]
    reflective_enabled: bool
    reflective_questions: list[str]
    stylistic_divergence: float
    flags: list[str]
    refused: bool
    refusal_reason: Optional[str]


class RefusalReason(str, Enum):
    """Standard refusal reasons for stable downstream handling."""

    OUT_OF_SCOPE = "OUT_OF_SCOPE"  # clinical/eligibility/rating/medical interpretation intent
    EMPTY_INPUT = "EMPTY_INPUT"


class BattleBuddyHandshake:
    """BattleBuddy-safe "handshake" response generator.

    Strict mode:
    - NO ADVICE
    - NO CLINICAL INTERPRETATION
    - NO ELIGIBILITY
    - NO RATING PREDICTIONS

    Output is observational + questions only.
    """

    def __init__(self) -> None:
        self.qualifiers = {"very", "really", "somewhat", "extremely", "kinda", "sorta"}
        self.temporal = {"now", "then", "when", "before", "after", "during", "today", "yesterday", "tomorrow"}

        # "Hot" / defensive language: do not add reflective channel when present.
        self.defense_markers = [
            "don't analyze",
            "dont analyze",
            "stop analyzing",
            "stop watching",
            "they're watching",
            "being watched",
            "gaslight",
            "gaslighting",
            "psyop",
            "bait",
            "trap",
            "cult",
            "not safe",
            "threat",
            "hacked",
            "breach",
        ]

        # Condition words may appear in admin-only contexts; do NOT auto-refuse on these alone.
        self.condition_words = {"ptsd", "depression", "anxiety", "adhd", "bipolar"}

        # Intent patterns that *are* out of scope (clinical/interpretation/prediction).
        # Note: avoid overly-broad clinical keyword triggers (e.g., "symptoms" alone).
        self.oos_intent_patterns = [
            r"\bdiagnos(e|is|ing)\b",
            r"\bwhat do i have\b",
            r"\bdo i have\b",
            r"\bis this (normal|ptsd|depression|anxiety|adhd|bipolar)\b",
            r"\bwhat (do|might) (my|these) symptom(s)? mean\b",
            r"\binterpret\b.*\b(records|mri|x-?ray|labs?|results?)\b",
            r"\bread my (records|mri|x-?ray|labs?|results?)\b",
            r"\b(am i|are we)\s+eligible\b",
            r"\beligibilit(y|ies)\b",
            r"\bwhat (rating|percent|%)\b",
            r"\b\d{1,3}\s*%\b",
            r"\bchance of\b|\blikely to (win|get approved)\b|\bwill i get\b",
            r"\bservice\s*connect(ed|ion)\b.*\b(chance|likely|probability)\b",
        ]

        # Process markers allowed at admin/process level.
        self.process_markers = {
            "claim",
            "appeal",
            "supplemental",
            "hlr",
            "higher-level review",
            "evidence",
            "records",
            "buddy statement",
            "lay statement",
            "nexus",
            "c&p",
            "exam",
            "dbq",
            "date",
            "timeline",
            "service",
            "treatment",
            "provider",
            "va form",
            "intent to file",
            "itf",
            "submission",
            "decision letter",
        }

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"\b[a-zA-Z0-9']+\b", text.lower())

    def _contains_question(self, text: str) -> bool:
        t = text.strip().lower()
        if "?" in t:
            return True
        return any(w in self._tokenize(text) for w in ("what", "why", "how", "where", "when", "can", "could"))

    def _detect_defense(self, text: str) -> tuple[bool, list[str]]:
        t = text.lower()
        hits = [p for p in self.defense_markers if p in t]

        # Hot state: excessive punctuation or long consecutive caps runs
        exclam = text.count("!")
        caps_runs = re.findall(r"[A-Z]{6,}", text)  # e.g., "THISISLOUD"
        if exclam >= 3 or len(caps_runs) >= 1:
            hits.append("hot_state_signal")

        return (len(hits) > 0), hits

    def _detect_out_of_scope(self, text: str) -> tuple[bool, list[str]]:
        t = text.lower()
        hits: list[str] = []

        for pat in self.oos_intent_patterns:
            if re.search(pat, t):
                hits.append(f"oos_intent:{pat}")

        return (len(hits) > 0), hits

    def _extract_nodes(self, text: str) -> dict[str, list[str]]:
        tokens = self._tokenize(text)

        entities = [
            w
            for w in tokens
            if len(w) >= 5
            and w.isalnum()
            and w not in self.qualifiers
            and w not in self.temporal
        ]

        proc = [p for p in self.process_markers if p in text.lower()]
        dates = re.findall(r"\b(?:\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?|\d{4})\b", text)

        return {"entities": entities[:10], "process_hits": proc[:10], "dates": dates[:10]}

    def _jaccard_divergence(self, a: str, b: str) -> float:
        sa = set(self._tokenize(a))
        sb = set(self._tokenize(b))
        if not sa and not sb:
            return 0.0
        inter = len(sa & sb)
        union = len(sa | sb)
        sim = inter / union if union else 0.0
        return float(1 - sim)

    def _build_observations(self, text: str, nodes: dict[str, list[str]]) -> str:
        parts: list[str] = []
        qflag = "question" if self._contains_question(text) else "statement"
        parts.append(f"Observations (process-only): Your message reads like a {qflag}.")

        if nodes["process_hits"]:
            parts.append(f"Process terms mentioned: {', '.join(nodes['process_hits'][:5])}.")

        if nodes["dates"]:
            parts.append(f"Date-like info detected: {', '.join(nodes['dates'][:3])}.")

        if not nodes["process_hits"] and not nodes["dates"]:
            parts.append("No obvious process artifacts (dates, forms, records, steps) were included in the text.")

        return " ".join(parts)

    def _build_questions(self, nodes: dict[str, list[str]]) -> list[str]:
        qs: list[str] = []

        qs.append(
            "What exact outcome are you trying to achieve (initial claim, increase, appeal/HLR, supplemental, or just readiness check)?"
        )
        qs.append(
            "What evidence types do you already have (service records, treatment timeline, medical documentation you already possess, nexus letter/opinion, buddy/lay statements, C&P/DBQ results if you have them)?"
        )
        qs.append(
            "What’s missing or uncertain right now (one or two admin/process gaps you can name without interpreting medical details)?"
        )

        if not nodes["dates"]:
            qs.append(
                "Do you have 2–3 timeline anchors (service period, first noted issue, first treatment, current status) as dates or approximate months/years?"
            )

        if not nodes["process_hits"]:
            qs.append(
                "Where are you in the VA process right now (not started, intent-to-file filed, submitted, C&P scheduled/completed, decision received)?"
            )

        qs.append("If you want the shortest path: can you list only (1) claim stage, (2) evidence you have, (3) biggest gap?")

        return qs

    def _build_reflective_questions(self) -> list[str]:
        return [
            "What part of this process feels most stuck: paperwork, timelines, finding records, or knowing what counts as evidence?",
            "What would ‘10% clearer’ look like right now: one missing document found, one date confirmed, or one form identified?",
            "If you had to choose one next fact to verify (not solve), what would it be?",
        ]

    def generate(self, text: str, divergence_soft_cap: float = 0.55) -> BBOutput:
        if not isinstance(text, str) or not text.strip():
            return BBOutput(
                observations="Observations (process-only): No text provided.",
                questions=[],
                reflective_enabled=False,
                reflective_questions=[],
                stylistic_divergence=0.0,
                flags=["empty_input"],
                refused=True,
                refusal_reason=RefusalReason.EMPTY_INPUT.value,
            )

        defense, defense_flags = self._detect_defense(text)
        oos, oos_flags = self._detect_out_of_scope(text)

        if oos:
            return BBOutput(
                observations=(
                    "Observations (process-only): Your message appears to request medical interpretation, eligibility, or rating prediction, "
                    "which this module can’t provide."
                ),
                questions=[
                    "If you want a readiness/evidence-gap check instead: what claim stage are you in, and what evidence types do you already have?",
                    "What specific document sources are in play (service records, VA records, private provider records, buddy/lay statements, decision letter, C&P/DBQ paperwork)?",
                    "What is the single biggest process gap you suspect (missing records, missing timeline, missing nexus letter, unclear claimed issue list)?",
                ],
                reflective_enabled=False,
                reflective_questions=[],
                stylistic_divergence=0.0,
                flags=defense_flags + oos_flags + ["refused_out_of_scope"],
                refused=True,
                refusal_reason=RefusalReason.OUT_OF_SCOPE.value,
            )

        nodes = self._extract_nodes(text)
        observations = self._build_observations(text, nodes)
        questions = self._build_questions(nodes)

        reflective_enabled = not defense
        reflective_qs: list[str] = []
        divergence = 0.0

        if reflective_enabled:
            reflective_qs = self._build_reflective_questions()
            divergence = self._jaccard_divergence(
                observations + " " + " ".join(questions),
                " ".join(reflective_qs),
            )
            if divergence > divergence_soft_cap:
                reflective_qs = [
                    "What single piece of info would make this feel less noisy?",
                    "What’s the smallest next fact you can verify?",
                ]
                divergence = self._jaccard_divergence(
                    observations + " " + " ".join(questions),
                    " ".join(reflective_qs),
                )

        return BBOutput(
            observations=observations,
            questions=questions,
            reflective_enabled=reflective_enabled,
            reflective_questions=reflective_qs,
            stylistic_divergence=divergence,
            flags=defense_flags,
            refused=False,
            refusal_reason=None,
        )


def _demo() -> None:
    bb = BattleBuddyHandshake()
    sample = "I filed a claim last year and got denied. I don't know what evidence they want."
    out = bb.generate(sample)
    print(out.observations)
    print("\nQuestions:")
    for q in out.questions:
        print(f"- {q}")
    if out.reflective_enabled:
        print("\nReflective questions (optional):")
        for q in out.reflective_questions:
            print(f"- {q}")


if __name__ == "__main__":
    _demo()
