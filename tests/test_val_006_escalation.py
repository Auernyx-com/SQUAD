"""
tests/test_val_006_escalation.py

Independent-audit finding (2026-09-06), round 2: _check_escalation_triggers()
implements a single check, VAL-006, but its two branches disagree on
severity. The crisis/safety branch correctly reports severity="error" when
the required crisis-redirect language is missing -- matching
SYSTEM/CONFIG/llm_guardrails_v1.json's declared fail_action for VAL-006
("reject"). The fraud branch of the SAME check reports severity="warning"
instead when the required fraud-warning language is missing.

Since main() in validate_llm_output_v1.py only exits non-zero for
severity=="error" results (unless --strict is passed), this meant a plan
flagged as a fraud/phishing risk -- with none of the required fraud-caution
keywords in it -- passed validation by default. Confirmed directly with a
probe against the pre-fix code: a plan with flags.fraud_or_phishing_risk=True
and no fraud-warning language produced VAL-006 with severity="warning", and
main()'s own would-exit-non-zero logic (errors present) evaluated False --
"VALIDATION PASSED" for a fraud-risk plan carrying zero fraud caution.

Fixed by making the fraud branch use severity="error", matching both the
crisis/safety branch of this same check and the config's own declared
fail_action.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import validate_llm_output_v1 as val  # noqa: E402

GUARDRAILS_PATH = REPO_ROOT / "SYSTEM" / "CONFIG" / "llm_guardrails_v1.json"


def _base_plan(risks_traps=None, if_blocked=None):
    return {
        "input": {
            "case": {"unknowns": []},
            "flags": {},
        },
        "output": {
            "stage": "PICK_LANE",
            "confidence": "HIGH",
            "updates": [],
            "pathfinder_plan": {
                "situation": "Received a text claiming to be from the VA asking for payment.",
                "goal": "Resolve safely.",
                "next_3_actions": ["Do not respond.", "Call your VSO to confirm.", "Report to VA OIG."],
                "evidence_needed": [],
                "risks_traps": risks_traps or [],
                "if_blocked_do_this": if_blocked or [],
            },
        },
    }


class Val006FraudSeverityTest(unittest.TestCase):
    def _val006(self, results):
        matches = [r for r in results if r.check_id == "VAL-006"]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_fraud_flag_with_no_warning_fails_as_error_not_warning(self):
        output = _base_plan()
        output["input"]["flags"]["fraud_or_phishing_risk"] = True
        validator = val.GuardrailValidator(GUARDRAILS_PATH)
        results = validator.validate_output(output)
        r = self._val006(results)
        self.assertFalse(r.passed)
        self.assertEqual(
            r.severity, "error",
            "VAL-006's fraud branch must fail as 'error' to match its own "
            "crisis/safety branch and SYSTEM/CONFIG/llm_guardrails_v1.json's "
            "declared fail_action ('reject') for VAL-006.",
        )

    def test_fraud_flag_with_no_warning_fails_overall_validation(self):
        output = _base_plan()
        output["input"]["flags"]["fraud_or_phishing_risk"] = True
        validator = val.GuardrailValidator(GUARDRAILS_PATH)
        results = validator.validate_output(output)
        errors = [r for r in results if not r.passed and r.severity == "error"]
        self.assertTrue(
            errors,
            "A fraud-risk plan with zero fraud-warning language must fail "
            "validation (main() only exits non-zero on severity=='error' "
            "results without --strict) -- it must not silently pass.",
        )

    def test_fraud_flag_with_warning_present_still_passes(self):
        output = _base_plan(risks_traps=["This looks like a scam -- don't send money or verify identity first."])
        output["input"]["flags"]["fraud_or_phishing_risk"] = True
        validator = val.GuardrailValidator(GUARDRAILS_PATH)
        results = validator.validate_output(output)
        r = self._val006(results)
        self.assertTrue(r.passed)

    def test_crisis_branch_severity_unaffected_no_regression(self):
        output = _base_plan()
        output["input"]["flags"]["immediate_safety_risk"] = True
        validator = val.GuardrailValidator(GUARDRAILS_PATH)
        results = validator.validate_output(output)
        r = self._val006(results)
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, "error")

    def test_no_flags_still_passes_as_info(self):
        output = _base_plan()
        validator = val.GuardrailValidator(GUARDRAILS_PATH)
        results = validator.validate_output(output)
        r = self._val006(results)
        self.assertTrue(r.passed)
        self.assertEqual(r.severity, "info")


if __name__ == "__main__":
    unittest.main()
