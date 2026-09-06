"""
tests/test_va_benefits_router.py

Coverage for MODULES/VA_BENEFITS/src/va_benefits_router.py's local-
resource lookup wiring. VaBenefitsResult originally had no key_resources
field, so this merged into secondary_options -- found directly, before
this test file was even finished, that pf_coordinator_v1.py's
invoke_division() truncates secondary_options to [:3] when building
next_actions, and every real intake already had 3+ items there before
any local match got appended -- a real local match was completely
invisible in the coordinator's actual output as a result. Added a
key_resources field (not truncated) instead; results merge there now,
matching every other Division.

Runs against the real, committed CO/western_slope.json shard data.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "MODULES" / "VA_BENEFITS" / "src"))

import va_benefits_router as router  # noqa: E402


class LocalResourceLookupTest(unittest.TestCase):
    def test_covered_county_surfaces_a_real_local_resource(self):
        result = router.run({
            "discharge": "honorable",
            "need_branches": ["employment"],
            "state": "CO",
            "county": "Mesa",
        })
        self.assertEqual(result.status, "OK")
        local_lines = [r for r in result.key_resources if r.startswith("Local (verified):")]
        self.assertTrue(local_lines)

    def test_local_resources_are_additive_not_a_replacement(self):
        result = router.run({
            "discharge": "honorable",
            "need_branches": ["employment"],
            "state": "CO",
            "county": "Mesa",
        })
        joined = " ".join(result.secondary_options)
        self.assertIn("careeronestop.org", joined)

    def test_uncovered_state_degrades_to_national_fallback_only(self):
        result = router.run({
            "discharge": "honorable",
            "need_branches": ["employment"],
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
