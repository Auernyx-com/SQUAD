"""
tests/test_transportation_v0_1.py

Independent-audit finding (2026-09-06, round 3, critical):
AGENTS/LOGIC/Transportation_v0_1.py's route_transportation(), TRACK 1 (VA
Beneficiary Travel / BTSSS) claims result["primary_path"]/result["next_action"]
with a plain, unconditional `=` -- the exact bug shape already found and
fixed in MedDisability_v0_1.py (PR #48). TRACK 6 (crisis) is correctly
guarded (`result["primary_path"] or (...)`, `if not result["next_action"]`)
specifically so it never clobbers whatever ran first -- but that's exactly
what silently defeats it here: a veteran who selects BOTH "va_appointment"
(or is simply VA-enrolled) AND "crisis" gets Track 1's BTSSS mileage-
reimbursement guidance as their headline primary_path/next_action, with
the crisis guidance ("Call 988 press 1... or 911. Do not wait.") never
reaching those two most-prominent fields at all -- even though the
crisis_transport_track flag correctly fires and crisis text IS added to
secondary_options/key_resources.

Confirmed with two independent probes before fixing: VetTransportProfile
with transport_needs=['va_appointment', 'crisis'] and separately
transport_needs=['daily_transit', 'crisis'] both returned primary_path
"VA Beneficiary Travel — BTSSS Mileage Reimbursement" and a next_action
about registering for BTSSS and submitting claims within 30 days -- with
zero mention of 988/911 in either of the two fields a real coordinator/CLI
surfaces most prominently to the veteran.

Fixed by not letting Track 1 claim primary_path/next_action when "crisis"
is also in transport_needs, letting Track 6's existing guard do what it
was already written to do. Track 1's other contributions (secondary_options,
key_forms, key_resources, flags, notes) are untouched -- they were never
the bug, and BTSSS info is still relevant once the crisis is addressed.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "AGENTS" / "LOGIC"))

from Transportation_v0_1 import VetTransportProfile, route_transportation  # noqa: E402


class CrisisTransportNotMaskedByBtssTest(unittest.TestCase):
    def test_va_appointment_plus_crisis_gets_crisis_as_primary(self):
        profile = VetTransportProfile(
            transport_needs=["va_appointment", "crisis"],
            has_sc_disability=True, disability_rating=50, enrolled_va_healthcare=True,
            is_rural=False, has_vehicle=True, can_drive=True, needs_adaptive_vehicle=False,
            state="TX", county="Bexar",
        )
        result = route_transportation(profile)

        self.assertEqual(result["primary_path"], "Crisis Transport — Immediate Resources")
        self.assertIn("988", result["next_action"])
        self.assertIn("crisis_transport_track", result["flags"])
        # Track 1's other contributions must still be present -- this fix
        # is scoped to primary_path/next_action only.
        self.assertIn("va_beneficiary_travel", result["flags"])
        self.assertIn("btsss_eligible", result["flags"])

    def test_daily_transit_plus_crisis_also_gets_crisis_as_primary(self):
        # Independent scenario -- different transport_needs combination and
        # different eligibility path, same underlying bug shape.
        profile = VetTransportProfile(
            transport_needs=["daily_transit", "crisis"],
            has_sc_disability=True, disability_rating=10, enrolled_va_healthcare=True,
            is_rural=True, has_vehicle=False, can_drive=True, needs_adaptive_vehicle=False,
            state="OH", county="Franklin",
        )
        result = route_transportation(profile)

        self.assertEqual(result["primary_path"], "Crisis Transport — Immediate Resources")
        self.assertIn("988", result["next_action"])

    def test_va_appointment_without_crisis_still_gets_btsss_as_primary_no_regression(self):
        profile = VetTransportProfile(
            transport_needs=["va_appointment"],
            has_sc_disability=True, disability_rating=50, enrolled_va_healthcare=True,
            is_rural=False, has_vehicle=True, can_drive=True, needs_adaptive_vehicle=False,
            state="TX", county="Bexar",
        )
        result = route_transportation(profile)

        self.assertEqual(result["primary_path"], "VA Beneficiary Travel — BTSSS Mileage Reimbursement")
        self.assertIn("Register for BTSSS", result["next_action"])

    def test_crisis_alone_still_works_no_regression(self):
        profile = VetTransportProfile(
            transport_needs=["crisis"],
            has_sc_disability=False, disability_rating=None, enrolled_va_healthcare=False,
            is_rural=False, has_vehicle=True, can_drive=True, needs_adaptive_vehicle=False,
            state="TX", county="Bexar",
        )
        result = route_transportation(profile)

        self.assertEqual(result["primary_path"], "Crisis Transport — Immediate Resources")
        self.assertIn("988", result["next_action"])


if __name__ == "__main__":
    unittest.main()
