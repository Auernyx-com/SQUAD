"""
tests/test_business_opportunity_v0_1.py

Independent-audit finding (2026-09-06, round 3, high): AGENTS/LOGIC/
BusinessOpportunity_v0_1.py's GATE 1 correctly identifies a dishonorable
discharge as BLOCKED and sets primary_path="Discharge Upgrade + Pursue
Open Tracks" with a note explaining certification "requires honorable
conditions discharge... Discharge upgrade... is the first step." But
GATE 1 never sets next_action (it stays None), and TRACK 1 (certification,
`if True:` -- "always runs") never checks discharge either --
check_certification_eligibility() only checks ownership/control/SC-
disability, never discharge. Since cert_check["certs"] ends up non-empty
regardless of discharge, TRACK 1's guarded assignment
(`result["next_action"] = result["next_action"] or (...)`) fills in
next_action with "Start at vetcert.sba.gov to apply for VOSB/SDVOSB
certification" -- directly contradicting the gate's own primary_path and
notes, and directly contradicting the gate's own comment: "Don't fully
block — some tracks still open" only ever meant to open non-certification
tracks (SBA/SCORE/GSA, all listed in the BLOCKED secondary_options), not
this one.

Confirmed directly before fixing: a dishonorable-discharge, business-
owning, SC-disabled veteran got next_action pointing them to apply for
VOSB/SDVOSB certification -- the same output whose own primary_path/notes
say that's exactly what they're blocked from.

Fixed by not running TRACK 1's certification logic at all when GATE 1's
qualification status is BLOCKED -- every part of TRACK 1's body is
inherently about certification eligibility, so there is no partial
content to preserve when certification itself is the thing discharge
blocks. TRACK 2 (federal contracting / SAM.gov registration) is
untouched -- registering on SAM.gov does not itself require VOSB/SDVOSB
certification, so it isn't part of this contradiction.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "AGENTS" / "LOGIC"))

from BusinessOpportunity_v0_1 import BusinessOpportunityProfile, route_business_opportunity  # noqa: E402


class DischargeBlockedCertificationContradictionTest(unittest.TestCase):
    def test_dishonorable_discharge_next_action_does_not_point_to_certification(self):
        profile = BusinessOpportunityProfile(
            discharge="dishonorable", service_connected_disability=True,
            disability_rating=70, business_stage="existing", need_branches=[],
            owns_51_percent=True, controls_operations=True, state="TX",
        )
        result = route_business_opportunity(profile)

        self.assertEqual(result["qualification"]["status"], "BLOCKED")
        self.assertEqual(result["primary_path"], "Discharge Upgrade + Pursue Open Tracks")
        self.assertNotIn("vetcert.sba.gov", (result["next_action"] or ""))
        self.assertEqual(result["certifications"], [])

    def test_dishonorable_discharge_still_has_the_open_tracks_the_gate_promised(self):
        profile = BusinessOpportunityProfile(
            discharge="dishonorable", service_connected_disability=True,
            disability_rating=70, business_stage="existing", need_branches=[],
            owns_51_percent=True, controls_operations=True, state="TX",
        )
        result = route_business_opportunity(profile)
        joined = " ".join(result["secondary_options"])
        self.assertIn("SBA", joined)
        self.assertIn("discharge upgrade", joined.lower())

    def test_honorable_discharge_still_gets_certification_as_before_no_regression(self):
        profile = BusinessOpportunityProfile(
            discharge="honorable", service_connected_disability=True,
            disability_rating=70, business_stage="existing", need_branches=[],
            owns_51_percent=True, controls_operations=True, state="TX",
        )
        result = route_business_opportunity(profile)

        self.assertNotEqual(result["certifications"], [])
        self.assertIn("vetcert.sba.gov", result["next_action"])

    def test_oth_limited_discharge_still_gets_certification_no_regression(self):
        # LIMITED status (OTH) is not BLOCKED -- certification track should
        # still run, only the hard BLOCKED status suppresses it.
        profile = BusinessOpportunityProfile(
            discharge="other_than_honorable", service_connected_disability=True,
            disability_rating=70, business_stage="existing", need_branches=[],
            owns_51_percent=True, controls_operations=True, state="TX",
        )
        result = route_business_opportunity(profile)

        self.assertEqual(result["qualification"]["status"], "LIMITED")
        self.assertNotEqual(result["certifications"], [])


if __name__ == "__main__":
    unittest.main()
