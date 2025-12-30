# Landlord Outreach Packet (v1)

Deterministic module that produces ready-to-send landlord outreach templates from the outputs of the three housing gates:

- Program feasibility (`ProgramGate_*` output)
- Listing legitimacy (`Listing_Legitimacy_RedFlags_v1` output)
- HQS pre-inspection (`HQS_PreInspection_Screener_v1` output)

This module does **not** do persuasion or "AI sales". It produces factual, standardized templates that reduce friction and clarify next steps.

## Outputs

- `landlordCallScript` (30–60 seconds)
- `smsTemplate`
- `emailTemplate`
- `docChecklist` (what landlord should provide)
- `fixList` (if HQS is `PASS_WITH_FIXES`)
- `timeline` (what happens when)
- `phaQuestions` (only when needed)

## Schemas

- Input: `schema_Landlord_Outreach_Packet_v1.json`
- Output: `schema_Landlord_Outreach_Packet_v1_output.json`

## Run demo

From this folder:

- `python .\Landlord_Outreach_Packet_v1.py`

Or run your own input:

- `python .\run_landlord_outreach_packet_v1.py --input .\example_input.json --pretty`

## Determinism notes

- No web calls, no scraping, no reputation scoring.
- All text is template-driven and parameter-filled.
- The gate outputs are treated as authoritative inputs.
