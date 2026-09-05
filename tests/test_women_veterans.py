"""
tests/test_women_veterans.py

Regression coverage for a severe priority-ordering bug in
AGENTS/LOGIC/WomenVeterans_v0_1.py's route_women_veterans().

TRACK 1 (Women's Health Care) fires for almost every veteran — its
condition is `"healthcare" in needs or not profile.enrolled_va_healthcare`,
so it fires whenever a veteran simply isn't yet VA-enrolled, regardless of
what she actually asked for. It ran FIRST in the function, and unlike every
other track in this file (and in Housing_v0_1.py / Legal_v0_1.py), it set
`primary_path` and `next_action` UNCONDITIONALLY instead of the file's own
`result["next_action"] = result["next_action"] or (...)` convention.

The result: a currently-homeless woman veteran who hadn't yet enrolled in
VA healthcare got flagged "homeless_urgent" internally, but her next_action
was "Call the Women Veterans Call Center to start enrollment" — the
time-critical "Call VA Homeless Veterans Hotline NOW" action was silently
suppressed, because the enrollment nudge claimed next_action first and
nothing after it could override an already-set value.

Confirmed against the pre-fix code with a direct probe: WomenVetProfile(
needs=["housing"], housing_situation="homeless", enrolled_va_healthcare=False)
returned next_action mentioning "start enrollment", not the homeless
hotline, despite "homeless_urgent" being in flags.

Fixed by moving the Housing & Homelessness track to evaluate BEFORE the
healthcare-enrollment nudge (matching every sibling Division file's
"most urgent runs first" convention — Housing_v0_1.py itself puts chronic
homelessness as its literal Track 1 for this same reason) and by making the
healthcare track's primary_path/next_action assignments respect the
already-set-wins convention like every other track in the file.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "AGENTS" / "LOGIC"))

from WomenVeterans_v0_1 import WomenVetProfile, route_women_veterans  # noqa: E402


class HomelessCrisisTakesPriorityOverEnrollmentNudgeTest(unittest.TestCase):
    def test_homeless_and_unenrolled_gets_the_homeless_hotline_as_next_action(self):
        profile = WomenVetProfile(
            needs=["housing"],
            housing_situation="homeless",
            enrolled_va_healthcare=False,
        )
        result = route_women_veterans(profile)

        self.assertIn("homeless_urgent", result["flags"])
        self.assertIn("Homeless Veterans Hotline NOW", result["next_action"])
        self.assertNotIn("start enrollment", result["next_action"])
        self.assertEqual(result["primary_path"], "Women Veterans Housing")

    def test_homeless_and_already_enrolled_still_gets_the_homeless_hotline(self):
        profile = WomenVetProfile(
            needs=["housing"],
            housing_situation="homeless",
            enrolled_va_healthcare=True,
        )
        result = route_women_veterans(profile)

        self.assertIn("Homeless Veterans Hotline NOW", result["next_action"])


class EnrollmentNudgeStillWorksWhenNotUrgentTest(unittest.TestCase):
    def test_unenrolled_with_no_housing_crisis_still_gets_enrollment_nudge(self):
        profile = WomenVetProfile(needs=["healthcare"], enrolled_va_healthcare=False)
        result = route_women_veterans(profile)

        self.assertEqual(result["primary_path"], "VA Women's Health Care — Enroll First")
        self.assertIn("Call the Women Veterans Call Center", result["next_action"])

    def test_at_risk_housing_does_not_claim_next_action_leaving_enrollment_nudge_intact(self):
        # at_risk (not full "homeless") never set next_action even before the
        # fix -- this asserts that behavior is preserved by the reorder.
        profile = WomenVetProfile(
            needs=["housing"],
            housing_situation="at_risk",
            enrolled_va_healthcare=False,
        )
        result = route_women_veterans(profile)

        self.assertEqual(result["primary_path"], "Women Veterans Housing")
        self.assertIn("Call the Women Veterans Call Center", result["next_action"])
        self.assertIn("housing_track", result["flags"])


if __name__ == "__main__":
    unittest.main()
