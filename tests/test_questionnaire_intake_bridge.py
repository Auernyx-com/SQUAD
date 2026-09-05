"""
tests/test_questionnaire_intake_bridge.py

Coverage for AGENTS/CORE/PATHFINDER/questionnaire_intake_bridge_v1.py — the
translator between the real wyerd-squad questionnaire's `intake` object and
a valid coordinator intake. See that module's own docstring for the full
list of real vocabulary mismatches this bridge exists to fix (discharge,
era, disability_rating, income, housing_status, need->domains, urgency).

Every test here uses the *actual* value strings the questionnaire sends
(tool/index.html), not the coordinator's own vocabulary — that's the whole
point: proving the bridge correctly translates real frontend output, not
values already in the shape the coordinator wants.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import _test_receipts_isolation  # noqa: F401,E402 — sets SQUAD_BAT_RECEIPTS_DIR before any coordinator run

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "AGENTS" / "CORE" / "PATHFINDER"))

import questionnaire_intake_bridge_v1 as bridge  # noqa: E402
import pf_coordinator_v1 as coordinator  # noqa: E402


class DischargeMappingTest(unittest.TestCase):
    def test_clean_mappings(self):
        self.assertEqual(bridge._map_discharge("honorable"), "honorable")
        self.assertEqual(bridge._map_discharge("general_uhc"), "general")
        self.assertEqual(bridge._map_discharge("oth"), "other_than_honorable")
        self.assertEqual(bridge._map_discharge("dishonorable"), "dishonorable")
        self.assertEqual(bridge._map_discharge("unknown"), "unknown")

    def test_missing_or_empty_defaults_to_unknown(self):
        self.assertEqual(bridge._map_discharge(None), "unknown")
        self.assertEqual(bridge._map_discharge(""), "unknown")

    def test_medical_is_passed_through_unchanged_on_purpose(self):
        # Deliberately NOT remapped: pf_coordinator_v1's own
        # MEDICAL_RETIREMENT_VA_DISPUTE edge case checks discharge=="medical"
        # directly. Remapping it here would break that check.
        self.assertEqual(bridge._map_discharge("medical"), "medical")


class EraMappingTest(unittest.TestCase):
    def test_post_911_underscore_drift_is_fixed(self):
        self.assertEqual(bridge._map_era(["post_911"]), "post_9_11")

    def test_exact_matches_pass_through(self):
        self.assertEqual(bridge._map_era(["gulf_war"]), "gulf_war")
        self.assertEqual(bridge._map_era(["vietnam"]), "vietnam")
        self.assertEqual(bridge._map_era(["korea"]), "korea")

    def test_multi_select_picks_the_highest_priority_present_value(self):
        # post_911 (index 0 in priority) must win over vietnam even though
        # vietnam appears first in the input list.
        self.assertEqual(bridge._map_era(["vietnam", "post_911"]), "post_9_11")

    def test_unmappable_era_falls_back_to_unknown_not_a_guess(self):
        self.assertEqual(bridge._map_era(["wwii"]), "unknown")
        self.assertEqual(bridge._map_era([]), "unknown")
        self.assertEqual(bridge._map_era(None), "unknown")

    def test_transitioning_sets_a_flag_not_an_era_value(self):
        self.assertTrue(bridge._era_includes_transitioning(["transitioning"]))
        self.assertFalse(bridge._era_includes_transitioning(["vietnam"]))
        # "transitioning" alone has no VALID_ERA equivalent — era falls back
        # to unknown, but the flag is still set correctly.
        self.assertEqual(bridge._map_era(["transitioning"]), "unknown")


class DisabilityRatingMappingTest(unittest.TestCase):
    """The router logic gates a real recommendation on `rating >= 10`
    (AGENTS/LOGIC/VaBenefits_v0_1.py). Every mapped value here must never
    cross that threshold falsely for the selected range."""

    def test_ranges_map_to_their_conservative_lower_bound(self):
        self.assertEqual(bridge._map_disability_rating("0_20"), 0)
        self.assertEqual(bridge._map_disability_rating("30_60"), 30)
        self.assertEqual(bridge._map_disability_rating("70_90"), 70)

    def test_0_20_never_falsely_crosses_the_10_percent_threshold(self):
        # This is the actual property that matters, not just the number 0.
        self.assertLess(bridge._map_disability_rating("0_20"), 10)

    def test_exact_values(self):
        self.assertEqual(bridge._map_disability_rating("none"), 0)
        self.assertEqual(bridge._map_disability_rating("100"), 100)
        self.assertEqual(bridge._map_disability_rating("tdiu"), 100)
        self.assertEqual(bridge._map_disability_rating("denied"), 0)

    def test_pending_is_none_not_zero(self):
        # "pending" means genuinely unknown, not a confirmed 0% rating —
        # these are different facts and must not be conflated.
        self.assertIsNone(bridge._map_disability_rating("pending"))

    def test_missing_is_none(self):
        self.assertIsNone(bridge._map_disability_rating(None))


class IncomeMappingTest(unittest.TestCase):
    """The router logic gates a pension recommendation on
    `income_monthly < 2000`. Every mapped value must never claim the
    veteran is below that threshold when they might not be."""

    def test_ranges_map_to_their_conservative_upper_bound(self):
        self.assertEqual(bridge._map_income("under_500"), 499)
        self.assertEqual(bridge._map_income("500_1000"), 1000)
        self.assertEqual(bridge._map_income("1000_2000"), 2000)

    def test_1000_2000_never_falsely_claims_below_the_2000_threshold(self):
        self.assertGreaterEqual(bridge._map_income("1000_2000"), 2000)

    def test_over_2000_clears_the_threshold(self):
        self.assertGreaterEqual(bridge._map_income("over_2000"), 2000)

    def test_none_bucket_is_zero(self):
        self.assertEqual(bridge._map_income("none"), 0)


class HousingStatusMappingTest(unittest.TestCase):
    def test_mappings(self):
        self.assertEqual(bridge._map_housing_status("unsheltered"), "unhoused")
        self.assertEqual(bridge._map_housing_status("car"), "unhoused")
        self.assertEqual(bridge._map_housing_status("shelter"), "unhoused")
        self.assertEqual(bridge._map_housing_status("couch"), "unstable")
        self.assertEqual(bridge._map_housing_status("unstable_housed"), "at_risk")
        self.assertEqual(bridge._map_housing_status("stable"), "stable")

    def test_missing_is_unknown(self):
        self.assertEqual(bridge._map_housing_status(None), "unknown")


class VaStatusMappingTest(unittest.TestCase):
    def test_never_and_contacted_only_map_to_not_enrolled(self):
        self.assertEqual(bridge._map_va_status("never", None), "not_enrolled")
        self.assertEqual(bridge._map_va_status("contacted_only", None), "not_enrolled")

    def test_healthcare_only_and_claim_active_map_to_enrolled_no_rating(self):
        self.assertEqual(bridge._map_va_status("healthcare_only", None), "enrolled_no_rating")
        self.assertEqual(bridge._map_va_status("claim_active", None), "enrolled_no_rating")

    def test_receiving_comp_cross_references_disability_rating(self):
        self.assertEqual(bridge._map_va_status("receiving_comp", "30_60"), "has_rating")
        self.assertEqual(bridge._map_va_status("receiving_comp", "100"), "100_percent_PT")
        self.assertEqual(bridge._map_va_status("receiving_comp", "tdiu"), "100_percent_PT")

    def test_missing_defaults_to_not_enrolled(self):
        self.assertEqual(bridge._map_va_status(None, None), "not_enrolled")


class NeedToDomainMappingTest(unittest.TestCase):
    def test_maps_each_need_to_its_domain(self):
        domains = bridge._map_needs_to_domains(["housing", "claims", "benefits"])
        self.assertEqual(domains, ["HOUSING", "CLAIMS", "BENEFITS"])

    def test_crisis_is_not_included_as_a_domain(self):
        domains = bridge._map_needs_to_domains(["housing", "crisis"])
        self.assertEqual(domains, ["HOUSING"])
        self.assertTrue(bridge._needs_flag_crisis(["housing", "crisis"]))

    def test_crisis_only_flags_crisis_and_produces_no_domains(self):
        self.assertEqual(bridge._map_needs_to_domains(["crisis"]), [])
        self.assertTrue(bridge._needs_flag_crisis(["crisis"]))


class LocationNormalizationTest(unittest.TestCase):
    def test_lowercase_two_letter_state_is_uppercased(self):
        self.assertEqual(bridge._normalize_state("co"), "CO")

    def test_full_state_name_is_rejected_not_guessed(self):
        # "Colorado" is not a valid 2-letter code — must not silently guess
        # an abbreviation; empty string signals "we don't have a usable state".
        self.assertEqual(bridge._normalize_state("Colorado"), "")

    def test_missing_state_is_empty(self):
        self.assertEqual(bridge._normalize_state(None), "")
        self.assertEqual(bridge._normalize_state(""), "")


class BuildCoordinatorIntakeEndToEndTest(unittest.TestCase):
    """The real regression tests: build an intake from real questionnaire
    values and run it through the actual coordinator, not a stub."""

    def test_oth_veteran_low_rating_unstable_housing_urgent_completes_across_domains(self):
        # The exact population Fail-Closed Design Law #4 names — verifies
        # they get real routing, not a validation failure.
        questionnaire_intake = {
            "service_status": "veteran",
            "discharge": "oth",
            "era": ["post_911"],
            "need": ["housing", "claims", "benefits"],
            "housing_status": "unstable_housed",
            "va_history": "never",
            "disability_rating": "0_20",
            "income": "under_500",
            "location": {"state": "co", "county": "Mesa"},
            "urgency": "tonight",
        }
        intake = bridge.build_coordinator_intake(questionnaire_intake, case_id="CASE_TEST_OTH")
        result = coordinator.run_coordinator(intake)
        by_domain = {r["domain"]: r["status"] for r in result["division_results"]}

        self.assertEqual(by_domain.get("HOUSING"), "COMPLETED")
        self.assertEqual(by_domain.get("BENEFITS"), "COMPLETED")
        self.assertEqual(by_domain.get("CLAIMS"), "COMPLETED")
        self.assertEqual(result["coordinator_status"], "WITHIN_TOLERANCE")

    def test_crisis_only_need_flags_crisis_and_surfaces_a_domain_gap_not_a_crash(self):
        questionnaire_intake = {
            "service_status": "veteran",
            "discharge": "honorable",
            "need": ["crisis"],
            "location": {"state": "CO", "county": "Mesa"},
            "urgency": "tonight",
        }
        intake = bridge.build_coordinator_intake(questionnaire_intake, case_id="CASE_TEST_CRISIS")
        self.assertTrue(intake["crisis"]["flagged"])
        result = coordinator.run_coordinator(intake)
        self.assertTrue(result["crisis_response"]["flagged"])
        self.assertTrue(any(g["domain"] == "CRISIS" for g in result["gaps"]))

    def test_medical_discharge_with_full_disability_rating_maps_va_status_correctly(self):
        questionnaire_intake = {
            "service_status": "veteran",
            "discharge": "medical",
            "need": ["medical"],
            "va_history": "receiving_comp",
            "disability_rating": "100",
            "location": {"state": "CO", "county": "Mesa"},
        }
        intake = bridge.build_coordinator_intake(questionnaire_intake, case_id="CASE_TEST_MED100")
        self.assertEqual(intake["va_status"], "100_percent_PT")
        # discharge=="medical" is intentionally outside VALID_DISCHARGE —
        # the router should ask a clarifying question, not crash or silently
        # misroute. This pins that documented, intentional behavior.
        result = coordinator.run_coordinator(intake)
        med_result = next(r for r in result["division_results"] if r["domain"] == "MEDICAL")
        self.assertEqual(med_result["status"], "NEEDS_INPUT")

    def test_business_only_minimal_intake_completes(self):
        questionnaire_intake = {
            "service_status": "veteran",
            "discharge": "honorable",
            "need": ["business"],
            "location": {"state": "CO", "county": "Mesa"},
        }
        intake = bridge.build_coordinator_intake(questionnaire_intake, case_id="CASE_TEST_BIZ")
        result = coordinator.run_coordinator(intake)
        biz_result = next(r for r in result["division_results"] if r["domain"] == "BUSINESS")
        self.assertEqual(biz_result["status"], "COMPLETED")

    def test_garbage_state_input_does_not_crash_and_surfaces_no_location_edge_case(self):
        questionnaire_intake = {
            "service_status": "veteran",
            "discharge": "honorable",
            "need": ["benefits"],
            "location": {"state": "Colorado", "county": ""},
        }
        intake = bridge.build_coordinator_intake(questionnaire_intake, case_id="CASE_TEST_BADSTATE")
        self.assertEqual(intake["state"], "")
        result = coordinator.run_coordinator(intake)
        self.assertIn("NO_LOCATION", [e["id"] for e in result["edge_cases"]])

    def test_empty_questionnaire_intake_does_not_crash(self):
        # Everything omitted — the bridge must degrade to safe defaults, not raise.
        intake = bridge.build_coordinator_intake({}, case_id="CASE_TEST_EMPTY")
        result = coordinator.run_coordinator(intake)
        self.assertIn(result["coordinator_status"], ("CONTROLLED", "WITHIN_TOLERANCE"))

    def test_receipt_ref_is_set_even_when_the_receipt_lives_outside_repo_root(self):
        # (the fix) run_coordinator's receipt_ref computation used
        # receipt_path.relative_to(REPO_ROOT) unconditionally — found by
        # this test suite's own receipts-isolation setup (which points
        # SQUAD_BAT_RECEIPTS_DIR at a tmp directory outside the repo,
        # verified as the actual test-process environment here) raising
        # ValueError on every single coordinator run. Fixed to fall back to
        # the absolute path rather than crash the whole run over a
        # bookkeeping field.
        intake = bridge.build_coordinator_intake({}, case_id="CASE_TEST_RECEIPT_REF")
        result = coordinator.run_coordinator(intake)
        self.assertTrue(result["receipt_ref"])


if __name__ == "__main__":
    unittest.main()
