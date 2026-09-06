"""
tests/test_local_resources.py

Coverage for MODULES/_shared/local_resources.py — the shared integration
point every Division router is meant to call instead of reimplementing
its own version of "find local data for this state/county." See that
module's own docstring for the full list of design decisions this test
file verifies (verified-data-only inherited from nonprofit_search,
fail-safe/never-raises, additive crisis widening, state-scoped fuzzy
matching, source labeling).

Tests run against the real, committed CO/western_slope.json shard data
(Mesa County and neighbors) rather than synthetic fixtures, so a change
to the real data that breaks the lookup path shows up here -- the same
reasoning tests/test_questionnaire_intake_bridge.py already uses real
questionnaire values instead of the bridge's own vocabulary.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "MODULES" / "_shared"))

from local_resources import (  # noqa: E402
    _normalize_county,
    _normalize_phone_for_downstream_matching,
    _resolve_county,
    find_local_resources,
    format_local_resource_line,
)

# The exact regex pf_coordinator_v1.py's invoke_division() uses to decide
# whether a key_resources/notes line gets promoted to the coordinator-level
# "immediate_contacts" field -- kept in sync manually since it isn't
# exported. If that regex ever changes, this test file's own assertions
# are the thing that should catch a silent mismatch, not a real veteran.
import re
_COORDINATOR_PHONE_PATTERN = re.compile(
    r"(1-\d{3}-\d{3}-\d{4}|1-\d{3}-\d{4}|1-877-4AID-VET|\d{3}-\d{3}-\d{4}|988)"
)


class PhoneNormalizationTest(unittest.TestCase):
    """Found directly while wiring the Division routers: the real shard
    data is inconsistent about phone formatting -- western_slope.json uses
    "(970) 245-4156" (parens+space), front_range.json uses "719-553-1000"
    (dashes) -- and pf_coordinator_v1.py's own phone-detection regex only
    matches the dash form. Without normalizing, a real local phone number
    would silently fail to reach "immediate_contacts", the one field the
    coordinator's synthesis actually surfaces at the top level, depending
    on which region happened to write it, not on whether the data was good.
    """

    def test_parens_and_space_format_normalizes_to_dashes(self):
        self.assertEqual(_normalize_phone_for_downstream_matching("(970) 245-4156"), "970-245-4156")

    def test_already_dashed_format_is_unchanged(self):
        self.assertEqual(_normalize_phone_for_downstream_matching("970-245-4156"), "970-245-4156")

    def test_leading_country_code_is_preserved(self):
        self.assertEqual(_normalize_phone_for_downstream_matching("1 (844) 263-2778"), "1-844-263-2778")

    def test_dotted_format_normalizes_to_dashes(self):
        self.assertEqual(_normalize_phone_for_downstream_matching("970.245.4156"), "970-245-4156")

    def test_unrecognizable_shape_is_left_as_given(self):
        self.assertEqual(_normalize_phone_for_downstream_matching("call the front desk"), "call the front desk")

    def test_normalized_output_actually_matches_the_coordinator_regex(self):
        for raw in ("(970) 245-4156", "970.245.4156", "1 (844) 263-2778"):
            normalized = _normalize_phone_for_downstream_matching(raw)
            with self.subTest(raw=raw, normalized=normalized):
                self.assertTrue(_COORDINATOR_PHONE_PATTERN.search(normalized))

    def test_format_local_resource_line_uses_the_normalized_phone(self):
        line = format_local_resource_line({"name": "Example Org", "phones": ["(970) 245-4156"]})
        self.assertIn("970-245-4156", line)
        self.assertTrue(_COORDINATOR_PHONE_PATTERN.search(line))


class NormalizeCountyTest(unittest.TestCase):
    def test_strips_county_suffix(self):
        self.assertEqual(_normalize_county("Mesa County"), "mesa")

    def test_strips_co_suffix(self):
        self.assertEqual(_normalize_county("Mesa Co"), "mesa")
        self.assertEqual(_normalize_county("Mesa Co."), "mesa")

    def test_lowercases_and_strips_whitespace(self):
        self.assertEqual(_normalize_county("  MESA  "), "mesa")

    def test_empty_or_none_is_empty_string(self):
        self.assertEqual(_normalize_county(""), "")
        self.assertEqual(_normalize_county(None), "")


class ResolveCountyTest(unittest.TestCase):
    KNOWN = ["Mesa", "Garfield", "Delta", "Montrose", "San Miguel"]

    def test_exact_match(self):
        self.assertEqual(_resolve_county("Mesa", self.KNOWN), "Mesa")

    def test_exact_match_case_insensitive(self):
        self.assertEqual(_resolve_county("mesa", self.KNOWN), "Mesa")

    def test_suffix_stripped_match(self):
        self.assertEqual(_resolve_county("Mesa County", self.KNOWN), "Mesa")

    def test_typo_resolves_via_fuzzy_match(self):
        self.assertEqual(_resolve_county("Mesaa", self.KNOWN), "Mesa")

    def test_unrelated_input_resolves_to_nothing(self):
        # Must not force a match onto something that isn't actually close --
        # this is the false-positive risk fuzzy matching trades against.
        self.assertIsNone(_resolve_county("Los Angeles", self.KNOWN))

    def test_empty_input_resolves_to_nothing(self):
        self.assertIsNone(_resolve_county("", self.KNOWN))

    def test_no_known_counties_resolves_to_nothing(self):
        self.assertIsNone(_resolve_county("Mesa", []))


class FindLocalResourcesRealDataTest(unittest.TestCase):
    """Against the real, committed CO/western_slope.json shard."""

    def test_exact_county_and_tag_finds_the_real_mesa_county_vso(self):
        results = find_local_resources(
            state="CO", county="Mesa", service_tags=["claims_assistance"]
        )
        names = [r["name"] for r in results]
        self.assertIn("Mesa County Veterans Service Office", names)

    def test_every_result_is_labeled_as_local_verified(self):
        results = find_local_resources(
            state="CO", county="Mesa", service_tags=["claims_assistance"]
        )
        self.assertTrue(results)
        for r in results:
            self.assertEqual(r["source"], "local_verified")

    def test_county_with_suffix_finds_the_same_results_as_exact(self):
        exact = find_local_resources(state="CO", county="Mesa", service_tags=["claims_assistance"])
        suffixed = find_local_resources(state="CO", county="Mesa County", service_tags=["claims_assistance"])
        self.assertEqual(
            {r["provider_id"] for r in exact},
            {r["provider_id"] for r in suffixed},
        )

    def test_misspelled_county_still_resolves_via_fuzzy_match(self):
        results = find_local_resources(state="CO", county="Mesaa", service_tags=["claims_assistance"])
        names = [r["name"] for r in results]
        self.assertIn("Mesa County Veterans Service Office", names)

    def test_lowercase_state_code_is_accepted(self):
        results = find_local_resources(state="co", county="Mesa", service_tags=["claims_assistance"])
        self.assertTrue(results)

    def test_multiple_service_tags_are_merged_and_deduplicated(self):
        results = find_local_resources(
            state="CO",
            county="Mesa",
            service_tags=["claims_assistance", "benefits_navigation"],
            limit_per_tag=5,
        )
        provider_ids = [r["provider_id"] for r in results]
        self.assertEqual(len(provider_ids), len(set(provider_ids)))

    def test_crisis_widening_can_find_more_than_a_plain_search(self):
        plain = find_local_resources(state="CO", county="Mesa", service_tags=["mental_health"])
        widened = find_local_resources(
            state="CO", county="Mesa", service_tags=["mental_health"],
            crisis_or_self_harm=True, limit_per_tag=5,
        )
        self.assertGreaterEqual(len(widened), len(plain))

    def test_crisis_widening_does_not_remove_non_crisis_results(self):
        # Additive, never exclusionary: a non-mental-health tag's results
        # must be unaffected by the crisis flag.
        plain = find_local_resources(state="CO", county="Mesa", service_tags=["housing_support"])
        with_crisis_flag = find_local_resources(
            state="CO", county="Mesa", service_tags=["housing_support"], crisis_or_self_harm=True,
        )
        self.assertEqual(
            {r["provider_id"] for r in plain},
            {r["provider_id"] for r in with_crisis_flag},
        )


class FindLocalResourcesFailsSafeTest(unittest.TestCase):
    """Every one of these must return [] and never raise -- a caller
    should never have to wrap this in its own try/except."""

    def test_unknown_state_returns_empty(self):
        self.assertEqual(find_local_resources(state="ZZ", county="Nowhere", service_tags=["claims_assistance"]), [])

    def test_missing_state_returns_empty(self):
        self.assertEqual(find_local_resources(state=None, county="Mesa", service_tags=["claims_assistance"]), [])

    def test_empty_state_returns_empty(self):
        self.assertEqual(find_local_resources(state="", county="Mesa", service_tags=["claims_assistance"]), [])

    def test_no_service_tags_returns_empty(self):
        self.assertEqual(find_local_resources(state="CO", county="Mesa", service_tags=[]), [])
        self.assertEqual(find_local_resources(state="CO", county="Mesa", service_tags=None), [])

    def test_a_state_with_no_shard_data_returns_empty_not_an_error(self):
        # Every real US state has at least a skeleton file, so use a
        # clearly invalid 2-letter code to simulate "no data for this
        # state" without depending on which real states happen to be
        # unpopulated.
        self.assertEqual(find_local_resources(state="XX", county="Anywhere", service_tags=["claims_assistance"]), [])

    def test_state_with_data_but_no_matching_county_returns_empty_gracefully(self):
        results = find_local_resources(state="CO", county="Nonexistent County Name", service_tags=["claims_assistance"])
        self.assertEqual(results, [])

    def test_county_omitted_still_returns_state_level_results(self):
        # Statewide entries (e.g. the state VSO agency) have no county
        # restriction -- omitting county should still surface those,
        # not silently return nothing.
        results = find_local_resources(state="CO", service_tags=["claims_assistance"], limit_per_tag=5)
        self.assertTrue(results)


if __name__ == "__main__":
    unittest.main()
