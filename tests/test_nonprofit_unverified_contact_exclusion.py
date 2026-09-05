"""
tests/test_nonprofit_unverified_contact_exclusion.py

MODULES/_shared/contacts.py states the policy in writing: "Any number not
positively verified is marked VERIFY_BEFORE_PRODUCTION and must not be
surfaced to a veteran." The real curated data in MODULES/RESOURCES_NONPROFITS
/DATA follows this convention -- 189 of 266 real provider records (as of
2026-09-05) carry a "verify_before_production" list flagging specific
unconfirmed details, 7 of them on records with a populated phone number,
including a domestic-violence 24hr crisis line.

BUG: "verify_before_production" was never added to allowed_output_fields, so
_sanitize_and_validate_record()'s field-stripping step silently DROPPED the
marker while keeping every other field -- including the still-unverified
phone number the marker was warning about. tools/qa/validate_nonprofit_
registry.py (a separate, manually-run QA script) already flags this as a
finding, but load_registry() -- the actual runtime path a real search call
uses -- enforced nothing at all.

Confirmed with a direct probe against the pre-fix code: loading CO's
front_range shard returned "TESSA — Colorado Springs" (a DV shelter/advocacy
org) with its phone number 719-633-3819 intact, with zero indication in the
output that the number was marked "verify current 24hr crisis line" and had
not been confirmed.

FIX: _sanitize_and_validate_record() now excludes (returns None for) any
record carrying a non-empty verify_before_production list, and
load_registry() skips None results. This does NOT raise and abort the whole
load the way a blocked-field-key violation does -- unlike a malformed file,
an org's phone number needing a follow-up call is routine, ongoing data
curation, so one pending verification must not take an entire state's
registry down. It just means that org doesn't appear in results until its
info is confirmed, the same as if it had closed.
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


class UnverifiedContactExclusionTest(unittest.TestCase):
    def test_record_with_unresolved_verify_before_production_is_excluded(self):
        path = _write_temp_shard([{
            "provider_id": "TEST/unverified-1",
            "name": "Unverified Org",
            "services": ["resource_referral"],
            "phones": ["555-000-0000"],
            "verify_before_production": ["555-000-0000 — verify current main line"],
        }])
        records = ns.load_registry([path])
        self.assertEqual(records, [])

    def test_verified_record_in_the_same_shard_still_loads(self):
        path = _write_temp_shard([
            {
                "provider_id": "TEST/unverified-1",
                "name": "Unverified Org",
                "services": ["resource_referral"],
                "verify_before_production": ["555-000-0000 — verify current main line"],
            },
            {
                "provider_id": "TEST/verified-1",
                "name": "Verified Org",
                "services": ["resource_referral"],
            },
        ])
        records = ns.load_registry([path])
        names = {r["name"] for r in records}
        # Exclusion is per-record -- one pending verification must not take
        # down the rest of the same shard.
        self.assertEqual(names, {"Verified Org"})

    def test_empty_verify_before_production_list_does_not_exclude(self):
        # An empty list is the "nothing currently flagged" state, not an
        # active warning -- must not be treated as unresolved.
        path = _write_temp_shard([{
            "provider_id": "TEST/empty-marker-1",
            "name": "Org With Empty Marker",
            "services": ["resource_referral"],
            "verify_before_production": [],
        }])
        records = ns.load_registry([path])
        self.assertEqual(len(records), 1)

    def test_real_dv_crisis_line_org_is_excluded_from_real_data(self):
        # TESSA — Colorado Springs carries a populated phone number
        # (719-633-3819, described in the source data as a "24hr crisis
        # line") alongside an unresolved verify_before_production entry for
        # that exact number. Confirmed present in real DATA/US/CO/
        # front_range.json as of 2026-09-05.
        paths = lr.resolve_shards(state="CO", region="front_range")
        records = ns.load_registry(paths)
        names = {r["name"] for r in records}
        self.assertNotIn("TESSA — Colorado Springs", names)

    def test_no_verify_before_production_key_leaks_into_any_output_record(self):
        shard_files = sorted(str(p) for p in (MODULE_ROOT / "DATA").rglob("*.json"))
        records = ns.load_registry(shard_files)
        leaked = [r for r in records if "verify_before_production" in r]
        self.assertEqual(leaked, [])


if __name__ == "__main__":
    unittest.main()
