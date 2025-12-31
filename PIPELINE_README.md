# SQUAD Housing Pipeline (v1)

This document defines the **pipeline order**, **decision boundaries**, and **human override points** for the current housing triad + outreach layer.

Goal: prevent “helpful” boundary collapse (e.g., a pre-screen module quietly making program eligibility decisions).

## Module order

1) **Listing Legitimacy** (`Listing_Legitimacy_RedFlags_v1`)
   - Purpose: filter scams/time-wasters and force verification when signals are unclear.

2) **Program Gate** (`ProgramGate_HUDVASH_HCV_S8`)
   - Purpose: feasibility math + hard disqualifiers (e.g., initial 40% cap, off-book side payments).

3) **HQS Pre-Inspection** (`HQS_PreInspection_Screener_v1`)
   - Purpose: inspection viability pre-screen and “what to check/fix before inspection.”

4) **Landlord Outreach Packet** (`Landlord_Outreach_Packet_v1`)
   - Purpose: produce ready-to-send factual templates + checklists using the gate outputs.

Recommended usage: run 1→3 as soon as you have enough input; run 4 once the unit is worth pursuing.

## What each module is allowed to decide

### 1) Listing Legitimacy
Allowed decisions:
- Flag red flags with evidence.
- Recommend verification next steps.
- Emit a conservative status (`LEGIT_LIKELY` / `NEEDS_VERIFICATION` / `UNKNOWN` / `SCAM_LIKELY`).

### 2) Program Gate
Allowed decisions:
- Compute gross rent / share estimates when inputs allow.
- Apply hard gates (PASS/FAIL) when the rule is deterministic.
- Emit `UNKNOWN` when required inputs are missing.
- Generate “Ask PHA” questions needed to resolve unknowns.

### 3) HQS Pre-Inspection
Allowed decisions:
- Pre-screen pass likelihood.
- Enumerate likely fail reasons, fixable items, and unknowns.
- Produce a showing checklist.

### 4) Landlord Outreach Packet
Allowed decisions:
- Render factual, standardized templates.
- Include checklists, timelines, fix lists.
- Include PHA questions when upstream indicates unknowns.

## What modules are NOT allowed to decide

These rules protect governance, safety, and auditability.

### Global non-authorities (apply to all modules)
- No legal determinations.
- No guarantees (no “will pass HQS,” “PHA will approve,” “this is definitely a scam”).
- No identity verification claims (no “owner verified”) unless an upstream human-recorded verification artifact is explicitly provided as an input.
- No web scraping, platform reputation scoring, or external lookups unless explicitly added as a separate module with an explicit contract.

### Cross-boundary prohibitions
- Listing Legitimacy must not approve/deny voucher feasibility.
- Program Gate must not claim the listing is legitimate.
- HQS Pre-Inspection must not claim program eligibility.
- Outreach Packet must not override the gates or “sell” beyond factual process explanation.

## Human override points (expected)

Human override is not failure; it is part of the design.

- **Legitimacy:** a human can proceed despite `NEEDS_VERIFICATION` only after completing verification steps (and recording what was verified).
- **Program Gate:** a human can proceed despite `UNKNOWN` by collecting missing PHA inputs; can challenge a FAIL only if an explicit policy exception exists and is documented.
- **HQS Pre-Inspection:** a human can proceed despite `UNKNOWN` by scheduling a showing/inspection and collecting evidence; can proceed with `PASS_WITH_FIXES` only if the fix plan is realistic.
- **Outreach:** a human can tailor tone/phrasing, but must not change facts or imply guarantees.

## Outputs and artifacts

- Each module output is an **artifact** meant to be saved alongside its input context.
- Downstream modules should treat upstream outputs as read-only inputs.
- When humans override a module, record: what was overridden, why, and what evidence supports the override.
