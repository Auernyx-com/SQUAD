"""
tests/test_val_007_claim_trace.py

SYSTEM/CONFIG/llm_guardrails_v1.json declares VAL-007 ("All claims trace to
inputs or marked verify-required", fail_action: warn), but
tools/validate_llm_output_v1.py implemented VAL-001..006 and VAL-008..010
and never called anything for VAL-007 -- the declared check silently never
ran. This mattered because it's the one check that would catch the exact
risk KNOWN_GAPS.md already calls "the most significant safety gap in the
current architecture": the model hallucinating a phone number.

Scope, deliberately kept narrow (KISS): this checks phone-number-shaped
claims only, not dates/dollar amounts/program names -- phone numbers are
the one claim type in this schema that is both a named, concrete risk and
cheap to verify mechanically (extract + compare) without building a real
NLP claim-extraction system.

A phone number in the output "traces to inputs" if it:
  - appears anywhere in the `input` envelope the model was given (meaning
    the model repeated a fact it was handed, e.g. from module_results),
  - or is one of the static, pre-verified numbers in
    MODULES/_shared/contacts.py (these are safe regardless of case,
    the same way VAL-006 always accepts 988 as a valid crisis redirect).
Otherwise, the output must be marked confidence=VERIFY_REQUIRED, or the
check fails as a warning (matching the config's fail_action).
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import validate_llm_output_v1 as val  # noqa: E402

GUARDRAILS_PATH = REPO_ROOT / "SYSTEM" / "CONFIG" / "llm_guardrails_v1.json"


def _base_output(confidence: str = "HIGH", plan_extra: dict | None = None,
                  input_extra: dict | None = None) -> dict:
    plan = {
        "situation": "Needs housing help.",
        "goal": "Stabilize housing.",
        "next_3_actions": ["Call the local VSO.", "Gather ID documents.", "Confirm intake appointment."],
        "evidence_needed": [],
        "risks_traps": [],
        "if_blocked_do_this": [],
    }
    if plan_extra:
        plan.update(plan_extra)
    doc = {
        "input": {
            "case": {"case_id": "T1", "known_facts": [], "unknowns": []},
            "flags": {},
            "module_results": {},
        },
        "output": {
            "stage": "PICK_LANE",
            "confidence": confidence,
            "updates": [],
            "pathfinder_plan": plan,
        },
    }
    if input_extra:
        doc["input"].update(input_extra)
    return doc


class Val007DeclaredButRunsTest(unittest.TestCase):
    """The config declares VAL-007 -- the validator must actually run it."""

    def test_val_007_appears_in_results(self):
        validator = val.GuardrailValidator(GUARDRAILS_PATH)
        results = validator.validate_output(_base_output())
        ids = {r.check_id for r in results}
        self.assertIn("VAL-007", ids, "VAL-007 is declared in the guardrails config but never checked")


class Val007PhoneTraceTest(unittest.TestCase):
    def _val007(self, results):
        matches = [r for r in results if r.check_id == "VAL-007"]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_no_phone_numbers_passes_trivially(self):
        validator = val.GuardrailValidator(GUARDRAILS_PATH)
        results = validator.validate_output(_base_output())
        r = self._val007(results)
        self.assertTrue(r.passed)

    def test_hallucinated_untraced_number_warns(self):
        validator = val.GuardrailValidator(GUARDRAILS_PATH)
        output = _base_output(
            confidence="HIGH",
            plan_extra={"next_3_actions": ["Call 555-019-2222 to schedule."]},
        )
        results = validator.validate_output(output)
        r = self._val007(results)
        self.assertFalse(r.passed)
        self.assertEqual(r.severity, "warning")

    def test_number_present_in_input_module_results_passes(self):
        validator = val.GuardrailValidator(GUARDRAILS_PATH)
        output = _base_output(
            confidence="HIGH",
            plan_extra={"next_3_actions": ["Call 555-019-2222 to schedule."]},
            input_extra={"module_results": {"housing": {"key_resources": ["Local VSO — 555-019-2222"]}}},
        )
        results = validator.validate_output(output)
        r = self._val007(results)
        self.assertTrue(r.passed)

    def test_verified_national_number_passes_with_no_case_data(self):
        validator = val.GuardrailValidator(GUARDRAILS_PATH)
        output = _base_output(
            confidence="HIGH",
            plan_extra={"next_3_actions": ["Call the VA main line at 1-800-827-1000."]},
        )
        results = validator.validate_output(output)
        r = self._val007(results)
        self.assertTrue(r.passed)

    def test_untraced_number_marked_verify_required_passes(self):
        validator = val.GuardrailValidator(GUARDRAILS_PATH)
        output = _base_output(
            confidence="VERIFY_REQUIRED",
            plan_extra={"next_3_actions": ["Try calling 555-019-2222, unconfirmed."]},
        )
        results = validator.validate_output(output)
        r = self._val007(results)
        self.assertTrue(r.passed)


if __name__ == "__main__":
    unittest.main()
