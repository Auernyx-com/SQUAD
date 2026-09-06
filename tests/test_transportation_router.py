"""
tests/test_transportation_router.py

Coverage for MODULES/TRANSPORTATION/src/transportation_router.py's
local-resource lookup wiring. "transportation" is an exact match in the
controlled vocabulary. crisis_transport_track additionally triggers the
crisis-widened mental_health search -- confirmed by reading
Transportation_v0_1.py's Track 6 directly, which points straight at the
Veterans Crisis Line, a genuine self-harm/crisis situation, not just
"urgent."

Runs against the real, committed CO/western_slope.json shard data.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "MODULES" / "TRANSPORTATION" / "src"))

import transportation_router as router  # noqa: E402


class LocalResourceLookupTest(unittest.TestCase):
    def test_crisis_transport_surfaces_a_real_local_resource_via_widening(self):
        result = router.run({
            "transport_needs": ["crisis"],
            "state": "CO",
            "county": "Mesa",
        })
        self.assertEqual(result.status, "OK")
        local_lines = [r for r in result.key_resources if r.startswith("Local (verified):")]
        self.assertTrue(local_lines)

    def test_crisis_local_resources_are_additive_not_a_replacement(self):
        result = router.run({
            "transport_needs": ["crisis"],
            "state": "CO",
            "county": "Mesa",
        })
        joined = " ".join(result.key_resources)
        self.assertIn("988", joined)

    def test_ordinary_need_does_not_crash_even_with_no_local_transportation_tag_data(self):
        result = router.run({
            "transport_needs": ["va_appointment"],
            "enrolled_va_healthcare": True,
            "state": "CO",
            "county": "Mesa",
        })
        self.assertEqual(result.status, "OK")

    def test_uncovered_state_degrades_to_national_fallback_only(self):
        result = router.run({
            "transport_needs": ["crisis"],
            "state": "WY",
            "county": "Laramie",
        })
        self.assertEqual(result.status, "OK")
        local_lines = [r for r in result.key_resources if r.startswith("Local (verified):")]
        self.assertEqual(local_lines, [])

    def test_missing_state_does_not_crash(self):
        result = router.run({"transport_needs": ["rural"]})
        self.assertEqual(result.status, "OK")


if __name__ == "__main__":
    unittest.main()
