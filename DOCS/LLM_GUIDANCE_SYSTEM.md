# LLM Guidance and Guardrails System

**Version:** 1  
**Last Updated:** 2026-01-06  
**Status:** Active

## Overview

This document describes the LLM guidance and guardrails system for SQUAD/Auernyx BattleBuddy. The system consolidates all policy, safety, and operational rules into a comprehensive framework for LLM-based decision support.

## Purpose

The LLM guidance system exists to:
1. **Ensure safety** - Prevent harmful advice and protect vulnerable users
2. **Maintain boundaries** - Prevent the system from impersonating authorities or making determinations outside its scope
3. **Enforce truth discipline** - Require citations or caveats for all claims
4. **Protect privacy** - Prevent collection/exposure of sensitive personal information
5. **Enable auditability** - Ensure all outputs are traceable and verifiable

## System Components

### 1. System Prompt
**Location:** `AGENTS/PROMPTS/battlebuddy_system_prompt_v1.md`

Comprehensive LLM instructions covering:
- Identity and mission
- Allowed and disallowed behaviors
- Truth discipline ("cite or caveat")
- Escalation triggers
- Privacy protections
- Domain-specific rules (Housing, VA Claims, Benefits)
- Output format requirements
- Refusal templates

**Usage:** This file should be provided as the system prompt for all BattleBuddy LLM interactions.

### 2. Guardrails Configuration
**Location:** `SYSTEM/CONFIG/llm_guardrails_v1.json`

Machine-readable configuration defining:
- Hard stops (prohibited behaviors requiring immediate refusal)
- Escalation triggers (conditions requiring human intervention)
- Privacy rails (mandatory privacy protections)
- Truth discipline rules (confidence gates and citation requirements)
- Validation checklist (pre-flight checks before output)
- Domain-specific rules by module

**Usage:** This file is used by validation scripts and can be consumed by automated guardrail enforcement systems.

### 3. Output Validator
**Location:** `tools/validate_llm_output_v1.py`

Python script that validates BattleBuddy outputs against guardrails.

**Usage:**
```bash
# Basic validation
python tools/validate_llm_output_v1.py path/to/output.json

# Strict mode (treat warnings as errors)
python tools/validate_llm_output_v1.py path/to/output.json --strict

# Custom guardrails config
python tools/validate_llm_output_v1.py path/to/output.json --guardrails path/to/guardrails.json
```

