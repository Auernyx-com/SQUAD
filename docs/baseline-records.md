# SQUAD BAT — Baseline Records

SHA-256 receipts for each ÆSIR PRE/POST baseline run against this repo.
Runtime artifacts are gitignored — this file is the permanent git-tracked record.

## How to read this

Each baseline cycle has two entries: PRE (before work begins) and POST (after work is committed).
The SHA-256 values here are the hash of the `final.json` receipt in `.auernyx/receipts/<runId>/`.
A PRE→POST pair with no drift means the repo state is accounted for.
Any drift between PRE and POST that is NOT explained by committed changes is a flag.

## Where artifacts land

| Artifact | Path | Git-tracked |
|---|---|---|
| Receipt (per run) | `.auernyx/receipts/<runId>/final.json` | No (gitignored) |
| State capture | `artifacts/statecapture/<YYYYMMDD-HHMMSS>/` | No (gitignored) |
| This record | `docs/baseline-records.md` | Yes |

## Run record

---

### 2026-05-24 — SQUAD BAT beta launch session

**Context:** End of session. Landing page, feedback strip, coverage gap, Front Range shard, va_facility_issues visual check all complete. First beta links going out.

*No ÆSIR baseline run executed this session — baseline infrastructure not yet wired to Linux environment. PowerShell tool at `tools/baseline/baseline.ps1` delegates to `C:\baseline-algorithms-and-programs` (Windows). Linux equivalent pending.*

*Record this entry when first baseline PRE/POST is run against SQUAD on this machine.*

---

<!-- Template for future entries:

### YYYY-MM-DD — [Context label]

**Context:** [What changed this session]

- Baseline PRE receipt
  - runId: `<runId>`
  - file: `.auernyx/receipts/<runId>/final.json`
  - sha256: `<SHA256>`

- Baseline POST receipt
  - runId: `<runId>`
  - file: `.auernyx/receipts/<runId>/final.json`
  - sha256: `<SHA256>`

- Drift: [None / list any unexpected changes]

-->
