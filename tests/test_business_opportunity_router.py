"""
tests/test_business_opportunity_router.py

Coverage for MODULES/BUSINESS_OPPORTUNITY/src/business_opportunity_router.py's
local-resource lookup wiring. Uses a fixed tag baseline (advocacy,
resource_referral) rather than flag-driven tags -- see the router's own
comment for why: no dedicated "veteran business" tag exists in the
controlled vocabulary, but every state's VSO/veterans-affairs agency
entry is a real, useful first stop for this too.

Runs against the real, committed CO/western_slope.json shard data.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "MODULES" / "BUSINESS_OPPORTUNITY" / "src"))

import business_opportunity_router as router  # noqa: E402


class LocalResourceLookupTest(unittest.TestCase):
    def test_covered_county_surfaces_a_real_local_resource(self):
        result = router.run({
            "discharge": "honorable",
            "business_stage": "startup",
            "need_branches": ["contracting"],
            "state": "CO",
            "county": "Mesa",
        })
        self.assertEqual(result.status, "OK")
        local_lines = [r for r in result.key_resources if r.startswith("Local (verified):")]
        self.assertTrue(local_lines)

    def test_local_resources_are_additive_not_a_replacement(self):
        result = router.run({
            "discharge": "honorable",
            "state": "CO",
            "county": "Mesa",
        })
        joined = " ".join(result.key_resources)
        self.assertIn("vetcert.sba.gov", joined)

    def test_uncovered_state_degrades_to_national_fallback_only(self):
        result = router.run({
            "discharge": "honorable",
            "state": "WY",
            "county": "Laramie",
        })
        self.assertEqual(result.status, "OK")
        local_lines = [r for r in result.key_resources if r.startswith("Local (verified):")]
        self.assertEqual(local_lines, [])

    def test_missing_state_does_not_crash(self):
        result = router.run({"discharge": "honorable"})
        self.assertEqual(result.status, "OK")


if __name__ == "__main__":
    unittest.main()
