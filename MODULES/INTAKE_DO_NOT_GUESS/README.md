# Intake — Do Not Guess Gate

Single job: **block progress until basics are present**.

If required basics are missing, output is **questions only** (no advice, no routing, no extra narrative).

## Required basics
- Location: state + county
- Need branch: pick 1–2 (`housing`, `claims`, `crisis`, `legal`, `education`)
- Current status (minimum): housed/unhoused + claim stage + employment status
- Contact preference: phone/email/in-person

## Interfaces
- Python API: `src/intake_gate.py`
- CLI: `cli/intake_gate_cli.py` (JSON in, JSON out)
