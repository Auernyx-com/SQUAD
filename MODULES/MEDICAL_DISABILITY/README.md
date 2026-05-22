# MEDICAL_DISABILITY — SQUAD BAT Division Module

**Version:** 0.1.0 (Framework)
**Status:** Active — routing engine built, tracks defined, ready for data expansion

---

## Purpose

This module routes veterans to the correct medical and disability track.
It does not guarantee eligibility. It maps what the veteran shared against common program criteria and produces a specific, actionable guidance package.

Every veteran has medical and disability concerns. This is the highest-volume division in SQUAD BAT.

---

## Qualification Gate (First Check)

Before any routing occurs, discharge status is evaluated:

| Discharge Type | VA Healthcare | Disability Claims | Notes |
|----------------|---------------|-------------------|-------|
| Honorable | Full access | Full access | Standard path |
| General (Under Honorable) | Full access | Full access | Some programs require honorable |
| Other Than Honorable (OTH) | Limited | Limited | MST care available regardless; combat vets may qualify for 2-year healthcare window |
| Dishonorable | Barred | Barred | Discharge upgrade path only |

OTH is flagged but does not stop routing — the module identifies what programs remain accessible.

---

## Tracks

### 1. Healthcare Enrollment
**Who:** Veterans not yet enrolled in VA healthcare
**Form:** VA Form 10-10EZ
**Contact:** 1-877-222-8387 or va.gov/health-care/apply
**Key note:** Priority Group assignment affects copay level. 50%+ rating = Priority Group 1-3 (typically no copays).

### 2. Initial Disability Claim
**Who:** Veterans enrolled but not yet rated
**Form:** VA Form 21-526EZ
**Contact:** VA Regional Office or any VSO (DAV, VFW, American Legion — free)
**Key note:** Filing date = effective date. File early, add evidence later.

### 3. Rating Increase / Supplemental Claim
**Who:** Already rated, condition has worsened or new conditions developed
**Form:** VA Form 20-0995 (new evidence) or 21-526EZ (new condition)
**Key note:** New medical evidence (nexus letter, private C&P exam) significantly strengthens increase claims.

### 4. Appeals
**Who:** Recently denied or disagree with rating decision
- **Higher-Level Review (HLR):** Same evidence, senior reviewer. Must file within 1 year. VA Form 20-0996.
- **Supplemental Claim:** New evidence, no time limit. VA Form 20-0995.
- **Board of Veterans Appeals (BVA):** Three lanes — direct review, evidence submission, hearing. May take years but final administrative step.
- **CAVC:** Federal court, requires accredited attorney.

### 5. TDIU — Total Disability Individual Unemployability
**Who:** Can't work due to service-connected conditions; rated 60%+ single or 70%+ combined
**Form:** VA Form 21-8940
**Pays at:** 100% compensation rate even if not rated 100%
**Key note:** Many veterans qualify and don't know it exists.

### 6. SMC — Special Monthly Compensation
**Who:** 100% rated or P&T; loss of use, need aid and attendance, or housebound
**Levels:** K through R2 (increasing severity = increasing payment)
**Key note:** Must be evaluated — it is not automatically applied.

### 7. Aid & Attendance
**Who:** Needs regular help with daily activities; in-home care or assisted living
**Form:** VA Form 21-2680
**Key note:** Can stack with disability compensation.

### 8. Caregiver Support (PCAFC)
**Who:** Family member providing substantial caregiver services to eligible veteran
**Provides:** Monthly stipend, health insurance, mental health support for caregiver
**Contact:** VA Caregiver Support Line: 1-855-260-3274

### 9. Mental Health
**Who:** PTSD, TBI, MST, adjustment disorder, substance use, any mental health need
**Low-barrier entry:** Vet Centers — open to OTH discharge, no enrollment required for initial contact
**MST specific:** MST Coordinator at every VAMC; no discharge barrier for MST-related care
**TBI specific:** VA Polytrauma/TBI Network Sites

### 10. Discharge Upgrade
**Who:** OTH or dishonorable discharge blocking access to needed programs
**Route:** Discharge Review Board (DRB, within 15 years) or Board for Correction of Military/Naval Records (BCMR/BCNR)
**Free help:** Veterans legal clinics, National Veterans Legal Services Program (NVLSP)

---

## Key Forms Reference

| Form | Purpose |
|------|---------|
| 10-10EZ | Healthcare enrollment |
| 21-526EZ | Initial disability claim / new conditions |
| 20-0995 | Supplemental claim (new evidence) |
| 20-0996 | Higher-Level Review |
| 21-8940 | TDIU (Individual Unemployability) |
| 21-2680 | Aid & Attendance / Housebound |
| 21-686c | Add dependents to compensation |

---

## Universal Crisis Escalation

If crisis signals are detected at any point, CRISIS_REDIRECT module takes priority.
Veterans Crisis Line: Call or text **988**, then press **1**.

---

## Governance

This module operates under the SQUAD BAT Veteran Data Sovereignty Law (v1).
- No diagnosis data stored
- No SSN collected
- Routing decisions logged as operation type + outcome only
- Veteran holds their data via encrypted vault passphrase

---

## Growth Path

This is v0.1 — the framework. Planned expansion:
- Western Slope CO specific VAMC contacts and Vet Center locations
- State-level VA benefit supplements (Colorado has additional programs)
- C&P exam preparation guide module
- VSO locator by county
- Form pre-fill helper (what to bring, what to expect)
