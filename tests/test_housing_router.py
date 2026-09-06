"""
tests/test_housing_router.py

Coverage for MODULES/HOUSING/src/housing_router.py's local-resource
lookup wiring (MODULES/_shared/local_resources.py) -- part of closing
the gap found while auditing the division routers: none of them ever
queried the real, curated resource database. No prior test coverage
existed for this router at all.

Runs against the real, committed CO/western_slope.json shard data
(Mesa County) for the same reason tests/test_local_resources.py does:
a change to the real data that breaks this wiring should show up here.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "MODULES" / "HOUSING" / "src"))

import housing_router as router  # noqa: E402


class LocalResourceLookupTest(unittest.TestCase):
    def test_covered_county_surfaces_a_real_local_resource(self):
        result = router.run({
            "housing_status": "unhoused",
            "is_chronically_homeless": True,
            "homelessness_months": 8,
            "discharge": "honorable",
            "state": "CO",
            "county": "Mesa",
        })
        self.assertEqual(result.status, "OK")
        local_lines = [r for r in result.key_resources if r.startswith("Local (verified):")]
        self.assertTrue(local_lines)

    def test_local_resources_are_additive_not_a_replacement(self):
        # The existing national-line fallback must still be present
        # alongside any local match, not replaced by it.
        result = router.run({
            "housing_status": "unhoused",
            "is_chronically_homeless": True,
            "discharge": "honorable",
            "state": "CO",
            "county": "Mesa",
        })
        joined = " ".join(result.key_resources)
        self.assertIn("1-877-4AID-VET", joined)

    def test_uncovered_state_degrades_to_national_fallback_only(self):
        result = router.run({
            "housing_status": "at_risk",
            "discharge": "honorable",
            "state": "WY",
            "county": "Laramie",
        })
        self.assertEqual(result.status, "OK")
        local_lines = [r for r in result.key_resources if r.startswith("Local (verified):")]
        self.assertEqual(local_lines, [])

    def test_missing_state_does_not_crash_and_has_no_local_lines(self):
        result = router.run({"housing_status": "unstable", "discharge": "honorable"})
        self.assertEqual(result.status, "OK")
        local_lines = [r for r in result.key_resources if r.startswith("Local (verified):")]
        self.assertEqual(local_lines, [])

    def test_dv_situation_widens_the_search_tags_and_still_succeeds(self):
        # Not asserting a specific match exists for DV shelters in the
        # current data -- only that requesting the wider tag set never
        # breaks the routing result.
        result = router.run({
            "housing_status": "unstable",
            "has_dv_situation": True,
            "discharge": "honorable",
            "state": "CO",
            "county": "Mesa",
        })
        self.assertEqual(result.status, "OK")


if __name__ == "__main__":
    unittest.main()
