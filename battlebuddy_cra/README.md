# BattleBuddy CRA (Claim Readiness Analysis)

Purpose: process-only readiness + evidence gap mapping for VA-style claims.

## Invariant (non-negotiable)
CRA analyzes **process completeness**, not health facts.

- No diagnosis/condition naming
- No medical inference or record interpretation
- No eligibility determination
- No outcome prediction (“likelihood of approval”)

## Refusal language (required)
If the input contains medical/clinical details, or the task asks for medical judgment or service-connection determination, CRA must refuse.

Standard refusal:
> I can’t analyze medical records or determine service connection. I can help identify common documentation or process gaps that affect claims outcomes.

## Schemas
- Input: `battlebuddy_cra/schema/cra.schema.json`
- Output: `battlebuddy_cra/schema/cra_output.schema.json`

## Examples
- Input example: `battlebuddy_cra/examples/example_input.cra.v1.json`

## Runner (local, no-fetch)
The CRA runner generates a schema-valid report from a CRA input payload.

- Run from repo root (explicit input + output path):
	- `powershell -NoProfile -ExecutionPolicy Bypass -Command "& .\.venv\Scripts\python.exe .\battlebuddy_cra\run_cra_v1.py --input .\battlebuddy_cra\examples\example_input.cra.v1.json --out C:\Temp\cra.report.v1.json"`

- Run against a case folder (default paths):
	- Place input at: `CASES/ACTIVE/<CASE_ID>/ARTIFACTS/CRA/cra.input.v1.json`
	- Then run: `powershell -NoProfile -ExecutionPolicy Bypass -Command "& .\.venv\Scripts\python.exe .\battlebuddy_cra\run_cra_v1.py --case-id <CASE_ID>"`
	- Output writes to: `CASES/ACTIVE/<CASE_ID>/ARTIFACTS/CRA/cra.report.v1.json` (with collision suffixes if needed)

## Privacy rails
Do not store PHI/PII in tracked text/code. Store VA/medical documents as case artifacts with redactions.
