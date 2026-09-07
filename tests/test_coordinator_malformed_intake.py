"""
tests/test_coordinator_malformed_intake.py

Independent-audit finding (2026-09-07, round 5, high):
pf_coordinator_v1.py's run_coordinator() had no defensive handling of
malformed-but-present intake fields. Specifically:

  - `domains` present but None (or any non-list) crashed
    resolve_divisions_for_domains()'s `for domain in domains:` with an
    uncaught TypeError -- and this happened BEFORE run_crisis_response()
    was ever called, so a veteran with `crisis.flagged: True` and a
    malformed `domains` field got a raw Python traceback instead of
    crisis resources. This is the worst-case instance of the "masked
    crisis path" bug shape found repeatedly in division routers in prior
    rounds -- here the veteran gets NOTHING back, not just a wrong
    answer.
  - `crisis` present but not a dict (e.g. a bare string) crashed
    run_crisis_response()'s `crisis.get("flagged", False)` the same way.
  - A missing `case_id` crashed on `intake["case_id"]` with a raw
    KeyError.

Confirmed directly against the unmodified code before this fix: all
three probes raised uncaught exceptions.

The module's own founding law is explicit that "Nothing about the
veteran... ever triggers fail-closed. Those route, with explanation" --
so the fix does NOT call _fail_closed() for any of these (that's reserved
for the three governance-integrity triggers). Instead: domains coerces to
[] if not a list (routes to gaps, same as an empty/unmapped domain list
already does), crisis coerces to {} if not a dict (same as crisis not
flagged), and case_id defaults to "UNKNOWN_CASE" if missing. Crisis
response is also now computed defensively-first and division resolution
is wrapped so a crash there cannot prevent crisis resources from
reaching the veteran -- upholding the module's own "crisis is additive,
never blocked by anything else going wrong" law for real, not just for
the happy path.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "AGENTS" / "CORE" / "PATHFINDER"))
sys.path.insert(0, str(REPO_ROOT / "tests"))

import _test_receipts_isolation  # noqa: F401,E402 — sets SQUAD_BAT_RECEIPTS_DIR before any coordinator run

from pf_coordinator_v1 import (  # noqa: E402
    run_coordinator,
    run_crisis_response,
    _FOUNDING_LAW_SHA256,
    _INTAKE_SCHEMA,
)


def _base_intake(**overrides):
    intake = {
        "schema": _INTAKE_SCHEMA,
        "founding_law_sha256": _FOUNDING_LAW_SHA256,
        "case_id": "CASE_test-1",
        "domains": ["HOUSING"],
        "crisis": {"flagged": False},
    }
    intake.update(overrides)
    return intake


class CoordinatorDoesNotCrashOnMalformedIntakeTest(unittest.TestCase):
    def test_crisis_flagged_with_none_domains_still_surfaces_crisis_resources(self):
        intake = _base_intake(
            domains=None,
            crisis={"flagged": True, "notes": "i want to kill myself"},
        )
        result = run_coordinator(intake)
        self.assertTrue(result["crisis_response"]["flagged"])
        self.assertIn("resources", result["crisis_response"])

    def test_non_list_domains_does_not_crash_and_routes_to_gaps(self):
        intake = _base_intake(domains="HOUSING")  # bare string, not a list
        result = run_coordinator(intake)
        self.assertEqual(result["synthesis"]["domain_summaries"], {})
        self.assertFalse(result["synthesis"]["quorum_met"])

    def test_missing_case_id_does_not_crash(self):
        intake = _base_intake()
        del intake["case_id"]
        result = run_coordinator(intake)
        self.assertEqual(result["case_id"], "UNKNOWN_CASE")

    def test_non_dict_crisis_does_not_crash_and_is_treated_as_not_flagged(self):
        intake = _base_intake(crisis="yes please help")
        result = run_coordinator(intake)
        self.assertFalse(result["crisis_response"]["flagged"])

    def test_run_crisis_response_directly_with_non_dict_crisis(self):
        result = run_crisis_response({"crisis": "not a dict"})
        self.assertEqual(result, {"flagged": False})

    def test_normal_case_unaffected_no_regression(self):
        intake = _base_intake(crisis={"flagged": True})
        result = run_coordinator(intake)
        self.assertTrue(result["crisis_response"]["flagged"])
        self.assertEqual(result["case_id"], "CASE_test-1")


if __name__ == "__main__":
    unittest.main()
