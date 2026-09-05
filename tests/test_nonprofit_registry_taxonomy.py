"""
tests/test_nonprofit_registry_taxonomy.py

Coverage for two related fixes to MODULES/RESOURCES_NONPROFITS:

1. THE TAXONOMY MISMATCH BUG. load_registry() — the module's own sanctioned
   loading path — rejected records from EVERY ONE of the 56 real shard files
   in DATA/ with "service tag not in taxonomy". A scan of all real provider
   records found the mismatch was systemic, not a typo: every state file
   uses primary_care/mental_health/specialty_care (used by full-service VAMCs
   that don't itemize), and the CO/WA regional shards additionally use
   mst_counseling, bereavement, substance_use, and 16 other tags (used by
   specialized providers like Vet Centers and military family support
   offices) — none of which were in GOVERNANCE/auernyx.nonprofit.scope.json's
   allowed_service_tags. The module could not load any real data as built.

   Fixed by expanding allowed_service_tags (in both the governance file and
   the JSON schema's ServiceTag enum) to include every tag actually used in
   the real data, verified against the specific provider records using each
   one (see the tag_hierarchy comment in the governance file) rather than
   guessed.

2. THE CRISIS-WIDENING FEATURE. The mismatched tags turned out to fall into a
   real two-level structure: e.g. a VAMC tags itself broadly with
   "mental_health", while a specialized provider (a Vet Center) itemizes the
   specific sub-type ("mst_counseling", "clinical_therapy_referral",
   "bereavement", "substance_use"). Per design: a routine search for a
   specific sub-type should match only providers offering that specific
   thing, but when intake has flagged a health/welfare or self-harm concern,
   the search must widen to the whole mental_health branch — a crisis search
   must never come back narrower than a routine one, and a general VAMC
   should not be silently excluded just because it didn't itemize.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = REPO_ROOT / "MODULES" / "RESOURCES_NONPROFITS"
sys.path.insert(0, str(MODULE_ROOT / "src"))

import nonprofit_search as ns  # noqa: E402
import location_resolver as lr  # noqa: E402


def _write_temp_shard(providers) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump({"providers": providers}, f)
    f.close()
    return f.name


class RealDataLoadsCleanlyTest(unittest.TestCase):
    """Regression: load_registry() must succeed against every real shard."""

    def test_every_shard_under_data_loads_without_error(self):
        shard_files = sorted(str(p) for p in (MODULE_ROOT / "DATA").rglob("*.json"))
        self.assertGreater(len(shard_files), 0, "expected real shard files under DATA/")
        records = ns.load_registry(shard_files)
        self.assertGreater(len(records), 0)

    def test_previously_rejected_tags_are_now_accepted_by_the_taxonomy(self):
        # These were the exact tags that raised "service tag not in
        # taxonomy" before the fix. Uses a synthetic record (not the real AK
        # shard) so this test doesn't depend on which real providers happen
        # to be verified vs. pending re-verification on any given day (see
        # the unverified-contact-exclusion fix, which now legitimately
        # excludes some of these tags' original real-world examples).
        for tag in ("primary_care", "mental_health", "specialty_care", "mst_counseling"):
            with self.subTest(tag=tag):
                path = _write_temp_shard([{
                    "provider_id": "TEST/synthetic-1",
                    "name": "Synthetic Test Provider",
                    "services": [tag],
                }])
                records = ns.load_registry([path])
                self.assertEqual(len(records), 1)
                self.assertIn(tag, records[0]["services"])


class CrisisWideningTest(unittest.TestCase):
    def setUp(self):
        paths = lr.resolve_shards(state="AK")
        self.records = ns.load_registry(paths)

    def test_routine_search_for_a_specific_subtype_matches_only_that_subtype(self):
        results = ns.search(self.records, service="mst_counseling")
        names = {r["name"] for r in results}
        self.assertEqual(names, {"Alaska Vet Centers"})

    def test_crisis_search_for_the_same_subtype_widens_to_the_whole_branch(self):
        results = ns.search(self.records, service="mst_counseling", crisis_or_self_harm=True)
        names = {r["name"] for r in results}
        # Widens to every other mental_health-branch provider in the real
        # AK data, not just the one that literally said "mst_counseling".
        # ("Alaska VA Healthcare System" also carries the parent
        # "mental_health" tag but is correctly excluded here by the
        # unverified-contact-info fix -- see the dedicated synthetic-data
        # test below for the "widens to a parent-only-tagged provider"
        # guarantee on its own, independent of any one real record's
        # verification status on a given day.)
        self.assertIn("Alaska Vet Centers", names)
        self.assertIn("Service Women's Action Network (SWAN)", names)

    def test_crisis_widening_pulls_in_a_provider_tagged_only_with_the_parent(self):
        # Synthetic data, independent of any real record's verification
        # status: a provider tagged only with the broad parent "mental_health"
        # (the way a full-service VAMC tags itself, per real data) must be
        # pulled in by a crisis-widened search for a specific child tag.
        path = _write_temp_shard([{
            "provider_id": "TEST/broad-1",
            "name": "Synthetic General Medical Center",
            "services": ["mental_health"],
        }])
        records = ns.load_registry([path])

        routine = {r["name"] for r in ns.search(records, service="mst_counseling")}
        crisis = {r["name"] for r in ns.search(records, service="mst_counseling", crisis_or_self_harm=True)}

        self.assertNotIn("Synthetic General Medical Center", routine)
        self.assertIn("Synthetic General Medical Center", crisis)

    def test_crisis_widened_results_are_a_superset_of_routine_results(self):
        routine = {r["name"] for r in ns.search(self.records, service="mst_counseling")}
        crisis = {r["name"] for r in ns.search(
            self.records, service="mst_counseling", crisis_or_self_harm=True
        )}
        self.assertTrue(routine.issubset(crisis))

    def test_crisis_flag_on_a_non_mental_health_tag_does_not_widen(self):
        # Scoped narrowly per design -- claims_assistance is not in any
        # crisis_widened_branches entry, so the flag must be a no-op here.
        routine = [r["name"] for r in ns.search(self.records, service="claims_assistance")]
        crisis = [r["name"] for r in ns.search(
            self.records, service="claims_assistance", crisis_or_self_harm=True
        )]
        self.assertEqual(routine, crisis)

    def test_crisis_flag_with_no_service_filter_is_a_no_op(self):
        routine = [r["name"] for r in ns.search(self.records)]
        crisis = [r["name"] for r in ns.search(self.records, crisis_or_self_harm=True)]
        self.assertEqual(routine, crisis)

    def test_searching_the_parent_tag_directly_under_crisis_also_widens(self):
        # Querying "mental_health" itself (the parent) under a crisis flag
        # should also pull in every child-tagged provider in the real data
        # ("Alaska Vet Centers" carries mst_counseling/clinical_therapy_
        # referral/mental_health_peer_support, all children of this branch).
        results = ns.search(self.records, service="mental_health", crisis_or_self_harm=True)
        names = {r["name"] for r in results}
        self.assertIn("Alaska Vet Centers", names)


if __name__ == "__main__":
    unittest.main()
