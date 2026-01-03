# Forge Verification Checklist (Per-Module)

Use this checklist at the end of each module implementation (before calling it “done”).

## 1) Scope + Freeze
- The module is in the intended authoritative folder path (frozen v1/v2, etc.).
- The module name matches spec and is the single authoritative implementation (no duplicates).
- Inputs/outputs are stable and deterministic for identical inputs.

## 2) Functional Rules Verification
- All must-have rules from the spec are implemented.
- Any policy knobs have safe defaults (documented) and are wired into behavior.
- “UNKNOWN” behavior is correct: not over-failing, and produces explicit follow-up questions/actions.

## 3) Demo / Examples
- A runnable demo exists (or example payloads) that exercises:
  - At least one PASS/OK case
  - At least one FAIL case
  - At least one UNKNOWN / needs-info case
- Demo output is explainable (reasons / notes / checklist items) and stable.

## 4) Data Model + Serialization
- Dataclasses / enums compile cleanly (no field ordering errors).
- JSON example payload(s) validate the intended shape and cover required fields.
- Optional fields behave correctly when omitted.

## 5) Governance + Licensing
- Licensing posture is correct for the repo (baseline modules: proprietary unless explicitly changed).
- Local execution receipts (e.g., `.baseline/`) are ignored and not committed.
- No accidental third-party license files were introduced by tooling.

## 6) Repo Hygiene (Critical)
- No `.gitmodules` was added unintentionally.
- No submodules point to local filesystem paths.
- Remotes are correct:
  - **Rule:** SQUAD must never have a remote pointing at `baseline-algorithms-and-programs`.

## 7) Publish Boundary
- If this module is meant to be published externally:
  - Confirm the target repo and branch are correct.
  - Confirm no cross-repo pushes (baseline vs SQUAD) are possible.
- If this module is local-only:
  - Confirm no unintended remote changes were made.

## 8) Minimal Command Set (Optional)
Run these from the repo root:
- `git status -sb`
- `git remote -v`
- Run the module demo / smoke test (command depends on module)

Repo QA (recommended for any “done” claim):
- `powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\qa\Invoke-RepoCheck.ps1`

Optional CRA fixtures gate (schema-only; OFF by default):
- Enable by switch: `powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\qa\Invoke-RepoCheck.ps1 -ValidateCRA`
- Or enable by env var (current session): `$env:SQUAD_VALIDATE_CRA = '1'` then run RepoCheck

Phase 5 governed-change discipline (opt-in):
- `powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\qa\Invoke-RepoCheck.ps1 -StrictGoverned -ConfirmGoverned`

## Known Tooling Quirks
- VS Code “Problems” may report “Variable ‘args’ is an automatic variable…” in `tools/qa/Invoke-RepoCheck.ps1` even when there is no `$args` assignment.
  - Treat as an IDE/analyzer false-positive unless it affects runtime behavior.
  - PowerShell parse checks + governed QA are the authoritative gate.
- VS Code “Problems” may flag “unapproved verb” warnings for internal helper functions in PowerShell scripts (e.g., Clerk helpers).
  - This is a style warning, not a correctness failure.
  - Do not rename governance entrypoints just to satisfy the analyzer; treat as noise unless you are explicitly refactoring public APIs.

## Notes (fill in per module)
- Module:
- Version:
- Spec source:
- Demo command:
- Known limitations:
- Publish decision (local-only / publish to repo):
