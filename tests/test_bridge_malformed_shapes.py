"""
tests/test_bridge_malformed_shapes.py

Independent-audit finding (2026-09-07, round 5, high):
questionnaire_intake_bridge_v1.py's build_coordinator_intake() crashed on
a malformed (present, but wrong-type) `location` or `discharge` field:

  - `location = q.get("location") or {}` only guards the FALSY case
    (None, "", missing) -- a non-dict truthy value (a bare string, a list,
    an int) passed through untouched and crashed the very next line's
    `location.get(...)` call with an uncaught AttributeError.
  - `_map_discharge()`'s `if not raw: return "unknown"` guard has the same
    gap -- a non-string, non-falsy `discharge` value (a list, a dict)
    crashed `_DISCHARGE_MAP.get(raw, "unknown")` with an uncaught
    TypeError (dict keys must be hashable).

The sibling MODULES/INTAKE_DO_NOT_GUESS module already has an in-code fix
for exactly this pattern (`p.get("location") if isinstance(p.get(
"location"), dict) else {}`), never applied here.

Confirmed directly against the unmodified code before this fix: a
location value of a bare string, a list, or an int, and a discharge value
of a list or a dict, all crashed build_coordinator_intake().
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "AGENTS" / "CORE" / "PATHFINDER"))

from questionnaire_intake_bridge_v1 import build_coordinator_intake  # noqa: E402


def _loc_state(result):
    return result.get("constraints", {}).get("location", {}).get("state")


class BridgeDoesNotCrashOnMalformedLocationTest(unittest.TestCase):
    def test_location_as_bare_string_does_not_crash(self):
        result = build_coordinator_intake({"location": "Colorado", "need": ["housing"]}, "case-1")
        self.assertIsNone(_loc_state(result))  # no usable location, but no crash either

    def test_location_as_a_list_does_not_crash(self):
        result = build_coordinator_intake({"location": ["CO", "Mesa"], "need": ["housing"]}, "case-2")
        self.assertIsNone(_loc_state(result))

    def test_location_as_an_int_does_not_crash(self):
        result = build_coordinator_intake({"location": 42, "need": ["housing"]}, "case-3")
        self.assertIsNone(_loc_state(result))

    def test_well_formed_location_still_works_no_regression(self):
        result = build_coordinator_intake(
            {"location": {"state": "CO", "county": "Mesa"}, "need": ["housing"]}, "case-4"
        )
        self.assertEqual(_loc_state(result), "CO")


class BridgeDoesNotCrashOnMalformedDischargeTest(unittest.TestCase):
    def test_discharge_as_a_list_does_not_crash(self):
        result = build_coordinator_intake({"discharge": ["oth"], "need": ["legal"]}, "case-5")
        self.assertEqual(result["discharge"], "unknown")

    def test_discharge_as_a_dict_does_not_crash(self):
        result = build_coordinator_intake({"discharge": {"x": 1}, "need": ["legal"]}, "case-6")
        self.assertEqual(result["discharge"], "unknown")

    def test_well_formed_discharge_still_works_no_regression(self):
        result = build_coordinator_intake({"discharge": "honorable", "need": ["legal"]}, "case-7")
        self.assertEqual(result["discharge"], "honorable")


if __name__ == "__main__":
    unittest.main()
