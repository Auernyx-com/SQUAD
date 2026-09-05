"""
tests/test_crisis_redirect.py

MODULES/CRISIS_REDIRECT had zero test coverage before this file. Its job is
to detect self-harm / suicide / immediate-danger language in free text and
escalate to crisis resources — the single most safety-critical piece of
logic in this repository.

PRIMARY REGRESSION: a smart/curly apostrophe evaded detection entirely.

_contains_any() only lower-cased the haystack before substring matching.
The phrase list manually enumerated straight-apostrophe ("i'm going to kill
myself") and no-apostrophe ("im going to kill myself") variants of each
phrase, but NOT the curly apostrophe (’, U+2019) that iOS, Android, and
virtually every modern word processor auto-substitutes for a plain "'" by
default. A veteran typing "I'm going to kill myself" completely normally on
a phone — where the keyboard silently turns that into "I’m going to kill
myself" — got status="OK" with zero crisis resources and zero escalation
questions. The identical phrase with a straight apostrophe correctly
triggered "CRISIS".

Confirmed against the pre-fix code with a direct probe before writing these
tests: crisis_redirect({"text": "I’m going to kill myself tonight"}) (curly
apostrophe) returned status="OK", while the same text with a straight
apostrophe or no apostrophe at all correctly returned status="CRISIS".

Fixed by normalizing curly/backtick apostrophe variants to a straight
apostrophe on both the haystack and each needle before matching, in
_contains_any() itself — so every phrase list (the hard crisis triggers and
the softer clarifying-question triggers) is protected by one change instead
of needing every future phrase to remember to enumerate every apostrophe
variant by hand.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "MODULES" / "CRISIS_REDIRECT" / "src"))

from crisis_redirect import crisis_redirect  # noqa: E402


class SmartQuoteEvasionRegressionTest(unittest.TestCase):
    def test_curly_right_apostrophe_still_triggers_crisis(self):
        # U+2019 RIGHT SINGLE QUOTATION MARK -- what a phone keyboard
        # actually inserts by default when a user types a straight "'".
        result = crisis_redirect({"text": "I’m going to kill myself tonight"})
        self.assertEqual(result.status, "CRISIS")
        self.assertTrue(result.resources)

    def test_curly_left_apostrophe_variant_still_triggers_crisis(self):
        # U+2018 LEFT SINGLE QUOTATION MARK -- less common but seen from
        # some input methods / pasted text.
        result = crisis_redirect({"text": "I‘m going to kill myself"})
        self.assertEqual(result.status, "CRISIS")

    def test_straight_apostrophe_still_works_no_regression(self):
        result = crisis_redirect({"text": "I'm going to kill myself tonight"})
        self.assertEqual(result.status, "CRISIS")

    def test_no_apostrophe_variant_still_works_no_regression(self):
        result = crisis_redirect({"text": "im going to kill myself tonight"})
        self.assertEqual(result.status, "CRISIS")

    def test_curly_apostrophe_in_soft_signal_phrase_still_asks_clarifying_questions(self):
        # "can't go on" is a soft-signal trigger (status stays OK, but
        # clarifying questions get added) -- must also survive the curly
        # apostrophe a phone keyboard would actually produce.
        result = crisis_redirect({"text": "I can’t go on anymore, feeling overwhelmed"})
        self.assertEqual(result.status, "OK")
        self.assertTrue(result.questions)


class CrisisDetectionBaselineTest(unittest.TestCase):
    def test_explicit_immediate_danger_signal_triggers_crisis(self):
        result = crisis_redirect({"text": "", "signals": {"immediate_danger": True}})
        self.assertEqual(result.status, "CRISIS")

    def test_explicit_self_harm_intent_signal_triggers_crisis(self):
        result = crisis_redirect({"text": "", "signals": {"self_harm_intent": True}})
        self.assertEqual(result.status, "CRISIS")

    def test_suicide_keyword_triggers_crisis(self):
        result = crisis_redirect({"text": "I've been thinking about suicide a lot lately"})
        self.assertEqual(result.status, "CRISIS")

    def test_unrelated_text_does_not_trigger_crisis(self):
        result = crisis_redirect({"text": "I need help checking my disability claim status"})
        self.assertEqual(result.status, "OK")
        self.assertEqual(result.resources, [])

    def test_empty_payload_does_not_crash_and_is_ok(self):
        result = crisis_redirect({})
        self.assertEqual(result.status, "OK")

    def test_crisis_result_includes_988_resource(self):
        result = crisis_redirect({"text": "I want to die"})
        self.assertEqual(result.status, "CRISIS")
        detail_text = " ".join(r["detail"] for r in result.resources)
        self.assertIn("988", detail_text)


if __name__ == "__main__":
    unittest.main()
