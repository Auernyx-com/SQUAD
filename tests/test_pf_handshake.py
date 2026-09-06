r"""
tests/test_pf_handshake.py

A real bug found in AGENTS/CORE/PATHFINDER/pf_handshake_v1.py's out-of-scope
detection, verified directly with re.search before touching any code:

    re.search(r"\bwhat (rating|percent|%)\b", "is 70% enough for TDIU?")
    re.search(r"\b\d{1,3}\s*%\b", "is 70% enough for TDIU?")

Both returned None. A literal "%" is a non-word character, so a trailing
\b right after it only matches when a word character immediately follows
with zero space (e.g. "80%rating") -- never true for ordinary text like
"what %", "80%", or "80% rating", all of which end the match on a
non-word-to-non-word or non-word-to-end transition, which is not a \b.

This module's own docstring states a hard design constraint: "NO RATING
PREDICTIONS" / "NO ELIGIBILITY". Because of the dead regex, a real,
plausible veteran message like "Is 70% enough for TDIU?" or "is 70% a
good rating for my knee" was never flagged out-of-scope and would have
gone through PathfinderHandshake.generate() as an ordinary process
question -- exactly the rating-prediction/eligibility interpretation this
module exists to refuse.

Fix: dropped the trailing \b after the literal "%" (kept it for the
"rating"/"percent" word alternatives, where it's not broken). This does
mean a plain statement like "I have 30% currently, how do I file for an
increase?" now also gets soft-refused (any bare N% mention triggers the
gate) -- a false positive, but a soft one: the refusal path still asks
for claim stage and evidence, the same information a process-only answer
would have needed anyway. That tradeoff is the conservative default this
module's own docstring calls for ("Conservative refusals based on intent
patterns"), and the original (broken) regex was already trying to catch
bare percent mentions -- this fix makes that existing intent functional,
it does not introduce a new one.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "AGENTS" / "CORE" / "PATHFINDER"))

from pf_handshake_v1 import PathfinderHandshake  # noqa: E402


class PercentOutOfScopeDetectionTest(unittest.TestCase):
    def setUp(self):
        self.hs = PathfinderHandshake()

    def test_rating_prediction_questions_are_refused(self):
        cases = [
            "Is 70% enough for TDIU?",
            "is 70% a good rating for my knee",
            "what percent will I get",
            "will I get 100%?",
            "80% rating, am I done?",
        ]
        for text in cases:
            with self.subTest(text=text):
                oos, _flags = self.hs._detect_out_of_scope(text)
                self.assertTrue(oos, f"expected out-of-scope refusal for: {text!r}")

    def test_generate_actually_refuses_a_rating_prediction_question(self):
        out = self.hs.generate("Is 70% enough for TDIU?")
        self.assertTrue(out.refused)
        self.assertEqual(out.refusal_reason, "OUT_OF_SCOPE")

    def test_ordinary_process_questions_still_pass(self):
        cases = [
            "I filed a claim last year and got denied. I don't know what evidence they want.",
            "What forms do I need for a supplemental claim?",
            "My C&P exam is scheduled for next month, what should I bring?",
        ]
        for text in cases:
            with self.subTest(text=text):
                oos, _flags = self.hs._detect_out_of_scope(text)
                self.assertFalse(oos, f"did not expect out-of-scope refusal for: {text!r}")


if __name__ == "__main__":
    unittest.main()
