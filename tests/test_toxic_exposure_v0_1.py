"""
tests/test_toxic_exposure_v0_1.py

Independent-audit finding (2026-09-06, round 3, high): AGENTS/LOGIC/
ToxicExposure_v0_1.py's route_toxic_exposure() never reads `discharge`
anywhere -- confirmed by grep, the field exists on ToxicExposureProfile
(collected and validated by the CLI/module wrapper) but has zero read
references in the routing function itself. A veteran with a dishonorable
discharge and burn-pit exposure gets IDENTICAL routing output to an
honorably-discharged veteran: told to file VA Form 21-526EZ (Disability
Compensation) for a "PACT Act... Presumptive Claim", with zero mention
that dishonorable discharge bars most VA disability compensation -- as
this codebase's own MedDisability_v0_1.py/VaBenefits_v0_1.py/
BusinessOpportunity_v0_1.py state explicitly for the exact same field
value.

Confirmed directly before fixing: a dishonorable-discharge profile and an
honorable-discharge profile, otherwise identical, produced byte-identical
routing output.

IMPORTANT DESIGN CONSTRAINT this fix respects: this file's own module
docstring states "Gate: Toxic exposure never blocks. Every veteran gets
routed." -- unlike MedDisability_v0_1.py/BusinessOpportunity_v0_1.py,
which have a real BLOCKED early-return gate, ToxicExposure_v0_1.py
explicitly opted OUT of blocking by design (burn-pit registry enrollment,
Camp Lejeune family-member water-contamination claims, and some
presumptive-condition healthcare access do not require honorable
discharge the same way standard disability compensation does). A hard
BLOCKED early-return here would violate that stated law, not fix a bug.
Fixed instead with additive, honest disclosure: a discharge-limitation
note/flag is added for dishonorable/OTH discharge, without blocking or
removing any of the existing routing -- the veteran still gets full PACT
Act/registry/condition-specific information, now with an accurate caveat
about compensation eligibility instead of a silent, misleading omission.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "AGENTS" / "LOGIC"))

from ToxicExposure_v0_1 import ToxicExposureProfile, route_toxic_exposure  # noqa: E402


def _base_kwargs():
    return dict(
        exposure_types=["burn_pit"], era="post_9_11", locations_served=["iraq"],
        conditions=["respiratory"], camp_lejeune=False, is_lejeune_family_member=False,
        has_existing_claim=False, was_previously_denied=False, enrolled_va_healthcare=False,
        state="TX", county="Bexar",
    )


class DischargeAwarenessTest(unittest.TestCase):
    def test_dishonorable_discharge_gets_a_compensation_limitation_note(self):
        result = route_toxic_exposure(ToxicExposureProfile(discharge="dishonorable", **_base_kwargs()))
        joined_notes = " ".join(result["notes"]).lower()
        self.assertTrue(
            "dishonorable" in joined_notes or "discharge" in joined_notes,
            f"Expected a discharge-limitation note for a dishonorable-discharge veteran, got notes: {result['notes']}",
        )
        self.assertIn("discharge_limits_compensation", result["flags"])

    def test_dishonorable_discharge_still_gets_full_pact_act_routing_never_blocks(self):
        # This router's own design law: "Toxic exposure never blocks."
        result = route_toxic_exposure(ToxicExposureProfile(discharge="dishonorable", **_base_kwargs()))
        self.assertEqual(result["primary_path"], "PACT Act (2022) — Burn Pit / Airborne Hazard Presumptive Claim")
        self.assertIn("pact_act_candidate", result["flags"])
        self.assertTrue(result["key_resources"])  # registry info still present

    def test_honorable_discharge_gets_no_limitation_note_no_regression(self):
        result = route_toxic_exposure(ToxicExposureProfile(discharge="honorable", **_base_kwargs()))
        self.assertNotIn("discharge_limits_compensation", result["flags"])
        self.assertEqual(result["primary_path"], "PACT Act (2022) — Burn Pit / Airborne Hazard Presumptive Claim")

    def test_oth_discharge_also_gets_a_limitation_note(self):
        result = route_toxic_exposure(ToxicExposureProfile(discharge="other_than_honorable", **_base_kwargs()))
        self.assertIn("discharge_limits_compensation", result["flags"])

    def test_dishonorable_and_honorable_are_no_longer_byte_identical(self):
        out_h = route_toxic_exposure(ToxicExposureProfile(discharge="honorable", **_base_kwargs()))
        out_d = route_toxic_exposure(ToxicExposureProfile(discharge="dishonorable", **_base_kwargs()))
        self.assertNotEqual(out_h, out_d)


if __name__ == "__main__":
    unittest.main()
