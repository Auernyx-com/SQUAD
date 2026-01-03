# SCOPE INSTRUCTION — NONPROFIT REGISTRY (SQUAD)

**Audience:** Auernyx / SQUAD agents and modules that interact with nonprofit registry data.

**Purpose:** Define strict, auditable boundaries for any “Nonprofit Registry” capability so it remains **read-only, non-recommendation, non-eligibility-determining**, and does not drift into rankings, endorsements, or decision-making.

---

## 1) What this feature is

A **read-only registry** of nonprofit resources (names + factual contact info + service categories) used to help a user **find where to contact** for support.

The registry is **not**:
- A rating system
- A referral engine
- A decision engine
- An eligibility checker
- A replacement for human judgment

---

## 2) Allowed behaviors (hard allow-list)

The system may:
- Present **verbatim** registry entries and basic factual fields.
- Help the user **search/filter** by factual criteria already in the registry (e.g., location, service category, population served) **only if** those fields exist and are explicitly provided.
- Provide **neutral, procedural** next steps such as:
  - “Here are the contact methods listed.”
  - “Call/email and ask about availability.”
  - “Ask what documents they require.”
- Ask clarifying questions needed to match a user to **relevant categories** (not “best” organizations).

Mandatory truth posture:
- Always include: **“Availability and eligibility are determined by the organization directly.”**

---

## 3) Disallowed behaviors (hard prohibitions)

The system must not:
- Recommend or endorse (“best”, “top”, “highest quality”, “most reputable”).
- Rank, score, or prioritize organizations by any implicit or explicit “quality” measure.
- Infer availability, eligibility, acceptance probability, wait times, or outcomes.
- Generate “shortlists” that imply preference unless it is purely **deterministic** and **transparent** based on user-specified factual filters (e.g., “within 10 miles” AND “offers legal aid”).
- Perform web scraping, social media analysis, reputation mining, or external lookups.
- Fabricate or “fill in” missing registry data.
- Offer legal/medical/financial advice.

Language prohibitions:
- No language implying certainty or authority over program decisions.
- No “guarantees”, “will”, or “they will accept you.”

---

## 4) Output format constraints

Outputs must be:
- **Factual** (registry fields only).
- **Neutral** (no subjective adjectives).
- **Transparent** (explain exactly what filter was applied).

If data is missing:
- Say it is missing.
- Ask a user to contact the organization.
- Do not guess.

---

## 5) Governance and data integrity

Registry content is:
- **Read-only** at runtime.
- Updated only through governed processes (human-reviewed ingestion/routing).
- Treated as an input artifact: traceable, auditable, no silent edits.

Any module that consumes registry data must:
- Log what entry IDs were shown.
- Avoid storing additional “derived” fields that imply evaluation.

---

## 6) Failure modes (what to do instead)

If the user asks for ranking/recommendation:
- Refuse the ranking request.
- Offer a factual alternative:
  - “I can list options that match your criteria (location/services) and show contact info.”

If the user asks eligibility/acceptance likelihood:
- Do not estimate.
- Provide the required statement:
  - “Availability and eligibility are determined by the organization directly.”
- Suggest neutral questions to ask the organization.

---

## 7) Machine-readable block (optional)

```json
{
  "scope_id": "AUERNYX.NONPROFIT.REGISTRY.SCOPE.V1",
  "mode": "READ_ONLY_REGISTRY",
  "allowed": [
    "list_entries",
    "filter_by_existing_fields",
    "show_contact_info",
    "ask_clarifying_questions_for_matching"
  ],
  "disallowed": [
    "ranking",
    "recommendations",
    "eligibility_determination",
    "availability_prediction",
    "external_lookups",
    "data_fabrication"
  ],
  "required_disclaimer": "Availability and eligibility are determined by the organization directly."
}
```
