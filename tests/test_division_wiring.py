"""
tests/test_division_wiring.py

First automated test coverage in this repo (KNOWN_GAPS.md: "No automated
test suite. ... This is the largest engineering gap"). Regression coverage
for a real bug found via a top-down review, then verified directly before
fixing: 3 of the 8 registered Divisions — VA Benefits, Business &
Opportunity, and Medical & Disability — had an empty "entry" in
config/divisions.json, so the Pathfinder coordinator's invoke_division()
always returned them SKIPPED ("Division entry not configured —
framework-only"), for every intake, regardless of what the intake actually
contained. Every veteran asking about disability claims, employment,
business/SBA programs, or medical/healthcare enrollment got nothing from
these three Divisions, even though real, working router code already
existed for all three.

Two of the three also had a second, independent bug once entry was fixed:
business_opportunity_router.py and med_disability_router.py only exposed
route()/route_to_dict(), not the run() name invoke_division() actually
requires (confirmed by reading every other wired Division's router — all
five expose run()). Verified directly: even after pointing divisions.json
at these two files, the coordinator's hasattr(mod, "run") check still
failed and both Divisions kept coming back SKIPPED. Fixed by adding
`run = route` to both.

Run with: python3 -m unittest discover -s tests -v
No third-party dependencies — this project has none, so tests stay in the
standard library (unittest) rather than introducing pytest as the first
external dependency this repo has ever had.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "AGENTS" / "CORE" / "PATHFINDER"))

import pf_coordinator_v1 as coordinator  # noqa: E402


PREVIOUSLY_UNWIRED = {
    "va-benefits-division": {
        "src_dir": "MODULES/VA_BENEFITS/src",
        "module": "va_benefits_router",
        "domain": "BENEFITS",
    },
    "business-opportunity-division": {
        "src_dir": "MODULES/BUSINESS_OPPORTUNITY/src",
        "module": "business_opportunity_router",
        "domain": "BUSINESS",
    },
    "medical-disability-division": {
        "src_dir": "MODULES/MEDICAL_DISABILITY/src",
        "module": "med_disability_router",
        "domain": "MEDICAL",
    },
}


def _load_router_module(rel_src_dir: str, module_name: str):
    import importlib.util

    src_dir = REPO_ROOT / rel_src_dir
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    spec = importlib.util.spec_from_file_location(module_name, src_dir / f"{module_name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class DivisionsConfigWiringTest(unittest.TestCase):
    """(the fix) config/divisions.json actually points at real files."""

    def setUp(self):
        with open(REPO_ROOT / "config" / "divisions.json", encoding="utf-8") as f:
            self.divisions_cfg = json.load(f)["divisions"]

    def test_all_three_previously_unwired_divisions_now_have_an_entry(self):
        for division_id in PREVIOUSLY_UNWIRED:
            entry = self.divisions_cfg[division_id]["entry"]
            self.assertTrue(entry, f"{division_id} still has an empty entry")

    def test_every_configured_entry_path_actually_exists_on_disk(self):
        # Guards against a config pointing at a file that was moved/renamed —
        # invoke_division() only reports this as a silent SKIPPED, never an error.
        for division_id, cfg in self.divisions_cfg.items():
            entry = cfg.get("entry", "")
            if not entry:
                continue
            self.assertTrue(
                (REPO_ROOT / entry).exists(),
                f"{division_id}'s configured entry does not exist: {entry}",
            )


class RouterRunEntrypointTest(unittest.TestCase):
    """(the fix) every configured Division router exposes run(), matching
    what invoke_division() actually calls — not just route()/route_to_dict()."""

    def test_all_configured_routers_expose_a_callable_run(self):
        with open(REPO_ROOT / "config" / "divisions.json", encoding="utf-8") as f:
            divisions_cfg = json.load(f)["divisions"]
        for division_id, cfg in divisions_cfg.items():
            entry = cfg.get("entry", "")
            if not entry:
                continue
            import importlib.util

            spec = importlib.util.spec_from_file_location(division_id, REPO_ROOT / entry)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            spec.loader.exec_module(mod)
            self.assertTrue(
                callable(getattr(mod, "run", None)),
                f"{division_id} ({entry}) has no callable run() — invoke_division() will always SKIP it",
            )


class UnwiredDivisionRouterDirectTest(unittest.TestCase):
    """Each previously-unwired router actually produces a real routing
    result when called directly, not just an importable stub."""

    def test_va_benefits_router_completes_with_a_valid_payload(self):
        mod = _load_router_module("MODULES/VA_BENEFITS/src", "va_benefits_router")
        result = mod.run({
            "discharge": "honorable",
            "era": "post_9_11",
            "is_transitioning": True,
            "disability_rating": 30,
            "state": "CO",
            "county": "Mesa",
        })
        self.assertEqual(result.status, "OK")
        self.assertTrue(result.primary_path)

    def test_business_opportunity_router_completes_with_a_valid_payload(self):
        mod = _load_router_module("MODULES/BUSINESS_OPPORTUNITY/src", "business_opportunity_router")
        result = mod.run({"discharge": "honorable", "state": "CO"})
        self.assertEqual(result.status, "OK")
        self.assertTrue(result.primary_path)

    def test_medical_disability_router_completes_with_a_valid_payload(self):
        mod = _load_router_module("MODULES/MEDICAL_DISABILITY/src", "med_disability_router")
        result = mod.run({
            "discharge": "honorable",
            "va_status": "has_rating",
            "disability_rating": 30,
        })
        self.assertEqual(result.status, "OK")
        self.assertTrue(result.primary_path)

    def test_medical_disability_router_needs_input_on_an_invalid_enum_value_not_a_crash(self):
        # va_status has a fixed enum (module.json / _validate) — a plausible-
        # looking but invalid value like "enrolled" must NEEDS_INPUT cleanly,
        # not raise or silently misroute.
        mod = _load_router_module("MODULES/MEDICAL_DISABILITY/src", "med_disability_router")
        result = mod.run({"discharge": "honorable", "va_status": "enrolled"})
        self.assertEqual(result.status, "NEEDS_INPUT")
        self.assertTrue(result.questions)


class CoordinatorEndToEndWiringTest(unittest.TestCase):
    """(the fix) the actual regression test: run the real Pathfinder
    coordinator end to end and confirm all three previously-broken domains
    now come back COMPLETED, not SKIPPED, for a complete, valid intake."""

    def _base_intake(self, domains):
        return {
            "schema": "squad-bat.coordinator-intake.v1",
            "case_id": "CASE_TEST_DIVISION_WIRING",
            "session_ref": "SESSION_test",
            "timestamp": "2026-09-05T00:00:00Z",
            "founding_law_sha256": coordinator._FOUNDING_LAW_SHA256,
            "stage": "STABILIZE",
            "crisis": {"flagged": False, "type": "NONE"},
            "domains": domains,
            "discharge": "honorable",
            "era": "post_9_11",
            "disability_rating": 30,
            "state": "CO",
            "county": "Mesa",
            "va_status": "has_rating",
        }

    def test_benefits_business_and_medical_domains_all_complete_not_skip(self):
        intake = self._base_intake(["BENEFITS", "BUSINESS", "MEDICAL"])
        result = coordinator.run_coordinator(intake)
        by_domain = {r["domain"]: r for r in result["division_results"]}

        for domain, division_id in [
            ("BENEFITS", "va-benefits-division"),
            ("BUSINESS", "business-opportunity-division"),
            ("MEDICAL", "medical-disability-division"),
        ]:
            self.assertIn(domain, by_domain, f"{domain} produced no division result at all")
            r = by_domain[domain]
            self.assertEqual(
                r["division_id"], division_id,
                f"{domain} routed to the wrong division",
            )
            self.assertEqual(
                r["status"], "COMPLETED",
                f"{domain} ({division_id}) was not COMPLETED — got {r['status']}: {r.get('result_summary')}",
            )

        self.assertEqual(result["coordinator_status"], "WITHIN_TOLERANCE")
        self.assertTrue(result["synthesis"]["quorum_met"])


if __name__ == "__main__":
    unittest.main()
