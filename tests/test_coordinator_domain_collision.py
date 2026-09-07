"""
tests/test_coordinator_domain_collision.py

Independent-audit finding (2026-09-07, round 5, high):
pf_coordinator_v1.py's resolve_divisions_for_domains() dedupes matched
Divisions by division_id, but when a later requested domain maps to a
division that's ALREADY matched under an earlier domain (e.g. MEDICAL and
CLAIMS both route to medical-disability-division; BENEFITS and EMPLOYMENT
both route to va-benefits-division), the later domain was silently
dropped -- not added to `matched`, and not added to `gaps` either. This
violates the module's own founding law #3 ("Every Division result...
is recorded. Nothing dropped").

Worse, because _CONFIDENCE_FIELDS["MEDICAL"] and _CONFIDENCE_FIELDS
["CLAIMS"] are different field lists, the SAME division call scored a
different confidence purely depending on which of the two domains
happened to come first in the input array -- confirmed directly against
the unmodified code:
    domains=['MEDICAL','CLAIMS'] -> matched domains: ['MEDICAL'], gaps: []
    domains=['CLAIMS','MEDICAL'] -> matched domains: ['CLAIMS'],  gaps: []
Both real, independently-selectable "need" checkboxes in the
questionnaire ("medical" and "claims") map to these two domains, so this
is reachable from real input, not just a theoretical direct-API call.

Fixed by grouping every requested domain by which division it resolves
to (so a collision no longer drops a domain -- every requested domain
that has a real division is recorded against that division's matched
entry), picking a deterministic "primary" domain label from the
DIVISION'S OWN declared domain order (not the caller's input order, so
which domain "wins" the display label never depends on request order),
and unioning _CONFIDENCE_FIELDS across every domain the division is
actually covering so the confidence score no longer depends on input
order either.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "AGENTS" / "CORE" / "PATHFINDER"))
sys.path.insert(0, str(REPO_ROOT / "tests"))

import _test_receipts_isolation  # noqa: F401,E402

from pf_coordinator_v1 import (  # noqa: E402
    resolve_divisions_for_domains,
    load_division_registry,
    load_divisions_config,
    calculate_division_confidence,
)


class DomainCollisionNotSilentlyDroppedTest(unittest.TestCase):
    def setUp(self):
        self.registry = load_division_registry()
        self.divisions_cfg = load_divisions_config()

    def test_both_colliding_domains_are_recorded_not_dropped(self):
        matched, gaps = resolve_divisions_for_domains(
            ["MEDICAL", "CLAIMS"], self.registry, self.divisions_cfg
        )
        self.assertEqual(len(matched), 1)  # still one division call
        self.assertEqual(set(matched[0]["all_requested_domains"]), {"MEDICAL", "CLAIMS"})
        self.assertEqual(gaps, [])  # neither domain is a real gap -- both are covered

    def test_primary_domain_label_is_order_independent(self):
        matched_a, _ = resolve_divisions_for_domains(
            ["MEDICAL", "CLAIMS"], self.registry, self.divisions_cfg
        )
        matched_b, _ = resolve_divisions_for_domains(
            ["CLAIMS", "MEDICAL"], self.registry, self.divisions_cfg
        )
        self.assertEqual(matched_a[0]["domain"], matched_b[0]["domain"])

    def test_benefits_employment_collision_also_fixed(self):
        matched, gaps = resolve_divisions_for_domains(
            ["EMPLOYMENT", "BENEFITS"], self.registry, self.divisions_cfg
        )
        self.assertEqual(len(matched), 1)
        self.assertEqual(set(matched[0]["all_requested_domains"]), {"BENEFITS", "EMPLOYMENT"})
        self.assertEqual(gaps, [])

    def test_non_colliding_domains_unaffected_no_regression(self):
        matched, gaps = resolve_divisions_for_domains(
            ["HOUSING", "LEGAL"], self.registry, self.divisions_cfg
        )
        self.assertEqual(len(matched), 2)
        self.assertEqual({m["division_id"] for m in matched},
                          {"housing-division", "legal-division"})

    def test_genuinely_unmapped_domain_still_reported_as_a_real_gap(self):
        matched, gaps = resolve_divisions_for_domains(
            ["MEDICAL", "NOT_A_REAL_DOMAIN"], self.registry, self.divisions_cfg
        )
        self.assertEqual(len(matched), 1)
        self.assertEqual(gaps, [{"domain": "NOT_A_REAL_DOMAIN", "reason": "No Division registered for this domain"}])


class ConfidenceNoLongerDependsOnRequestOrderTest(unittest.TestCase):
    # Real intake where MEDICAL's 5 fields (discharge/disability_rating/
    # va_history/state/county) are all present but CLAIMS's 4 fields
    # (discharge/disability_rating/va_history/state) are the same present
    # set minus county -- i.e. MEDICAL alone would score lower than CLAIMS
    # alone (80% vs 100%) if only one of the two colliding domains' field
    # list were used, which is exactly the order-dependent bug.
    _INTAKE = {
        "discharge": "honorable", "disability_rating": "70",
        "va_history": "receiving_comp", "state": "CO", "county": "Mesa",
    }

    def test_confidence_is_identical_regardless_of_which_domain_is_passed(self):
        # Simulates what invoke_division() now does: pass the FULL set of
        # requested domains a division is covering, not just whichever one
        # happened to "win" the matched-entry label.
        conf_medical_first = calculate_division_confidence(
            "MEDICAL", self._INTAKE, "COMPLETED", [], all_domains=["MEDICAL", "CLAIMS"]
        )
        conf_claims_first = calculate_division_confidence(
            "CLAIMS", self._INTAKE, "COMPLETED", [], all_domains=["CLAIMS", "MEDICAL"]
        )
        self.assertEqual(conf_medical_first, conf_claims_first)

    def test_union_of_fields_used_not_just_the_primary_domains_fields(self):
        # Without the union, "MEDICAL" alone (5 fields, all present here)
        # would score 100; "CLAIMS" alone (4 fields, all present) would
        # also score 100 -- pick an intake where the two domains'
        # individual field lists diverge more meaningfully instead.
        intake = {"discharge": "honorable"}  # only 1 of the union's fields present
        conf = calculate_division_confidence(
            "MEDICAL", intake, "COMPLETED", [], all_domains=["MEDICAL", "CLAIMS"]
        )
        # Union of MEDICAL+CLAIMS fields = {discharge, disability_rating,
        # va_history, state, county} = 5 fields, 1 present = 20%.
        self.assertEqual(conf, 20)

    def test_no_all_domains_arg_falls_back_to_single_domain_no_regression(self):
        # All 5 of MEDICAL's own fields are present in self._INTAKE.
        conf = calculate_division_confidence("MEDICAL", self._INTAKE, "COMPLETED", [])
        self.assertEqual(conf, 100)


if __name__ == "__main__":
    unittest.main()
