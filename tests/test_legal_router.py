"""
tests/test_legal_router.py

Coverage for MODULES/LEGAL/src/legal_router.py's local-resource lookup
wiring (MODULES/_shared/local_resources.py). No prior test coverage
existed for this router at all.

Runs against the real, committed CO/western_slope.json shard data.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "MODULES" / "LEGAL" / "src"))

import legal_router as router  # noqa: E402


class LocalResourceLookupTest(unittest.TestCase):
    def test_covered_county_surfaces_a_real_local_resource(self):
        result = router.run({
            "discharge": "honorable",
            "legal_needs": ["civilian_legal"],
            "state": "CO",
            "county": "Mesa",
        })
        self.assertEqual(result.status, "OK")
        local_lines = [r for r in result.key_resources if r.startswith("Local (verified):")]
        self.assertTrue(local_lines)

    def test_local_resources_are_additive_not_a_replacement(self):
        result = router.run({
            "discharge": "honorable",
            "legal_needs": ["civilian_legal"],
            "state": "CO",
            "county": "Mesa",
        })
        joined = " ".join(result.key_resources)
        self.assertIn("abavetslegalservices.org", joined)

    def test_uncovered_state_degrades_to_national_fallback_only(self):
        result = router.run({
            "discharge": "honorable",
            "legal_needs": ["civilian_legal"],
            "state": "WY",
            "county": "Laramie",
        })
        self.assertEqual(result.status, "OK")
        local_lines = [r for r in result.key_resources if r.startswith("Local (verified):")]
        self.assertEqual(local_lines, [])

    def test_missing_state_does_not_crash(self):
        result = router.run({"discharge": "honorable", "legal_needs": ["civilian_legal"]})
        self.assertEqual(result.status, "OK")


if __name__ == "__main__":
    unittest.main()
