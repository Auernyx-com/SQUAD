# Listing Legitimacy Red Flags (v1)

Deterministic pre-screen module to flag common rental-listing legitimacy/scam warning signs from *what the listing says* and *what the contact is asking you to do*.

This is not a proof-of-scam tool. It produces:
- a coarse `legitimacyStatus`
- structured `redFlags[]`
- recommended `nextSteps[]`

## Output

- `legitimacyStatus`: `LEGIT_LIKELY` | `SCAM_LIKELY` | `UNKNOWN` | `NEEDS_VERIFICATION`
- `riskLevel`: `LOW` | `MED` | `HIGH`
- `riskScore`: integer 0–100
- `redFlags[]`: structured objects with `code`, `severity`, `evidence`
- `nextSteps[]`: actionable verification steps
- `notes[]`: deterministic trace notes

Interpretation:

- `legitimacyStatus` is the authoritative decision for downstream consumers.
- `riskLevel` is a coarse severity band derived from `riskScore` and may not perfectly align with `legitimacyStatus` in all cases (e.g., a single high-severity red flag can drive `SCAM_LIKELY`).

Schemas:

- Input: `schema_Listing_Legitimacy_RedFlags_v1.json`
- Output: `schema_Listing_Legitimacy_RedFlags_v1_output.json`

## Run demo

From this folder:

- `C:/Projects/SQUAD/DATA/HOUSING/.venv/Scripts/python.exe .\Listing_Legitimacy_RedFlags_v1.py`

Or with system Python:

- `python .\Listing_Legitimacy_RedFlags_v1.py`

## Run on your own JSON

From this folder:

- `python .\run_listing_legitimacy_redflags_v1.py --input .\example_input.json --pretty`
- `python .\run_listing_legitimacy_redflags_v1.py --input in.json --output out.json --pretty`

## Determinism notes

- Rules are intentionally simple and auditable.
- v1 treats “upfront payment required before viewing” and “payment via gift cards/crypto/wire” as high-severity indicators.
- v1 does *not* attempt web scraping, reverse-image search, or platform reputation scoring.

## Roadmap (v2 ideas, optional)

- Optional integration points for: county assessor lookup, phone/email reputation checks, reverse-image search results (as inputs), and platform policy enforcement.
