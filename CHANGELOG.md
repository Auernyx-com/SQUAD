# Changelog

## 2025-12-20 — Harden baseline scripts and verification

- Merged `verify/harden-baseline-scripts` into `main` (commit 88eaf63).
- Changes:
  - Added ShouldProcess support and safer path handling to `scripts/Invoke-BaselineClerk.ps1`.
  - Hardened `scripts/modules/Invoke-BaselineStateCapture.ps1` (relative-paths, TrimStart fixes, verbose output).
  - Standardized `.sha256` output format and improved logging.
  - Added `artifacts/reports/verification-20251220-193811.md` with PRE/POST capture comparison.
  - Included `artifacts/psscriptanalyzer_output.txt` showing analyzer run results.

See `artifacts/reports/verification-20251220-193811.md` for details.
