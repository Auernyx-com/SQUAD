# Copilot instructions for SQUAD

VS Code/Copilot supports repository instructions via `.github/copilot-instructions.md`. When instruction files are enabled, VS Code automatically applies these instructions to Copilot Chat requests in this workspace. This makes repo workflow rules (Clerk entrypoint authority, baseline PRE/POST ritual, artifact routing) discoverable and auditable as versioned code, instead of living in a transient chat.

## Big picture (read this first)
- SQUAD is **artifact-driven** and optimized for auditability under stress; “helpful” shortcuts that break traceability are considered defects.
- The repo-root **Admin Clerk** PowerShell script is the constitutional doorway for governance, routing, and audit trails:
  - Authoritative entrypoint: [Invoke-SquadAdminClerk.ps1](Invoke-SquadAdminClerk.ps1)
  - Any other instance (e.g., [SYSTEM/CLERK/Invoke-SquadAdminClerk.ps1](SYSTEM/CLERK/Invoke-SquadAdminClerk.ps1)) is **non-authoritative** and must either call into the root Clerk or be byte-for-byte identical and documented as a mirror.
- Housing pipeline modules are intentionally separated with strict decision boundaries. See [PIPELINE_README.md](PIPELINE_README.md).

## Non-negotiables (repo conventions)
- Prefer using the Clerk for creating/routing artifacts; outputs without traceable inputs are invalid. See [README.md](README.md).
- Respect governance boundary: SQUAD must not push to the baseline repo; see [DOCS/GOVERNANCE.md](DOCS/GOVERNANCE.md).
- Do not add “cross-boundary” decisions to modules (e.g., legitimacy module must not decide eligibility). Follow [PIPELINE_README.md](PIPELINE_README.md).

## Baseline ritual (required workflow)
- Start-of-session: run [launchers/SQUAD_BASELINE_PRE.cmd](launchers/SQUAD_BASELINE_PRE.cmd).
- End-of-session: run [launchers/SQUAD_BASELINE_POST.cmd](launchers/SQUAD_BASELINE_POST.cmd).
- Repo-local shim delegates to external baseline tool at `C:\baseline-algorithms-and-programs\baseline.ps1`: [tools/baseline/baseline.ps1](tools/baseline/baseline.ps1).

## BattleBuddy (contract-driven)
- BattleBuddy consumes a **Contract v1 JSON envelope** and returns an output envelope.
  - Schema: [AGENTS/SCHEMAS/BattleBuddy_Contract_v1.schema.json](AGENTS/SCHEMAS/BattleBuddy_Contract_v1.schema.json)
  - Runner: [AGENTS/CORE/BATTLEBUDDY/bb_core_runner_v1.py](AGENTS/CORE/BATTLEBUDDY/bb_core_runner_v1.py)
  - “Cite or caveat” truth gating: [AGENTS/CORE/BATTLEBUDDY/bb_truth_v1.py](AGENTS/CORE/BATTLEBUDDY/bb_truth_v1.py)
  - Enabled modules/config: [SYSTEM/CONFIG/auernyx.battlebuddy.config.v1.json](SYSTEM/CONFIG/auernyx.battlebuddy.config.v1.json) and [AGENTS/CORE/BATTLEBUDDY/module_registry.v1.json](AGENTS/CORE/BATTLEBUDDY/module_registry.v1.json)
- When extending BattleBuddy:
  - Keep logic **envelope-only** (no external fetches inside truth/plan logic).
  - Use the existing stage model (`STABILIZE` → `TRACK_FOLLOW_UP`) and avoid introducing new stages unless schema + governance docs are updated.

## Artifacts and routing
- Case work lives under:
  - [CASES/ACTIVE](CASES/ACTIVE) (case state + per-case `ARTIFACTS/`)
  - [OUTPUTS/RUNS](OUTPUTS/RUNS) (run logs/exports)
- The Clerk routes files by extension (e.g., `.json` → `DATA/INTAKE`, `.pdf`/`.docx` → `DOCS/FORMS`, `.py` → `AGENTS/CORE`). See routing logic in [SYSTEM/CLERK/Invoke-SquadAdminClerk.ps1](SYSTEM/CLERK/Invoke-SquadAdminClerk.ps1).

## Guardrails (strict)
- Treat `OUTPUTS/` as write-protected: do not create or edit files under `OUTPUTS/` by hand. Only generate outputs via governed runs (e.g., Clerk/BattleBuddy) so outputs always have traceable inputs.
- For any routing/move operation with `-InPath`, require a dry-run first: run the Clerk with `-Plan` before the real move. No silent moves.

Example (required pattern):

1) Plan (no move):
`powershell -NoProfile -ExecutionPolicy Bypass -File .\Invoke-SquadAdminClerk.ps1 -InPath "C:\\path\\to\\file.pdf" -CaseId "PO_DEMO_GENERIC_0001" -Plan`

2) Execute (move):
`powershell -NoProfile -ExecutionPolicy Bypass -File .\Invoke-SquadAdminClerk.ps1 -InPath "C:\\path\\to\\file.pdf" -CaseId "PO_DEMO_GENERIC_0001"`

## Example: download VA forms (scriptable)
- Manifest: [DATA/LEGAL/va_forms_manifest.csv](DATA/LEGAL/va_forms_manifest.csv)
- Downloader: [DOCS/SCRIPTS/Invoke-VaFormsFetch.ps1](DOCS/SCRIPTS/Invoke-VaFormsFetch.ps1)
- Usage:
  - `powershell -NoProfile -ExecutionPolicy Bypass -File .\DOCS\SCRIPTS\Invoke-VaFormsFetch.ps1 -ManifestCsvPath .\DATA\LEGAL\va_forms_manifest.csv -OutDir .\DOCS\FORMS\VA`
  - Optional: set `VA_API_KEY` to enable VA Forms API resolution for non-insurance PDFs.

## Forms vs outputs (routing semantics)
- Downloaded VA forms are routed to `DOCS/FORMS/VA/` as canonical reference inputs.
- Case-specific completed/generated documents belong under `OUTPUTS/` (and/or `CASES/ACTIVE/<caseId>/ARTIFACTS/` when routed by the Clerk).

## How to make changes safely
- Prefer minimal, targeted edits; avoid reformatting unrelated files.
- When adding new modules/contracts, update:
  - schema in [AGENTS/SCHEMAS](AGENTS/SCHEMAS)
  - module registry in [AGENTS/CORE/BATTLEBUDDY/module_registry.v1.json](AGENTS/CORE/BATTLEBUDDY/module_registry.v1.json)
  - relevant docs in [DOCS](DOCS) / [PIPELINE_README.md](PIPELINE_README.md)
