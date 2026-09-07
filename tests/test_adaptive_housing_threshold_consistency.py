"""
tests/test_adaptive_housing_threshold_consistency.py

Independent-audit finding (2026-09-06, round 4, low):
AGENTS/LOGIC/Housing_v0_1.py and AGENTS/LOGIC/VaBenefits_v0_1.py both
describe the exact same federal program (SAH/SHA adaptive housing grants,
identical dollar figures: $109,986 SAH / $22,036 SHA) but used different
disability-rating thresholds to flag a veteran as a "candidate" -- Housing
used >= 30%, VaBenefits used >= 50%. A veteran at, say, 35% rating got
flagged as an adaptive-housing candidate through one division router but
not the other for the identical program.

Low severity: this is a "candidate/mention" heuristic in both files, not a
hard eligibility gate -- neither router claims to make a final SAH/SHA
determination (real VA eligibility is based on specific certified
disabilities, not a combined rating percentage). The practical impact is
an inconsistent-looking mention across two routers, not a wrong routing
decision.

Fixed by aligning VaBenefits_v0_1.py's threshold to Housing_v0_1.py's
existing 30% (the more inclusive of the two) -- under-mentioning a program
a veteran might actually use is worse than over-mentioning it for a
"candidate" heuristic like this one.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "AGENTS" / "LOGIC"))

from Housing_v0_1 import VetHousingProfile, route_housing  # noqa: E402
from VaBenefits_v0_1 import VaBenefitsProfile, route_va_benefits  # noqa: E402


class AdaptiveHousingThresholdConsistencyTest(unittest.TestCase):
    def test_35_percent_rating_is_a_candidate_in_both_housing_and_va_benefits(self):
        housing_result = route_housing(
            VetHousingProfile(disability_rating=35, housing_status="stable")
        )
        benefits_result = route_va_benefits(
            VaBenefitsProfile(discharge="honorable", disability_rating=35, need_branches=["home_loan"])
        )
        self.assertIn("adaptive_housing_candidate", housing_result["flags"])
        self.assertIn("adaptive_housing_candidate", benefits_result["flags"])
        self.assertTrue(any("Adaptive Housing" in s for s in housing_result["secondary_options"]))
        self.assertTrue(any("SAH Grant" in s for s in benefits_result["secondary_options"]))

    def test_below_30_percent_is_not_a_candidate_in_either_no_regression(self):
        housing_result = route_housing(
            VetHousingProfile(disability_rating=20, housing_status="stable")
        )
        benefits_result = route_va_benefits(
            VaBenefitsProfile(discharge="honorable", disability_rating=20, need_branches=["home_loan"])
        )
        self.assertNotIn("adaptive_housing_candidate", housing_result["flags"])
        self.assertNotIn("adaptive_housing_candidate", benefits_result["flags"])


if __name__ == "__main__":
    unittest.main()
