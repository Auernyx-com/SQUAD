"""
tests/test_branch_emergency_aliases.py

Regression coverage for a silent branch-resource wiring bug in
MODULES/_shared/contacts.py's BRANCH_EMERGENCY lookup, used by
Housing_v0_1.py and Legal_v0_1.py.

Found by cross-referencing BRANCH_EMERGENCY's dict keys against the real
branch option values sent by the live questionnaire
(wyerd-squad/tool/index.html): the questionnaire sends 'marines', 'army_ng',
and 'air_ng', but BRANCH_EMERGENCY was keyed 'marine_corps',
'army_national_guard', and 'air_national_guard'. Both Housing_v0_1.py and
Legal_v0_1.py normalized the raw branch value (lowercase + underscore) and
indexed BRANCH_EMERGENCY directly with no alias step, so the mismatch was
silent: a Marine Corps or Guard veteran got status="OK" with zero
branch-specific emergency resources (Semper Fi & America's Fund, AER, the
State National Guard Family Assistance Center, etc.) even though the
resources existed in the dict and the routing code was written to surface
them.

Confirmed with a direct probe against the pre-fix code: a
VetHousingProfile(housing_status="unhoused", branch="marines") never set the
"branch_emergency_resources_available" flag and never mentioned "Semper Fi"
in its notes, while the same profile with branch="marine_corps" (the
dict's literal key) did.

Fixed with a single BRANCH_ALIASES map + get_branch_emergency() helper in
contacts.py, used by every caller — so the fix reaches Housing and Legal
(and any future caller) from one place instead of duplicated lookup logic.

Reserve-component values ('army_reserve', 'navy_reserve', 'af_reserve',
'usmc_reserve', 'uscg_reserve') are a known, disclosed, still-open gap —
BRANCH_EMERGENCY has no distinct entries for any Reserve component, so they
intentionally remain unmapped rather than guessed at. See the comment above
BRANCH_ALIASES in contacts.py.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "MODULES" / "_shared"))
sys.path.insert(0, str(REPO_ROOT / "AGENTS" / "LOGIC"))

import contacts  # noqa: E402
from Housing_v0_1 import VetHousingProfile, route_housing  # noqa: E402
from Legal_v0_1 import VetLegalProfile, route_legal  # noqa: E402


class GetBranchEmergencyAliasTest(unittest.TestCase):
    def test_marines_aliases_to_marine_corps(self):
        self.assertEqual(
            contacts.get_branch_emergency("marines"),
            contacts.BRANCH_EMERGENCY["marine_corps"],
        )

    def test_army_ng_aliases_to_army_national_guard(self):
        self.assertEqual(
            contacts.get_branch_emergency("army_ng"),
            contacts.BRANCH_EMERGENCY["army_national_guard"],
        )

    def test_air_ng_aliases_to_air_national_guard(self):
        self.assertEqual(
            contacts.get_branch_emergency("air_ng"),
            contacts.BRANCH_EMERGENCY["air_national_guard"],
        )

    def test_literal_dict_keys_still_work_directly(self):
        for branch in ("army", "navy", "air_force", "coast_guard", "marine_corps"):
            with self.subTest(branch=branch):
                self.assertEqual(
                    contacts.get_branch_emergency(branch),
                    contacts.BRANCH_EMERGENCY[branch],
                )

    def test_unknown_branch_returns_empty_list_not_an_error(self):
        self.assertEqual(contacts.get_branch_emergency("space_force"), [])
        self.assertEqual(contacts.get_branch_emergency(""), [])
        self.assertEqual(contacts.get_branch_emergency(None), [])

    def test_reserve_components_are_a_disclosed_gap_not_silently_aliased(self):
        # Documented known gap — must not be guessed into an active-duty org
        # without verifying reservist eligibility first.
        for branch in (
            "army_reserve", "navy_reserve", "af_reserve",
            "usmc_reserve", "uscg_reserve",
        ):
            with self.subTest(branch=branch):
                self.assertEqual(contacts.get_branch_emergency(branch), [])


class HousingBranchEmergencyRegressionTest(unittest.TestCase):
    def test_marine_corps_veteran_gets_branch_resources_when_unhoused(self):
        profile = VetHousingProfile(housing_status="unhoused", branch="marines")
        result = route_housing(profile)
        self.assertIn("branch_emergency_resources_available", result["flags"])
        self.assertTrue(any("Semper Fi" in n for n in result["notes"]))

    def test_army_national_guard_veteran_gets_branch_resources_when_unhoused(self):
        profile = VetHousingProfile(housing_status="unhoused", branch="army_ng")
        result = route_housing(profile)
        self.assertIn("branch_emergency_resources_available", result["flags"])
        self.assertTrue(any("Army Emergency Relief" in n for n in result["notes"]))


class LegalBranchEmergencyRegressionTest(unittest.TestCase):
    def test_marine_corps_veteran_gets_branch_resources_in_vtc_track(self):
        profile = VetLegalProfile(active_criminal_case=True, branch="marines")
        result = route_legal(profile)
        self.assertIn("branch_emergency_resources_available", result["flags"])
        self.assertTrue(any("Semper Fi" in n for n in result["notes"]))

    def test_air_national_guard_veteran_gets_branch_resources_in_medical_retirement_track(self):
        profile = VetLegalProfile(
            medical_retirement_va_dispute=True, branch="air_ng",
        )
        result = route_legal(profile)
        self.assertIn("branch_emergency_resources_available", result["flags"])
        self.assertTrue(any("Air Force Aid Society" in n for n in result["notes"]))


if __name__ == "__main__":
    unittest.main()
