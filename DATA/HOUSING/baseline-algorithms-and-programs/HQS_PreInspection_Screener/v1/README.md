# HQS Pre-Inspection Screener (v1)

Pre-screen module to reduce wasted showings by flagging predictable HQS/HUD-VASH failure risks from listing info + photos + your answers.

## Output

- `hqsStatus`: `PASS_LIKELY` | `FAIL_LIKELY` | `UNKNOWN` | `PASS_WITH_FIXES`
- `failReasons[]`, `fixableItems[]`, `unknownItems[]`, `showingChecklist[]`
- `confidence`: `LOW` | `MED` | `HIGH`

## Run demo

From this folder:

- `C:/Projects/SQUAD/DATA/HOUSING/.venv/Scripts/python.exe .\HQS_PreInspection_Screener_v1.py`

## Determinism notes

- This is a pre-screen only; real HQS inspection controls.
- v1 does not auto-fail “wood heat” or “hotplate-only” because PHA policies vary.
- v1 includes `utilities.hasWorkingHeat` so “no heat” can be expressed directly.
- v1 treats `leaksWaterDamage=yes` as a hard-fail signal (commonly maps to active leak/rot).

## Roadmap (optional, v2 ideas)

- Split `leaksWaterDamage` into `activeLeak` vs `historicalWaterDamage` to separate cosmetic staining from active failures.
