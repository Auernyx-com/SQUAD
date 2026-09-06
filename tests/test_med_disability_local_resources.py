"""
tests/test_med_disability_local_resources.py

Coverage for MODULES/MEDICAL_DISABILITY/src/med_disability_router.py's
local-resource lookup wiring, kept separate from tests/test_med_disability.py
(which covers route_med_disability() LOGIC directly, and the
recent_denial appeal-deadline fix) to keep each file focused on one
concern.

Found and fixed alongside this wiring: VetMedProfile's own "location"
field is never read by any Track in route_med_disability() (confirmed
via grep), and the real bridge never sends a flat "location" string
anyway -- it sends separate "state"/"county" keys. That field was always
a no-op. This wiring reads state/county directly off payload instead,
matching every other Division's own local-resource wiring.

mst_flagged/ptsd_flagged/tbi_flagged trigger the crisis-widened
mental_health search -- the clearest, most directly applicable use of
that widening across all 8 Divisions (this is exactly the "health and
welfare or self-harm concern" case GOVERNANCE/
auernyx.nonprofit.scope.json's crisis_widened_branches was built for).

Runs against the real, committed CO/western_slope.json shard data.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "MODULES" / "MEDICAL_DISABILITY" / "src"))

import med_disability_router as router  # noqa: E402


class LocalResourceLookupTest(unittest.TestCase):
    def test_covered_county_surfaces_a_real_local_resource(self):
        result = router.route({
            "va_status": "not_enrolled",
            "discharge": "honorable",
            "state": "CO",
            "county": "Mesa",
        })
        self.assertEqual(result.status, "OK")
        local_lines = [r for r in result.key_resources if r.startswith("Local (verified):")]
        self.assertTrue(local_lines)

    def test_ptsd_flag_widens_to_find_an_additional_mental_health_match(self):
        plain = router.route({
            "va_status": "has_rating", "discharge": "honorable",
            "disability_rating": 70, "state": "CO", "county": "Mesa",
        })
        with_ptsd = router.route({
            "va_status": "has_rating", "discharge": "honorable",
            "disability_rating": 70, "ptsd": True, "state": "CO", "county": "Mesa",
        })
        plain_local = {r for r in plain.key_resources if r.startswith("Local (verified):")}
        ptsd_local = {r for r in with_ptsd.key_resources if r.startswith("Local (verified):")}
        self.assertTrue(ptsd_local.issuperset(plain_local))
        self.assertGreater(len(ptsd_local), len(plain_local))

    def test_local_resources_are_additive_not_a_replacement(self):
        result = router.route({
            "va_status": "not_enrolled",
            "discharge": "honorable",
            "state": "CO",
            "county": "Mesa",
        })
        joined = " ".join(result.secondary_options)
        self.assertIn("Vet Centers", joined)

    def test_uncovered_state_degrades_to_national_fallback_only(self):
        result = router.route({
            "va_status": "not_enrolled",
            "discharge": "honorable",
            "state": "WY",
            "county": "Laramie",
        })
        self.assertEqual(result.status, "OK")
        local_lines = [r for r in result.key_resources if r.startswith("Local (verified):")]
        self.assertEqual(local_lines, [])

    def test_missing_state_does_not_crash(self):
        result = router.route({"va_status": "not_enrolled", "discharge": "honorable"})
        self.assertEqual(result.status, "OK")


if __name__ == "__main__":
    unittest.main()
