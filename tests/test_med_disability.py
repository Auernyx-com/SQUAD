"""
tests/test_med_disability.py

Regression coverage for a silent-overwrite bug in
AGENTS/LOGIC/MedDisability_v0_1.py's route_med_disability().

TRACK 3 (Has Rating — Increase / Appeals) runs as a separate `if`, independent
of the Track 1 (not enrolled) / Track 2 (enrolled, no rating) if/elif chain
above it. That's correct when va_status alone decides which track fires, but
Track 1 ALSO fires whenever "healthcare_enrollment" is in need_branches, even
for a veteran whose va_status is "has_rating" — need_branches is documented
as multi-select, so a rated veteran can legitimately ask for both "help
re-enrolling in VA healthcare" AND "help with my appeal" at once.

When both fired, Track 3's appeals/increase branches set primary_path,
next_action, and secondary_options with plain `=` assignment instead of the
"first/most relevant wins" `result[...] = result[...] or (...)` convention
used everywhere else in this file (and in every sibling Division file) —
so Track 3 silently wiped out everything Track 1 had just set. The veteran's
flags still showed "not_enrolled" and key_forms still had "VA Form 10-10EZ",
but primary_path, next_action, and secondary_options all became appeals-only,
with no trace of how to actually re-enroll.

Confirmed against the pre-fix code with a direct probe: VetMedProfile(
va_status="has_rating", need_branches=["healthcare_enrollment", "appeal"],
recent_denial=True, has_new_evidence=True) returned next_action about
"Submit new evidence... VA Form 20-0995" with zero mention of
va.gov/health-care/apply, and secondary_options contained only the three
BVA/attorney/VSO appeals options -- Track 1's Vet Centers / Community Care /
State program options, plus the "Priority Group 1-3 enrollment" note it had
just inserted, were gone.

Fixed by using the same `or`-for-primary_path/next_action and always-extend-
never-replace-for-secondary_options convention Track 3 was missing.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "AGENTS" / "LOGIC"))

from MedDisability_v0_1 import VetMedProfile, route_med_disability  # noqa: E402


class MultiNeedDoesNotSilentlyDropEarlierGuidanceTest(unittest.TestCase):
    def test_healthcare_enrollment_plus_appeal_keeps_both_sets_of_guidance(self):
        profile = VetMedProfile(
            va_status="has_rating",
            discharge="honorable",
            disability_rating=70,
            need_branches=["healthcare_enrollment", "appeal"],
            recent_denial=True,
            has_new_evidence=True,
        )
        result = route_med_disability(profile)

        # Track 1's guidance must survive Track 3 running afterward.
        self.assertEqual(result["primary_path"], "VA Healthcare Enrollment — VA Form 10-10EZ")
        self.assertIn("va.gov/health-care/apply", result["next_action"])
        joined = " ".join(result["secondary_options"])
        self.assertIn("Vet Centers", joined)
        self.assertIn("Community Care", joined)
        self.assertIn("Priority Group 1", joined)

        # Track 3's guidance must still be present too -- additive, not a
        # replacement.
        self.assertIn("Board of Veterans Appeals", joined)
        self.assertIn("appeals_track", result["flags"])
        self.assertIn("VA Form 20-0995 (Supplemental Claim)", result["key_forms"])

    def test_healthcare_enrollment_plus_increase_claim_keeps_both(self):
        profile = VetMedProfile(
            va_status="has_rating",
            discharge="honorable",
            disability_rating=50,
            need_branches=["healthcare_enrollment", "increase_claim"],
        )
        result = route_med_disability(profile)

        self.assertEqual(result["primary_path"], "VA Healthcare Enrollment — VA Form 10-10EZ")
        joined = " ".join(result["secondary_options"])
        self.assertIn("Vet Centers", joined)
        self.assertIn("VSO review of your current rating decision", joined)
        self.assertIn("increase_track", result["flags"])

    def test_appeal_only_single_need_still_works_normally(self):
        # No regression for the common single-need case.
        profile = VetMedProfile(
            va_status="has_rating",
            discharge="honorable",
            disability_rating=70,
            need_branches=["appeal"],
            recent_denial=True,
            has_new_evidence=True,
        )
        result = route_med_disability(profile)

        self.assertEqual(result["primary_path"], "Supplemental Claim (new evidence)")
        self.assertIn("VA Form 20-0995", result["next_action"])
        joined = " ".join(result["secondary_options"])
        self.assertIn("Board of Veterans Appeals", joined)

    def test_increase_claim_only_single_need_still_works_normally(self):
        profile = VetMedProfile(
            va_status="has_rating",
            discharge="honorable",
            disability_rating=50,
            need_branches=["increase_claim"],
        )
        result = route_med_disability(profile)

        self.assertEqual(
            result["primary_path"],
            "Rating Increase — Supplemental Claim or direct increase request",
        )
        self.assertIn("VSO review of your current rating decision", result["secondary_options"])


class RecentDenialReachesAppealGuidanceEvenWithoutARatingTest(unittest.TestCase):
    """(the fix) Track 3 -- and the critical 1-year appeal-deadline warning
    inside it -- was gated on `va_status in ("has_rating", "100_percent_PT")`
    alone. A veteran whose va_history is "denied" correctly maps to va_status
    "enrolled_no_rating" (they don't have a confirmed rating) -- but that
    meant Track 3 could never fire for them at all, so they got Track 2's
    "file an initial claim" guidance with zero mention of the deadline.
    """

    def test_denied_with_no_rating_still_gets_the_appeal_deadline_warning(self):
        profile = VetMedProfile(
            va_status="enrolled_no_rating",
            discharge="honorable",
            disability_rating=None,
            recent_denial=True,
        )
        result = route_med_disability(profile)

        self.assertIn("appeals_track", result["flags"])
        joined_notes = " ".join(result["notes"])
        self.assertIn("one year from your decision letter", joined_notes)

    def test_denied_still_keeps_track_2s_initial_claim_guidance_too(self):
        # Additive, not a replacement -- Track 2 fires on the same
        # va_status regardless, and its guidance must survive.
        profile = VetMedProfile(
            va_status="enrolled_no_rating",
            discharge="honorable",
            disability_rating=None,
            recent_denial=True,
        )
        result = route_med_disability(profile)

        self.assertIn("unrated_claim_candidate", result["flags"])

    def test_not_denied_and_no_rating_does_not_trigger_appeals_track(self):
        profile = VetMedProfile(
            va_status="enrolled_no_rating",
            discharge="honorable",
            disability_rating=None,
            recent_denial=False,
        )
        result = route_med_disability(profile)

        self.assertNotIn("appeals_track", result["flags"])


if __name__ == "__main__":
    unittest.main()
