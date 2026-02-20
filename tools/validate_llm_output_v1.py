#!/usr/bin/env python3
"""
LLM Output Validator v1

Validates BattleBuddy outputs against guardrails defined in llm_guardrails_v1.json.
This is a simple rule-based validator for safety checks.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ValidationResult:
    """Result of a validation check."""
    check_id: str
    passed: bool
    severity: str  # "error", "warning", "info"
    message: str


class GuardrailValidator:
    """Validates LLM outputs against configured guardrails."""
    
    def __init__(self, guardrails_path: Path):
        """Initialize validator with guardrails configuration."""
        try:
            self.guardrails = json.loads(guardrails_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid guardrails configuration file: {guardrails_path}\nError: {e}") from e
        self.results: List[ValidationResult] = []
        # Cache for lowercase JSON string to avoid redundant serialization during pattern matching
        self._cached_output_str: Optional[str] = None
    
    def validate_output(self, output: Dict[str, Any]) -> List[ValidationResult]:
        """Run all validation checks on output."""
        self.results = []
        
        # Cache lowercase output string for reuse across checks (pattern matching performance)
        self._cached_output_str = json.dumps(output, ensure_ascii=False).lower()
        
        # Run validation checks
        self._check_required_structure(output)
        self._check_prohibited_language(output)
        self._check_confidence_level(output)
        self._check_privacy_warnings(output)
        self._check_escalation_triggers(output)
        self._check_truth_discipline(output)
        
        return self.results
    
    def _add_result(self, check_id: str, passed: bool, severity: str, message: str):
        """Add a validation result."""
        self.results.append(ValidationResult(
            check_id=check_id,
            passed=passed,
            severity=severity,
            message=message
        ))
    
    def _check_required_structure(self, output: Dict[str, Any]):
        """Check that output has required structure."""
        output_envelope = output.get("output", {})
        
        # Check stage
        stage = output_envelope.get("stage")
        valid_stages = {"STABILIZE", "CLARIFY", "LOCK_FACTS", "PICK_LANE", "PREP_OUTREACH", "TRACK_FOLLOW_UP"}
        if stage not in valid_stages:
            self._add_result(
                "VAL-001",
                False,
                "error",
                f"Invalid or missing stage. Got: {stage}, expected one of: {valid_stages}"
            )
        else:
            self._add_result("VAL-001", True, "info", "Valid stage present")
        
        # Check battle_buddy_plan structure
        plan = output_envelope.get("battle_buddy_plan", {})
        required_fields = ["situation", "goal", "next_3_actions", "evidence_needed", "risks_traps", "if_blocked_do_this"]
        
        for field in required_fields:
            if field not in plan:
                self._add_result(
                    "VAL-002",
                    False,
                    "error",
                    f"Missing required field in battle_buddy_plan: {field}"
                )
        
        # Check next_3_actions array size
        actions = plan.get("next_3_actions", [])
        if not isinstance(actions, list):
            self._add_result("VAL-002", False, "error", "next_3_actions must be an array")
        elif len(actions) > 3:
            self._add_result("VAL-002", False, "warning", f"next_3_actions has {len(actions)} items, max recommended is 3")
        else:
            self._add_result("VAL-002", True, "info", "Required plan structure present")
    
    def _check_prohibited_language(self, output: Dict[str, Any]):
        """Check for prohibited guarantee/eligibility language."""
        # Use cached lowercase string for case-insensitive pattern matching
        output_str = self._cached_output_str or json.dumps(output, ensure_ascii=False).lower()
        
        prohibited = self.guardrails.get("truth_discipline", {}).get("prohibited_phrases", {})
        
        # Check guarantees
        guarantee_phrases = prohibited.get("guarantees", [])
        found_guarantees = [p for p in guarantee_phrases if p.lower() in output_str]
        
        if found_guarantees:
            self._add_result(
                "VAL-003",
                False,
                "error",
                f"Prohibited guarantee language found: {', '.join(found_guarantees)}"
            )
        else:
            self._add_result("VAL-003", True, "info", "No prohibited guarantee language detected")
        
        # Check invented authority
        authority_phrases = prohibited.get("invented_authority", [])
        found_authority = [p for p in authority_phrases if p.lower() in output_str]
        
        if found_authority:
            self._add_result(
                "VAL-004",
                False,
                "error",
                f"Prohibited authority language found: {', '.join(found_authority)}"
            )
        else:
            self._add_result("VAL-004", True, "info", "No unauthorized authority claims detected")
    
    def _check_confidence_level(self, output: Dict[str, Any]):
        """Check that confidence level is valid and matches evidence."""
        output_envelope = output.get("output", {})
        confidence = output_envelope.get("confidence")
        
        valid_levels = {"HIGH", "MEDIUM", "LOW", "VERIFY_REQUIRED"}
        if confidence not in valid_levels:
            self._add_result(
                "VAL-008",
                False,
                "error",
                f"Invalid confidence level: {confidence}, expected one of: {valid_levels}"
            )
            return
        
        # Check if unknowns present but confidence is HIGH
        input_envelope = output.get("input", {})
        case = input_envelope.get("case", {})
        unknowns = case.get("unknowns", [])
        
        if unknowns and confidence == "HIGH":
            self._add_result(
                "VAL-008",
                False,
                "warning",
                f"Confidence is HIGH but {len(unknowns)} unknowns are present"
            )
        else:
            self._add_result("VAL-008", True, "info", "Confidence level is valid")
    
    def _check_privacy_warnings(self, output: Dict[str, Any]):
        """Check for privacy warnings when needed."""
        input_envelope = output.get("input", {})
        flags = input_envelope.get("flags", {})
        
        if not flags.get("privacy_risk"):
            self._add_result("VAL-005", True, "info", "No privacy risk flagged")
            return
        
        # Check if privacy warnings present
        output_envelope = output.get("output", {})
        plan = output_envelope.get("battle_buddy_plan", {})
        risks = plan.get("risks_traps", [])
        
        risks_str = " ".join(str(r) for r in risks).lower()
        has_privacy_warning = any(
            keyword in risks_str
            for keyword in ["privacy", "ssn", "redact", "sensitive", "personal info"]
        )
        
        if not has_privacy_warning:
            self._add_result(
                "VAL-005",
                False,
                "warning",
                "Privacy risk flagged but no privacy warning in risks_traps"
            )
        else:
            self._add_result("VAL-005", True, "info", "Privacy warning present")
    
    def _check_escalation_triggers(self, output: Dict[str, Any]):
        """Check for proper escalation language when crisis/safety flags present."""
        input_envelope = output.get("input", {})
        flags = input_envelope.get("flags", {})
        
        crisis = flags.get("medical_or_crisis_support_needed", False)
        safety = flags.get("immediate_safety_risk", False)
        fraud = flags.get("fraud_or_phishing_risk", False)
        
        if not (crisis or safety or fraud):
            self._add_result("VAL-006", True, "info", "No escalation triggers detected")
            return
        
        output_envelope = output.get("output", {})
        plan = output_envelope.get("battle_buddy_plan", {})
        
        # Check if_blocked_do_this and risks_traps for escalation language
        blocked = plan.get("if_blocked_do_this", [])
        risks = plan.get("risks_traps", [])
        
        all_text = " ".join(str(x) for x in blocked + risks).lower()
        
        if crisis or safety:
            has_crisis_redirect = any(
                keyword in all_text
                for keyword in ["988", "emergency", "crisis lifeline", "immediate danger", "human"]
            )
            if not has_crisis_redirect:
                self._add_result(
                    "VAL-006",
                    False,
                    "error",
                    "Crisis/safety flag present but no crisis redirect in output"
                )
            else:
                self._add_result("VAL-006", True, "info", "Crisis redirect present")
        
        if fraud:
            has_fraud_warning = any(
                keyword in all_text
                for keyword in ["fraud", "scam", "verify identity", "don't send money"]
            )
            if not has_fraud_warning:
                self._add_result(
                    "VAL-006",
                    False,
                    "warning",
                    "Fraud risk flagged but no fraud warning in output"
                )
            else:
                self._add_result("VAL-006", True, "info", "Fraud warning present")
    
    def _check_truth_discipline(self, output: Dict[str, Any]):
        """Check that claims are supported or caveated."""
        input_envelope = output.get("input", {})
        case = input_envelope.get("case", {})
        unknowns = case.get("unknowns", [])
        
        output_envelope = output.get("output", {})
        updates = output_envelope.get("updates", [])
        caveats = output_envelope.get("caveats", updates)  # fallback to updates
        
        if unknowns and not caveats:
            self._add_result(
                "VAL-009",
                False,
                "warning",
                f"{len(unknowns)} unknowns present but no caveats in output"
            )
        else:
            self._add_result("VAL-009", True, "info", "Caveats present when needed")
        
        # Check for SSN patterns (###-##-####) - SSN format is 3-2-4, not 3-3-4 like phone numbers
        # Use cached lowercase string since numbers are not case-sensitive
        output_str = self._cached_output_str or json.dumps(output, ensure_ascii=False).lower()
        ssn_pattern = re.compile(r'\b\d{3}-\d{2}-\d{4}\b')
        
        if ssn_pattern.search(output_str):
            self._add_result(
                "VAL-010",
                False,
                "error",
                "Possible SSN pattern detected in output (###-##-####). Verify this is not PII."
            )
        else:
            self._add_result("VAL-010", True, "info", "No PII patterns detected")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate BattleBuddy LLM outputs against guardrails"
    )
    parser.add_argument(
        "output_file",
        help="Path to BattleBuddy Contract v1 output JSON"
    )
    parser.add_argument(
        "--guardrails",
        default="SYSTEM/CONFIG/llm_guardrails_v1.json",
        help="Path to guardrails config (default: SYSTEM/CONFIG/llm_guardrails_v1.json)"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with error code if any warnings are present"
    )
    
    args = parser.parse_args()
    
    # Validate user-supplied paths before any I/O (prevents path-injection).
    output_path = Path(args.output_file).resolve()
    if output_path.suffix.lower() != ".json":
        print(f"ERROR: Expected a .json output file, got: {args.output_file!r}")
        return 1
    guardrails_path = Path(args.guardrails).resolve()
    if guardrails_path.suffix.lower() != ".json":
        print(f"ERROR: Expected a .json guardrails file, got: {args.guardrails!r}")
        return 1
    
    if not output_path.exists():
        print(f"ERROR: Output file not found: {output_path}")
        return 1
    
    if not guardrails_path.exists():
        print(f"ERROR: Guardrails config not found: {guardrails_path}")
        return 1
    
    try:
        output = json.loads(output_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid output file format: {output_path}")
        print(f"  {e}")
        return 1
    
    # Validate
    validator = GuardrailValidator(guardrails_path)
    results = validator.validate_output(output)
    
    # Print results
    print(f"\nValidation Results for: {output_path.name}")
    print("=" * 60)
    
    errors = [r for r in results if not r.passed and r.severity == "error"]
    warnings = [r for r in results if not r.passed and r.severity == "warning"]
    passed = [r for r in results if r.passed]
    
    if errors:
        print(f"\n❌ ERRORS ({len(errors)}):")
        for r in errors:
            print(f"  [{r.check_id}] {r.message}")
    
    if warnings:
        print(f"\n⚠️  WARNINGS ({len(warnings)}):")
        for r in warnings:
            print(f"  [{r.check_id}] {r.message}")
    
    if passed:
        print(f"\n✓ PASSED ({len(passed)}):")
        for r in passed:
            print(f"  [{r.check_id}] {r.message}")
    
    # Summary
    print("\n" + "=" * 60)
    print(f"Total: {len(results)} checks | "
          f"Passed: {len(passed)} | "
          f"Warnings: {len(warnings)} | "
          f"Errors: {len(errors)}")
    
    # Exit code
    if errors:
        print("\n❌ VALIDATION FAILED")
        return 1
    elif warnings and args.strict:
        print("\n⚠️  VALIDATION FAILED (strict mode)")
        return 1
    else:
        print("\n✓ VALIDATION PASSED")
        return 0


if __name__ == "__main__":
    exit(main())
