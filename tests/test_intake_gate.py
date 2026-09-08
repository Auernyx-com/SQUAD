"""
tests/test_intake_gate.py

MODULES/INTAKE_DO_NOT_GUESS is the "do-not-guess intake gate" -- its entire
purpose is to ask a clarifying question rather than proceed on incomplete
data. It had zero test coverage before this file.

BUG: `p.get("location", {}).get("state")` only falls back to {} when the
"location" key is entirely ABSENT from the payload. A payload with
"location": null -- a plausible shape from any intake form that serializes
an unfilled nested object as JSON null rather than omitting the key -- has
the key present with value None, so .get("location", {}) returns None, and
the immediately-following .get("state") crashes with AttributeError. The
same gap existed for "status", and a non-dict truthy value (a stray string)
crashed the (X or {}) idiom the same way since that idiom only protects
against falsy values, not wrong types.

Confirmed against the pre-fix code with direct probes: gate_intake({
"location": None, "need": "housing"}), gate_intake({"location": "somewhere",
...}), gate_intake({"status": None, ...}), and gate_intake({"status":
"weird_string", ...}) all raised AttributeError instead of returning
NEEDS_INPUT with a clarifying question -- exactly the failure mode this
module exists to prevent (crashing is worse than the guessing it's designed
to avoid).

Fixed with an isinstance(..., dict) guard for both "location" and "status",
matching the pattern the file already used for "constraints".
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "MODULES" / "INTAKE_DO_NOT_GUESS" / "src"))

from intake_gate import gate_intake  # noqa: E402


class MalformedNestedFieldsDoNotCrashTest(unittest.TestCase):
    def test_null_location_returns_needs_input_not_a_crash(self):
        result = gate_intake({"location": None, "need": "housing"})
        self.assertEqual(result.status, "NEEDS_INPUT")
        self.assertTrue(any("state" in q.lower() for q in result.questions))

    def test_string_location_returns_needs_input_not_a_crash(self):
        result = gate_intake({"location": "somewhere", "need": "housing"})
        self.assertEqual(result.status, "NEEDS_INPUT")

    def test_null_status_returns_needs_input_not_a_crash(self):
        result = gate_intake({"status": None, "need": "housing", "state": "CO", "county": "Mesa"})
        self.assertEqual(result.status, "NEEDS_INPUT")

    def test_string_status_returns_needs_input_not_a_crash(self):
        result = gate_intake({"status": "weird_string", "need": "housing", "state": "CO", "county": "Mesa"})
        self.assertEqual(result.status, "NEEDS_INPUT")

    def test_empty_payload_returns_needs_input_not_a_crash(self):
        result = gate_intake({})
        self.assertEqual(result.status, "NEEDS_INPUT")
        self.assertTrue(result.questions)


class ValidIntakeStillWorksTest(unittest.TestCase):
    def test_fully_populated_nested_location_and_status_returns_ok(self):
        payload = {
            "location": {"state": "CO", "county": "Mesa"},
            "need": "housing",
            "status": {"housing": "housed", "claim": "not_filed", "employment": "employed"},
            "contact_preference": "phone",
        }
        result = gate_intake(payload)
        self.assertEqual(result.status, "OK")
        self.assertEqual(result.normalized["location"], {"state": "CO", "county": "Mesa"})

    def test_flat_top_level_fields_still_work_as_an_alternative_shape(self):
        payload = {
            "state": "co",
            "county": "Mesa",
            "need": "housing",
            "housing_status": "housed",
            "claim_stage": "not_filed",
            "employment_status": "employed",
            "contact_preference": "phone",
        }
        result = gate_intake(payload)
        self.assertEqual(result.status, "OK")
        self.assertEqual(result.normalized["location"]["state"], "CO")


class CrisisNeverSilentlyDroppedByTheTwoNeedCapTest(unittest.TestCase):
    """Independent-audit finding (2026-09-08, round 12, high): needs beyond
    the first two named were silently discarded by a blind `needs[:2]`, with
    no regard for which ones. Confirmed directly: a veteran naming
    ["housing", "legal", "crisis"] -- in that order -- normalized to
    needs=["housing", "legal"], with "crisis" (the single highest-priority
    need branch this module defines) dropped with no trace. Fixed so
    "crisis" is always kept (and surfaced first) when present, regardless
    of where it fell in the caller's own ordering.
    """

    BASE = {
        "state": "CO",
        "county": "Mesa",
        "housing_status": "unhoused",
        "claim_stage": "not_filed",
        "employment_status": "unemployed",
        "contact_preference": "phone",
    }

    def test_crisis_survives_even_when_named_last_of_three(self):
        result = gate_intake({**self.BASE, "need": ["housing", "legal", "crisis"]})
        self.assertEqual(result.status, "OK")
        self.assertIn("crisis", result.normalized["needs"])

    def test_crisis_kept_first_to_signal_priority(self):
        result = gate_intake({**self.BASE, "need": ["housing", "legal", "crisis"]})
        self.assertEqual(result.normalized["needs"][0], "crisis")

    def test_crisis_named_first_still_works_no_regression(self):
        result = gate_intake({**self.BASE, "need": ["crisis", "housing", "legal"]})
        self.assertIn("crisis", result.normalized["needs"])

    def test_no_crisis_present_the_original_two_cap_still_applies(self):
        # Must not regress the ordinary case -- no crisis in the list, so
        # plain first-two-named behavior is unchanged.
        result = gate_intake({**self.BASE, "need": ["housing", "legal", "education"]})
        self.assertEqual(result.normalized["needs"], ["housing", "legal"])

    def test_only_crisis_named_returns_just_crisis(self):
        result = gate_intake({**self.BASE, "need": ["crisis"]})
        self.assertEqual(result.normalized["needs"], ["crisis"])


if __name__ == "__main__":
    unittest.main()
