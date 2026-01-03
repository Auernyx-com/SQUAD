# CRISIS_REDIRECT (v1)

Minimal crisis-safe redirect module.

## Contract
- Input: JSON payload (free-form) with at least one of:
  - `text` (string)
  - `signals` (object of booleans)
- Output: JSON object with:
  - `status`: `OK` | `CRISIS`
  - `reason`: short string
  - `resources`: list of crisis resources (non-exhaustive)
  - `questions`: optional list of clarifying questions

## Behavior
- If clear self-harm / suicide intent or immediate danger is detected:
  - Return `status=CRISIS` and provide crisis resources.
  - Do not provide planning, tactics, or operational steps.
- If unclear:
  - Return `OK` with questions that help a human assess urgency.

## CLI
- JSON from file: `python MODULES/CRISIS_REDIRECT/cli/crisis_redirect_cli.py --in payload.json`
- JSON from stdin: `type payload.json | python MODULES/CRISIS_REDIRECT/cli/crisis_redirect_cli.py`

The CLI prints JSON to stdout.
