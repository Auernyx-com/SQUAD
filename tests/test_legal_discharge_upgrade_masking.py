"""
tests/test_legal_discharge_upgrade_masking.py

Independent-audit finding (2026-09-06, round 4, high):
AGENTS/LOGIC/Legal_v0_1.py's route_legal(), TRACK 1 (Discharge Upgrade)
claims result["primary_path"]/result["next_action"] with a plain,
unconditional `=` -- the same bug shape already found and fixed in
MedDisability_v0_1.py (PR #48), Transportation_v0_1.py (PR #51), and
BusinessOpportunity_v0_1.py (PR #53). Every other track in this same file
(Tracks 2-10) uses the file's own `result["primary_path"] or (...)` /
`if not result["next_action"]` convention specifically so an
earlier-evaluated track never clobbers a later, possibly more urgent one.
Track 1 is the sole exception, and because it is evaluated first, it always
wins the race for any veteran with an OTH/dishonorable discharge -- even
one whose more time-critical need is an active VA appeal deadline
(Track 2) or a Veterans Treatment Court diversion window (Track 7).

Confirmed with two independent probes before fixing:
  - discharge="dishonorable" + active DV criminal case + self-defense claim
    (VTC track) still returned primary_path "Discharge Upgrade" and a
    next_action about contacting NVLSP, with zero mention of VTC diversion
    in either field, despite flags correctly including "vtc_track".
  - discharge="other_than_honorable" + legal_needs=["va_appeal"] +
    has_denied_claim=True returned the same "Discharge Upgrade"
    primary_path/next_action instead of the appeal-deadline guidance,
    despite flags correctly including "appeals_lane_not_selected".

Fixed by changing Track 1's result["primary_path"]/result["next_action"]
assignments to the same `result[x] or (...)` / `if not result[x]` guard
every other track in this file already uses. Track 1's other
contributions (secondary_options, key_forms, key_resources, flags, notes)
are untouched.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "AGENTS" / "LOGIC"))

from Legal_v0_1 import VetLegalProfile, route_legal  # noqa: E402


class DischargeUpgradeDoesNotMaskVtcTest(unittest.TestCase):
    def test_oth_plus_vtc_eligible_case_gets_vtc_as_primary(self):
        profile = VetLegalProfile(
            legal_needs=[],
            discharge="dishonorable",
            active_criminal_case=True,
            criminal_case_type="dv",
            claiming_self_defense=True,
        )
        result = route_legal(profile)
        self.assertIn("vtc_track", result["flags"])
        self.assertIn("Veterans Treatment Court", result["primary_path"])
        self.assertIn("Veterans Treatment Court", result["next_action"])

    def test_discharge_upgrade_still_reachable_when_no_higher_priority_track_fires(self):
        # Regression guard: a veteran with ONLY a discharge-upgrade need
        # must still get Track 1 as primary_path.
        profile = VetLegalProfile(
            legal_needs=["discharge_upgrade"],
            discharge="other_than_honorable",
        )
        result = route_legal(profile)
        self.assertEqual(result["primary_path"], "Discharge Upgrade — DRB or BCMR/BCNR")
        self.assertIn("NVLSP", result["next_action"])


class DischargeUpgradeDoesNotMaskAppealDeadlineTest(unittest.TestCase):
    def test_oth_plus_denied_claim_gets_appeal_guidance_as_primary(self):
        profile = VetLegalProfile(
            legal_needs=["va_appeal"],
            discharge="other_than_honorable",
            has_denied_claim=True,
            appeals_lane="none",
        )
        result = route_legal(profile)
        self.assertIn("appeals_lane_not_selected", result["flags"])
        self.assertEqual(result["primary_path"], "VA Appeals — Three Lanes Available")
        self.assertIn("appeal", result["next_action"].lower())


if __name__ == "__main__":
    unittest.main()
