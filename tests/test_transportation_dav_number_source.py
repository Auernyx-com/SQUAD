"""
tests/test_transportation_dav_number_source.py

Independent-audit finding (2026-09-08, round 6, high):
Transportation_v0_1.py hardcoded "1-800-424-3838" as the DAV
Transportation Network's phone number in two places (Track 2), while
MODULES/_shared/contacts.py -- the file whose own documented policy is
"When a number changes, fix it here only. One edit, all divisions
update" -- defines DAV_SERVICE_LINE = "1-800-741-4990" for the same
organization (DAV). Transportation_v0_1.py never imported contacts.py at
all (confirmed via grep -- only Housing_v0_1.py and Legal_v0_1.py did, of
all 8 division routers). This meant two conflicting "verified" DAV
numbers coexisted in the codebase with no reconciliation mechanism, and
the wrong one was reachable: confirmed with a direct probe that
route_transportation() surfaced "1-800-424-3838" in both
secondary_options and next_action.

This fix does NOT assert which of the two numbers is factually correct
(that requires verification this environment cannot perform) -- it fixes
the architectural bug: Transportation now imports and uses contacts.py's
DAV_SERVICE_LINE, the same way Housing_v0_1.py and Legal_v0_1.py already
do, so there is exactly one place to correct the number if it's ever
found to be wrong, matching the file's own stated single-source-of-truth
policy.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "AGENTS" / "LOGIC"))
sys.path.insert(0, str(REPO_ROOT / "MODULES" / "_shared"))

from contacts import DAV_SERVICE_LINE  # noqa: E402
from Transportation_v0_1 import VetTransportProfile, route_transportation  # noqa: E402


class TransportationUsesSharedDavNumberTest(unittest.TestCase):
    def test_dav_track_surfaces_the_shared_contacts_number(self):
        profile = VetTransportProfile(transport_needs=["va_appointment"])
        result = route_transportation(profile)
        self.assertIn(DAV_SERVICE_LINE, result["next_action"])
        self.assertTrue(any(DAV_SERVICE_LINE in s for s in result["secondary_options"]))

    def test_dav_track_no_longer_surfaces_the_conflicting_hardcoded_number(self):
        profile = VetTransportProfile(transport_needs=["daily_transit"])
        result = route_transportation(profile)
        self.assertNotIn("1-800-424-3838", result["next_action"])
        self.assertFalse(any("1-800-424-3838" in s for s in result["secondary_options"]))


if __name__ == "__main__":
    unittest.main()
