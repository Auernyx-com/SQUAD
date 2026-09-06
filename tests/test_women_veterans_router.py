"""
tests/test_women_veterans_router.py

A real bug found in MODULES/WOMEN_VETERANS/src/women_veterans_router.py,
verified directly against the real intake bridge before fixing:

women_veterans_router.py validated and read a field named "housing_situation"
against {"stable","at_risk","homeless","unknown"} -- but
AGENTS/CORE/PATHFINDER/questionnaire_intake_bridge_v1.py (the actual
real-intake path) has never sent that field name at all. It sends
"housing_status", with values unhoused/unstable/at_risk/stable/unknown
(see that module's own _map_housing_status) -- every other division's
router (housing_router.py included) already reads exactly that
field/vocabulary.

Confirmed via git stash before writing the fix: on real bridge-built
intake for a veteran who selected "unsheltered" (street-level
homelessness) housing_status, women_veterans_router.run() returned
flags=["housing_track", "womens_healthcare_track"] -- missing
"homeless_urgent" entirely. WomenVeterans_v0_1.py's own Track 6
(Housing/Homeless), specifically reordered ahead of Track 1 in an
earlier fix because a housing crisis must take priority, keys directly
off profile.housing_situation in ("homeless", "at_risk") -- unreachable
from real intake data for as long as this field-name mismatch existed.

No prior test caught this because tests/test_women_veterans.py
constructs WomenVetProfile directly (the AGENTS/LOGIC dataclass), which
bypasses this router -- and its bug -- entirely. This file exercises the
router's run() the way the real coordinator actually calls it, on a
payload shaped like the bridge's real output.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "MODULES" / "WOMEN_VETERANS" / "src"))

import women_veterans_router as router  # noqa: E402


def _bridge_shaped_payload(**overrides):
    payload = {
        "discharge": "honorable",
        "needs": ["housing"],
        "housing_status": "unknown",
        "state": "CO",
        "county": "Mesa",
    }
    payload.update(overrides)
    return payload


class HousingStatusFieldNameTest(unittest.TestCase):
    def test_run_reads_housing_status_not_housing_situation(self):
        # "housing_situation" is not a real field this router should ever
        # receive from the actual intake path -- confirms it's simply
        # ignored now rather than silently accepted as if it mattered.
        payload = _bridge_shaped_payload(housing_status="unhoused", housing_situation="stable")
        result = router.run(payload)
        self.assertIn("homeless_urgent", result.flags)

    def test_street_homelessness_reaches_the_homeless_urgent_track(self):
        payload = _bridge_shaped_payload(housing_status="unhoused")
        result = router.run(payload)
        self.assertEqual(result.status, "OK")
        self.assertIn("homeless_urgent", result.flags)

    def test_at_risk_housing_reaches_the_at_risk_track_not_homeless(self):
        payload = _bridge_shaped_payload(housing_status="at_risk")
        result = router.run(payload)
        self.assertIn("housing_track", result.flags)
        self.assertNotIn("homeless_urgent", result.flags)

    def test_unstable_maps_to_the_at_risk_bucket_not_lost_as_unknown(self):
        # "unstable" has no exact equivalent in WomenVeterans_v0_1.py's own
        # vocabulary -- documented approximation, but it must not just
        # disappear into "unknown" and lose the signal entirely.
        payload = _bridge_shaped_payload(housing_status="unstable")
        result = router.run(payload)
        self.assertIn("housing_track", result.flags)

    def test_stable_housing_does_not_trigger_any_housing_urgency(self):
        payload = _bridge_shaped_payload(housing_status="stable", needs=[])
        result = router.run(payload)
        self.assertNotIn("homeless_urgent", result.flags)

    def test_invalid_housing_status_value_is_rejected(self):
        payload = _bridge_shaped_payload(housing_status="not_a_real_value")
        result = router.run(payload)
        self.assertEqual(result.status, "NEEDS_INPUT")

    def test_missing_housing_status_defaults_safely_to_unknown(self):
        payload = _bridge_shaped_payload()
        del payload["housing_status"]
        result = router.run(payload)
        self.assertEqual(result.status, "OK")
        self.assertNotIn("homeless_urgent", result.flags)


class NativeVocabularyCliRegressionTest(unittest.TestCase):
    """women_veterans_cli.py is a real, separate caller of this router that
    never goes through the bridge at all -- it sends "housing_situation"
    directly in WomenVeterans_v0_1.py's own native vocabulary (stable/
    at_risk/homeless/unknown), which is exactly the field/vocabulary this
    router read before the housing_status fix above. That fix correctly
    closed the bridge-path bug but, confirmed directly, silently broke the
    CLI's own housing question in the process: '{"needs": ["housing"],
    "housing_situation": "homeless"}' produced flags without
    "homeless_urgent" -- the same bug reintroduced for a different caller.
    """

    def test_cli_native_homeless_value_still_reaches_the_homeless_urgent_track(self):
        payload = {"needs": ["housing"], "housing_situation": "homeless"}
        result = router.run(payload)
        self.assertEqual(result.status, "OK")
        self.assertIn("homeless_urgent", result.flags)

    def test_cli_native_at_risk_value_reaches_housing_track_not_homeless(self):
        payload = {"needs": ["housing"], "housing_situation": "at_risk"}
        result = router.run(payload)
        self.assertIn("housing_track", result.flags)
        self.assertNotIn("homeless_urgent", result.flags)

    def test_cli_native_stable_value_triggers_no_housing_urgency(self):
        payload = {"needs": [], "housing_situation": "stable"}
        result = router.run(payload)
        self.assertNotIn("homeless_urgent", result.flags)

    def test_invalid_native_housing_situation_value_is_rejected(self):
        payload = {"needs": ["housing"], "housing_situation": "not_a_real_value"}
        result = router.run(payload)
        self.assertEqual(result.status, "NEEDS_INPUT")

    def test_housing_status_takes_precedence_if_both_fields_somehow_present(self):
        payload = {
            "needs": ["housing"],
            "housing_status": "at_risk",     # bridge vocab -> would map to at_risk
            "housing_situation": "homeless",  # native vocab -- should be ignored
        }
        result = router.run(payload)
        self.assertNotIn("homeless_urgent", result.flags)


if __name__ == "__main__":
    unittest.main()
