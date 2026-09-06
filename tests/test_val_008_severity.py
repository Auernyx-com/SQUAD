"""
tests/test_val_008_severity.py

Independent-audit finding (2026-09-06, round 3, medium): VAL-008's
invalid-confidence-value branch reports severity="error", but
SYSTEM/CONFIG/llm_guardrails_v1.json declares VAL-008's fail_action as
"warn" (matching VAL-008's OTHER branch -- unknowns present but
confidence=HIGH -- which already correctly uses "warning"). Since main()
in validate_llm_output_v1.py treats any severity="error" result as an
immediate hard failure regardless of --strict, a plan with a malformed/
unrecognized confidence value hard-blocks the whole pipeline instead of
just warning as the config declares -- the opposite-direction mismatch
from the already-fixed VAL-006 bug (which was too lax; this one is too
strict).

Confirmed directly before fixing: confidence="HIGH_CONFIDENCE" (an
invalid value) produced VAL-008 with severity="error".
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import validate_llm_output_v1 as val  # noqa: E402

GUARDRAILS_PATH = REPO_ROOT / "SYSTEM" / "CONFIG" / "llm_guardrails_v1.json"


def _base_output(confidence):
    return {
        "input": {"case": {"unknowns": []}, "flags": {}},
        "output": {
            "stage": "CLARIFY",
            "confidence": confidence,
            "updates": [],
            "pathfinder_plan": {
                "situation": "x", "goal": "x",
                "next_3_actions": ["a", "b", "c"],
                "evidence_needed": [], "risks_traps": [], "if_blocked_do_this": [],
            },
        },
    }


class Val008SeverityTest(unittest.TestCase):
    def _val008(self, results):
        matches = [r for r in results if r.check_id == "VAL-008"]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_invalid_confidence_value_is_a_warning_not_an_error(self):
        validator = val.GuardrailValidator(GUARDRAILS_PATH)
        results = validator.validate_output(_base_output("HIGH_CONFIDENCE"))
        r = self._val008(results)
        self.assertFalse(r.passed)
        self.assertEqual(
            r.severity, "warning",
            "VAL-008 must warn, not error, matching SYSTEM/CONFIG/llm_guardrails_v1.json's "
            "declared fail_action ('warn') for VAL-008.",
        )

    def test_invalid_confidence_value_does_not_hard_fail_overall_validation(self):
        validator = val.GuardrailValidator(GUARDRAILS_PATH)
        results = validator.validate_output(_base_output("HIGH_CONFIDENCE"))
        errors = [r for r in results if not r.passed and r.severity == "error"]
        self.assertFalse(
            errors,
            "An invalid confidence value must not hard-fail validation (main() only "
            "exits non-zero on severity=='error' without --strict) -- it should warn.",
        )

    def test_valid_confidence_still_passes_no_regression(self):
        validator = val.GuardrailValidator(GUARDRAILS_PATH)
        results = validator.validate_output(_base_output("HIGH"))
        r = self._val008(results)
        self.assertTrue(r.passed)

    def test_unknowns_present_with_high_confidence_still_warns_no_regression(self):
        validator = val.GuardrailValidator(GUARDRAILS_PATH)
        output = _base_output("HIGH")
        output["input"]["case"]["unknowns"] = ["something unresolved"]
        validator = val.GuardrailValidator(GUARDRAILS_PATH)
        results = validator.validate_output(output)
        r = self._val008(results)
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, "warning")


if __name__ == "__main__":
    unittest.main()
