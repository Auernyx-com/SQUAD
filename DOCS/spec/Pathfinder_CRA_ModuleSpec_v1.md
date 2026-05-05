# MODULE SPEC — Claim Readiness & Evidence Gap Analysis (CRA)

## Module Name

Pathfinder — Claim Readiness Analysis (CRA)

## Module Type

Non-clinical, non-authoritative, process-analysis module

## Status

Design-approved, safe to implement

## Purpose

The Claim Readiness Analysis module exists to help identify administrative and evidentiary gaps that commonly prevent successful VA service-connection outcomes.

It does not:

- Diagnose conditions
- Interpret medical records
- Determine eligibility
- Replace clinicians, VSOs, or accredited representatives

It operates entirely at the process and documentation level.

## Core Principle (Invariant)

Pathfinder analyzes process completeness, not health facts.

If a task requires medical judgment, clinical interpretation, or eligibility determination, the module must refuse.

## Inputs (Allowed)

All inputs must be categorical, boolean, or self-reported, never clinical.

### Claim Status

- not_filed
- filed_pending
- denied
- appeal_pending
- unknown

### Evidence Presence (yes / no / unknown)

- Service records available
- Current diagnosis documentation exists (yes/no only, no details)
- Nexus opinion exists
- Lay statements present
- Continuity evidence present

### Administrative Context

- Representation status (none / VSO / attorney / unknown)
- Prior VA decisions received (yes/no)
- Appeal lane used (if any)

### Veteran-Reported Barriers (Non-medical)

- Difficulty obtaining records
- Confusion about process
- Missed deadlines
- Lack of representation
- Conflicting information received

## Explicitly Prohibited Inputs

The module must reject or ignore:

- Diagnoses
- Symptoms
- Treatment details
- Medical notes
- Lab results
- Provider opinions
- Disability ratings tied to conditions

If detected, the module must:

- Refuse analysis
- Flag the data
- Explain the refusal

## Outputs (Allowed)

### 1) Claim Readiness Summary

High-level status:

- “Incomplete — common evidentiary gaps present”
- “Procedurally ready, evidence verification pending”
- “Administrative barriers detected”

### 2) Evidence Gap Map

A categorized list such as:

- Missing service documentation
- Missing nexus opinion
- Incomplete continuity evidence
- Administrative follow-through gaps

No medical interpretation. No condition naming.

### 3) Process Guidance (Non-Prescriptive)

Examples:

- “Claims are commonly denied when nexus opinions are missing.”
- “Veterans often require an accredited representative to navigate appeals lanes.”
- “VA decisions frequently cite lack of continuity evidence.”

These are patterns, not advice.

### 4) Next Procedural Steps (Safe)

Examples:

- “Request service records from NPRC if unavailable.”
- “Consider consulting an accredited VSO for claim review.”
- “Obtain copies of prior VA decision letters.”

No instruction on what medical evidence should say.

## Refusal Rules (Hard)

Pathfinder must refuse if asked to:

- Decide whether a condition is service-connected
- Interpret VA medical care adequacy
- Explain a diagnosis
- Suggest what a clinician should write
- Infer eligibility based on health status

## Standard Refusal Language

“I can’t analyze medical records or determine service connection. I can help identify common documentation or process gaps that affect claims outcomes.”

## Compliance Posture

### HIPAA

- Module does not store, process, or analyze PHI
- Operates outside covered-entity scope by design

### VA Alignment

- Informed by VA claims process structure
- Does not claim VA authority or integration
- Uses publicly known process mechanics only

## Schema-Level Guardrails (Required)

- Enumerated fields only
- No free-text medical fields
- No attachment parsing
- Validation fails if prohibited fields appear

Reference schema:

- `pathfinder_cra/schema/cra.schema.json`

Output schema:

- `pathfinder_cra/schema/cra_output.schema.json`

## Training Note (Important)

This module is trained on patterns, not examples.

Acceptable training sources:

- Public VA appeals statistics
- Redacted denial reason summaries
- VSO process documentation
- Veteran-reported administrative experiences

Unacceptable:

- Medical case studies
- Individual claim files
- Clinical narratives

## Why This Module Exists (Plain Truth)

Veterans don’t fail claims because they’re lying.
They fail because the system demands structure they were never taught.

This module exists to expose that structure without pretending to be a doctor or the VA.

## Relationship to Other Modules

- Intake: supplies high-level context only
- Strategy: remains separate and conservative
- Docs: stores process artifacts only
- Auernyx Agent: enforces refusals and guardrails

## Completion Criteria

This module is “done” when:

- It reliably flags evidence gaps
- It refuses unsafe analysis
- It helps humans ask better questions without answering them

Nothing more.

---

If you want next, we can:

- Define the CRA JSON schema
- Add refusal test cases
- Integrate this as a review mode in VS Code

But this spec is the foundation.
