"""
tests/test_women_veterans_local_resources.py

Coverage for MODULES/WOMEN_VETERANS/src/women_veterans_router.py's
local-resource lookup wiring, kept separate from
tests/test_women_veterans_router.py (which covers the housing_status/
housing_situation field-mismatch fix specifically) to keep each file
focused on one concern.

homeless_urgent is treated as this Division's crisis/self-harm-widening
signal since WomenVetProfile has no dedicated self-harm field -- matches
Housing's own treatment of chronic homelessness as urgent.

Runs against the real, committed CO/western_slope.json shard data.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "MODULES" / "WOMEN_VETERANS" / "src"))

import women_veterans_router as router  # noqa: E402


class LocalResourceLookupTest(unittest.TestCase):
    def test_covered_county_surfaces_a_real_local_resource(self):
        result = router.run({
            "needs": ["housing"],
            "housing_status": "unhoused",
            "state": "CO",
            "county": "Mesa",
        })
        self.assertEqual(result.status, "OK")
        local_lines = [r for r in result.key_resources if r.startswith("Local (verified):")]
        self.assertTrue(local_lines)

    def test_local_resources_are_additive_not_a_replacement(self):
        result = router.run({
            "needs": ["housing"],
            "housing_status": "unhoused",
            "state": "CO",
            "county": "Mesa",
        })
        joined = " ".join(result.key_resources)
        self.assertIn("Women Veterans Call Center", joined)

    def test_no_needs_still_returns_ok_and_does_not_crash(self):
        result = router.run({"state": "CO", "county": "Mesa"})
        self.assertEqual(result.status, "OK")

    def test_uncovered_state_degrades_to_national_fallback_only(self):
        result = router.run({
            "needs": ["housing"],
            "housing_status": "unhoused",
            "state": "WY",
            "county": "Laramie",
        })
        self.assertEqual(result.status, "OK")
        local_lines = [r for r in result.key_resources if r.startswith("Local (verified):")]
        self.assertEqual(local_lines, [])

    def test_missing_state_does_not_crash(self):
        result = router.run({"needs": ["mst"], "has_mst": True})
        self.assertEqual(result.status, "OK")


if __name__ == "__main__":
    unittest.main()