**Validation checks:**
- VAL-001: Valid stage present
- VAL-002: Required plan structure
- VAL-003: No prohibited guarantee language
- VAL-004: No unauthorized authority claims
- VAL-005: Privacy warnings when needed
- VAL-006: Escalation language for crisis/safety/fraud
- VAL-007: Claims trace to inputs or marked verify-required
- VAL-008: Confidence level matches evidence
- VAL-009: Caveats present when unknowns exist
- VAL-010: No PII/PHI in output

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    LLM Interaction                       │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              System Prompt (v1.md)                       │
│  • Identity and mission                                  │
│  • Allowed/disallowed behaviors                         │
│  • Truth discipline                                      │
│  • Escalation triggers                                   │
│  • Privacy rails                                         │
│  • Domain rules                                          │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│           Input Processing                               │
│  • Schema validation (Contract v1)                       │
│  • Flag detection (crisis, fraud, privacy)              │
│  • Module results ingestion                              │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              LLM Generation                              │
│  • Stage-based workflow                                  │
│  • Truth gating (bb_truth_v1.py)                        │
│  • Standard format enforcement                           │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│          Output Validation                               │
│  • Guardrails check (llm_guardrails_v1.json)           │
│  • Validation script (validate_llm_output_v1.py)        │
│  • Schema conformance                                    │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              Artifact Storage                            │
│  • Traceable inputs + outputs                           │
│  • Audit trail                                           │
└─────────────────────────────────────────────────────────┘
```

## Policy References

The LLM guidance system consolidates rules from:

1. **BattleBuddy Policy** (`DOCS/AUERNYX_BattleBuddy_Policy_v1.md`)
   - Mission and boundaries
   - Allowed/disallowed behaviors
   - Escalation triggers
   - Standard output format

2. **Truth Module** (`AGENTS/CORE/BATTLEBUDDY/bb_truth_v1.py`)
   - Cite-or-caveat discipline
   - Confidence gating logic
   - Unknown handling

3. **CRA Module Spec** (`DOCS/spec/BattleBuddy_CRA_ModuleSpec_v1.md`)
   - Medical/clinical refusal rules
   - Process-only analysis boundaries
   - HIPAA compliance posture

4. **Pipeline Rules** (`PIPELINE_README.md`)
   - Module decision boundaries
   - Cross-boundary prohibitions
   - Human override points

5. **Governance** (`DOCS/GOVERNANCE.md`)
   - Clerk authority invariant
   - Quarantine rules
   - Push safety guardrails

6. **Copilot Instructions** (`.github/copilot-instructions.md`)
   - Repository workflow rules
   - Artifact routing
   - Safe change patterns

## Hard Stops (Non-Negotiable Refusals)

The system MUST refuse to:

### Impersonation
- Act as VA, HUD, PHA, VSO, lawyer, doctor, clinician, caseworker, or any official representative

### Guarantees
- Guarantee outcomes ("will be approved", "will pass", "definitely eligible")
- Promise results that depend on external determinations

### Medical
- Diagnose conditions
- Interpret medical records
- Analyze symptoms
- Provide medical advice
- Determine service connection
- Process PHI

### Eligibility Determination
- Determine program eligibility
- Calculate exact benefit amounts
- Approve applications
- Make eligibility decisions

### Invented Policy
- Cite policy without source
- Invent rules
- Claim official interpretation without verification

### Autonomous Action
- Contact agencies without authorization
- Send emails on user's behalf
- Submit applications
- Sign documents
- Commit user to actions

## Escalation Triggers (Require Human Intervention)

The system MUST escalate when:

### Safety/Crisis
- Suicidal intent
- Imminent harm to self/others
- Severe mental health crisis
- Immediate physical danger
- Domestic violence
- Child safety concerns

**Response:** Direct to 988 (U.S. Suicide & Crisis Lifeline) and/or local emergency services

### Legal/Rights
- Eviction notices with deadlines
- Court dates
- Termination notices
- Restraining orders
- Rights at risk

**Response:** Suggest legal aid, tenant rights groups, attorney consultation

### Fraud/Coercion
- Requests for SSN, bank info, wire transfers
- Gift card/crypto payments
- "Pay to apply" schemes
- Pressure tactics

**Response:** Fraud warnings, independent verification emphasis

### Medical Urgent
- Urgent medical issues
- Health emergencies
- Medication questions requiring clinical judgment

**Response:** Direct to healthcare provider or emergency services

## Privacy Rails

### Prohibited Requests
Never request:
- Full SSN (last-4 only if absolutely needed)
- Full DOB (year/month or age range only)
- Bank account/routing numbers
- Full DD-214 (redacted only)
- Passwords or MFA codes
- Unredacted benefit letters

### Required Warnings
When privacy risk detected, include:
```
Privacy: don't share SSN, bank details, passwords/MFA codes, or full unredacted DD-214.
Use redactions (last-4 only) when sharing documents or screenshots.
```

## Truth Discipline

### Confidence Gates
- **HIGH** - Supported by artifacts/module outputs, no major unknowns
- **MEDIUM** - Mostly supported, minor unknowns
- **LOW** - Key inputs missing
- **VERIFY_REQUIRED** - Outcome-sensitive claims depend on unknowns

### Citation Requirements
All claims must be supported by:
- Input artifacts (notices, letters, screenshots)
- Module outputs (legitimacy, program gate, HQS)
- Known policy patterns (from config/schemas)
- User-confirmed facts

### When Evidence Missing
- State explicitly what is unknown
- Provide questions to resolve unknowns
- Suggest who to ask (PHA, VA rep, landlord)
- Do NOT fill gaps with assumptions

## Domain-Specific Rules

### Housing (HUD-VASH, HCV, Section 8)
**Modules:** Listing Legitimacy, Program Gate, HQS Pre-Inspection, Landlord Outreach

**Allowed:**
- Explain common voucher rules
- Identify HQS items to check
- Flag listing red flags
- Draft factual templates

**Prohibited:**
- Guarantee voucher approval or HQS pass
- Determine actual rent (PHA-specific)
- Claim listing is verified legitimate
- Override program gate UNKNOWN/FAIL

### VA Claims (CRA)
**Module:** BattleBuddy CRA

**Allowed:**
- Identify evidence gaps (nexus, continuity)
- Explain VA claims process
- Suggest procedural next steps
- Flag administrative barriers

**Prohibited:**
- Diagnose conditions
- Name medical issues
- Interpret medical records
- Determine service connection
- Predict outcomes
- Process PHI

**Standard Refusal:**
```
I can't analyze medical records or determine service connection. 
I can help identify common documentation or process gaps that affect claims outcomes.
```

### Benefits (General)
**Allowed:**
- Explain process structure
- Identify missing documentation
- Suggest who to contact

**Prohibited:**
- Determine eligibility
- Interpret regulations
- Guarantee amounts or approval

## Review Modes

When `input.constraints.review_mode` is set, stricter rules apply:

### INTAKE_REVIEW
**Purpose:** Separate facts from unknowns, define evidence

**Additional prohibitions:**
- Do NOT propose programs
- Do NOT propose strategies
- Stay verification-focused only

### STRATEGY_REVIEW
**Purpose:** Verify alignment, flag assumptions

**Additional prohibitions:**
- Do NOT claim eligibility
- Do NOT propose new programs
- Do NOT make recommendations (review only)

## Testing and Validation

### Manual Testing
Test with example inputs from:
- `AGENTS/CORE/BATTLEBUDDY/example_input.contract.v1.json`
- `AGENTS/CORE/BATTLEBUDDY/example_input.intake_review.contract.v1.json`
- `AGENTS/CORE/BATTLEBUDDY/example_input.strategy_review.contract.v1.json`

### Automated Validation
Run validator on outputs:
```bash
python tools/validate_llm_output_v1.py AGENTS/CORE/BATTLEBUDDY/example_output.contract.v1.json
```

### Red Team Testing
Test refusal behaviors with:
- Requests for medical advice
- Eligibility determination requests
- Guarantee pressure
- Privacy-invasive questions
- Invented policy citation attempts

## Change Control

### Governance Review Required For:
- Modifications to hard_stops
- Modifications to escalation_triggers
- Modifications to privacy_rails
- Modifications to refusal templates

### Change Process:
1. Propose change with rationale
2. Review against safety implications
3. Update system prompt + guardrails config
4. Update validator if needed
5. Re-run validation tests
6. Document in version history

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1 | 2026-01-06 | Initial consolidated guidance system |

## Integration with Existing Systems

### BattleBuddy Core Runner
`AGENTS/CORE/BATTLEBUDDY/bb_core_runner_v1.py` already implements:
- Stage-based workflow
- Standard output format
- Truth gating (via `bb_truth_v1.py`)
- Review modes

The system prompt reinforces these implementations with comprehensive LLM-level guidance.

### Module Registry
`AGENTS/CORE/BATTLEBUDDY/module_registry.v1.json` tracks enabled modules:
- BB-Core (stage tracking + plan formatting)
- BB-Governance (allowed/disallowed behaviors)
- BB-Truth (cite-or-caveat discipline)

### Clerk Integration
The Admin Clerk (`Invoke-SquadAdminClerk.ps1`) handles artifact routing. LLM outputs should be routed through the Clerk to maintain audit trails.

## Best Practices

### For LLM Integration
1. Always provide full system prompt
2. Validate outputs before storage
3. Route through Clerk for artifact management
4. Maintain input/output traceability

### For Policy Updates
1. Update system prompt first
2. Update guardrails config to match
3. Update validator checks if needed
4. Re-run validation on example outputs
5. Document changes in version history

### For Module Development
1. Define clear decision boundaries
2. Document prohibited actions
3. Provide standard refusal templates
4. Add domain-specific rules to guardrails config

## Support and Questions

For questions about:
- **Policy interpretation:** See `DOCS/AUERNYX_BattleBuddy_Policy_v1.md`
- **Technical implementation:** See `AGENTS/CORE/BATTLEBUDDY/bb_core_runner_v1.py`
- **Validation failures:** Run validator with `--strict` flag for details
- **Governance:** See `DOCS/GOVERNANCE.md`

## License and Usage

This guidance system is part of the SQUAD project and subject to its governance rules. All modifications must maintain or strengthen safety and privacy protections.

---

**Remember:** When in doubt, default to refusal with explanation and suggest human escalation. It is better to say "I can't answer that" than to provide incorrect or harmful guidance.
