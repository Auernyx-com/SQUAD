"""
tests/test_cra_claim_status.py

Independent-audit finding (2026-09-06, round 3, high): `claim_status` is a
required, schema-validated input field (pathfinder_cra/schema/cra.schema.json,
enum: not_filed/filed_pending/denied/appeal_pending/unknown) -- but
run_cra_v1.py's _build_ok_report() never reads it anywhere (confirmed by
grep: zero references to "claim_status" in the whole file before this fix).
Readiness/gaps/next-steps were derived only from evidence presence and
administrative context, never from claim status itself.

Confirmed directly before fixing: a veteran who was DENIED, has a VSO, has
received the decision letter, and has all evidence present (but hasn't yet
picked an appeal lane -- appeal_lane_used: "unknown", the same
appeal_lane_unknown gap that already exists independent of claim_status)
got readiness="procedurally_ready_verification_pending" and a single next
step ("build_one_page_timeline") with no mention of the 1-year appeal
deadline at all -- the exact fact pattern already fixed for VA Benefits/
MedDisability routing (recent_denial reaching the appeal track, PRs
#37/#48), but never addressed here.

Fixed additively: claim_status in {"denied", "appeal_pending"} now adds a
dedicated procedural pattern and next-safe-step about the appeal deadline,
independent of (and in addition to) any evidence/admin gaps already
present. Per this module's own explicit design ("this is a process-only
gap map; it does not assess eligibility or outcomes"), readiness itself is
NOT changed by claim_status -- only the informational pattern/step layer.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "pathfinder_cra"))

from run_cra_v1 import _build_ok_report  # noqa: E402


def _base_payload(claim_status: str, appeal_lane_used: str = "none") -> dict:
    return {
        "module": "pathfinder.cra",
        "version": "1.0.0",
        "claim_status": claim_status,
        "evidence_presence": {
            "service_records_available": "yes",
            "current_diagnosis_documentation_exists": "yes",
            "nexus_opinion_exists": "yes",
            "lay_statements_present": "yes",
            "continuity_evidence_present": "yes",
        },
        "administrative_context": {
            "representation_status": "vso",
            "prior_va_decisions_received": "yes",
            "appeal_lane_used": appeal_lane_used,
        },
        "veteran_reported_barriers": [],
    }


class ClaimStatusAppealDeadlineTest(unittest.TestCase):
    def test_denied_with_all_evidence_present_still_surfaces_appeal_deadline(self):
        report = _build_ok_report(_base_payload("denied"))
        self.assertIn("appeal_deadline_may_apply", report["procedural_patterns"])
        steps = [s["step"] for s in report["next_safe_steps"]]
        self.assertIn("confirm_appeal_deadline", steps)

    def test_appeal_pending_also_surfaces_the_deadline_pattern(self):
        report = _build_ok_report(_base_payload("appeal_pending"))
        self.assertIn("appeal_deadline_may_apply", report["procedural_patterns"])

    def test_not_filed_does_not_surface_appeal_deadline_no_regression(self):
        report = _build_ok_report(_base_payload("not_filed"))
        self.assertNotIn("appeal_deadline_may_apply", report["procedural_patterns"])
        steps = [s["step"] for s in report["next_safe_steps"]]
        self.assertNotIn("confirm_appeal_deadline", steps)

    def test_readiness_classification_is_unaffected_by_claim_status(self):
        # Per this module's own design: process-only gap map, does not
        # assess eligibility or outcomes -- claim_status must not change
        # the readiness bucket, only add the deadline pattern/step.
        report_denied = _build_ok_report(_base_payload("denied"))
        report_not_filed = _build_ok_report(_base_payload("not_filed"))
        self.assertEqual(report_denied["summary"]["readiness"], report_not_filed["summary"]["readiness"])

    def test_unknown_claim_status_does_not_crash_no_regression(self):
        report = _build_ok_report(_base_payload("unknown"))
        self.assertEqual(report["status"], "ok")


if __name__ == "__main__":
    unittest.main()
