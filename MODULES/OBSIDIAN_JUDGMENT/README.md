# OBSIDIAN_JUDGMENT (v1)

A minimal provenance + governance-hash mechanism ported from `auernyx-agent-mk2` and adapted for SQUAD.

## What it is
- `genesis.v1.json`: a signed-by-hash record of the repo's governance baseline.
- `judgment.v1.json`: an optional "refuse" state (human-visible) that can be used to block privileged operations.
- `audit.ndjson`: append-only audit events for creation/activation/clear.

## What it is NOT
- It is not a decision engine.
- It does not alter files under `OUTPUTS/`.
- It does not fetch external data.

## Storage
All files live under `SYSTEM/META/PROVENANCE/`:
- `genesis.v1.json`
- `judgment.v1.json`
- `audit.ndjson`

## Governance hash inputs (SQUAD)
The governance hash is computed from the literal contents of a small allowlist of governance-critical files:
- `Invoke-SquadAdminClerk.ps1`
- `SYSTEM/CLERK/Invoke-SquadAdminClerk.ps1`
- `SYSTEM/CONFIG/squad.config.json`
- `.github/copilot-instructions.md`
- `DOCS/GOVERNANCE.md`
- `PIPELINE_README.md`
- `AGENTS/SCHEMAS/Pathfinder_Contract_v1.schema.json`

## CLI
- Status (JSON): `python MODULES/OBSIDIAN_JUDGMENT/cli/obsidian_judgment_cli.py status`
- Verify (JSON): `python MODULES/OBSIDIAN_JUDGMENT/cli/obsidian_judgment_cli.py verify`
- Create genesis (explicit): `python MODULES/OBSIDIAN_JUDGMENT/cli/obsidian_judgment_cli.py genesis --write`
- Clear judgment (explicit): `python MODULES/OBSIDIAN_JUDGMENT/cli/obsidian_judgment_cli.py clear --confirm YES`

Notes:
- If genesis is missing, verification returns `GENESIS_MISSING` (non-fatal by default in repo QA).
- Repo QA fails only when judgment is active, or when genesis exists but fails verification.
