"""
tests/test_women_veterans_healthcare_masking.py

Independent-audit finding (2026-09-06, round 4, high):
AGENTS/LOGIC/WomenVeterans_v0_1.py's route_women_veterans() -- a prior fix
(see tests/test_women_veterans.py) reordered TRACK 6 (Housing) to run
BEFORE TRACK 1 (Women's Health Care / enrollment nudge) so a homeless
veteran's crisis wins the shared primary_path/next_action fields. That fix
only covered Housing. TRACK 1 still runs immediately after Housing and
BEFORE Tracks 2 (Maternity), 3 (MST), 4 (Mental Health), and 5
(Reproductive Health) -- and its condition (`not
profile.enrolled_va_healthcare`) fires for almost any unenrolled veteran.
Because Track 1 still runs first among these, its guarded
`result["primary_path"] or (...)` assignment still wins the race for any
unenrolled MST survivor, pregnant veteran, or veteran disclosing PTSD.

Confirmed with three independent probes before fixing: WomenVetProfile(
needs=["mst"], has_mst=True, enrolled_va_healthcare=False),
WomenVetProfile(needs=["maternity"], is_pregnant=True,
enrolled_va_healthcare=False), and WomenVetProfile(needs=["mental_health"],
has_ptsd=True, enrolled_va_healthcare=False) all returned primary_path
"VA Women's Health Care — Enroll First" and a generic enrollment
next_action, instead of the MST/maternity/PTSD-specific guidance -- despite
flags correctly including mst_track/maternity_track/mental_health_track/
ptsd_track. Per Track 3's own text, MST-related care does not actually
require VA enrollment first, making the enrollment-first framing
substantively misleading for that population, not just non-optimal.

Fixed by moving Tracks 2-5 to evaluate BEFORE Track 1, matching the same
"most specific/urgent need wins the headline fields" convention already
established for Housing.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "AGENTS" / "LOGIC"))

from WomenVeterans_v0_1 import WomenVetProfile, route_women_veterans  # noqa: E402


class HealthcareEnrollmentDoesNotMaskSpecificTracksTest(unittest.TestCase):
    def test_unenrolled_mst_survivor_gets_mst_guidance_as_primary(self):
        profile = WomenVetProfile(needs=["mst"], has_mst=True, enrolled_va_healthcare=False)
        result = route_women_veterans(profile)
        self.assertIn("mst_track", result["flags"])
        self.assertEqual(result["primary_path"], "MST — Care Without Report")
        self.assertIn("MST Coordinator", result["next_action"])

    def test_unenrolled_pregnant_veteran_gets_maternity_guidance_as_primary(self):
        profile = WomenVetProfile(needs=["maternity"], is_pregnant=True, enrolled_va_healthcare=False)
        result = route_women_veterans(profile)
        self.assertIn("maternity_track", result["flags"])
        self.assertEqual(result["primary_path"], "VA Maternity Care")

    def test_unenrolled_veteran_with_ptsd_gets_mental_health_guidance_as_primary(self):
        profile = WomenVetProfile(needs=["mental_health"], has_ptsd=True, enrolled_va_healthcare=False)
        result = route_women_veterans(profile)
        self.assertIn("mental_health_track", result["flags"])
        self.assertEqual(result["primary_path"], "Women Veterans Mental Health")

    def test_unenrolled_veteran_with_no_specific_track_still_gets_enrollment_nudge(self):
        # Regression guard: Track 1 must still fire and claim the headline
        # fields when nothing more specific applies.
        profile = WomenVetProfile(needs=[], enrolled_va_healthcare=False)
        result = route_women_veterans(profile)
        self.assertIn("womens_healthcare_track", result["flags"])
        self.assertEqual(result["primary_path"], "VA Women's Health Care — Enroll First")

    def test_homeless_crisis_still_wins_over_everything_no_regression(self):
        profile = WomenVetProfile(
            needs=["mst"], has_mst=True, enrolled_va_healthcare=False,
            housing_situation="homeless",
        )
        result = route_women_veterans(profile)
        self.assertIn("homeless_urgent", result["flags"])
        self.assertIn("Homeless Veterans Hotline", result["next_action"])


if __name__ == "__main__":
    unittest.main()
