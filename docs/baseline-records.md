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

### 2026-05-25 — GitHub hardening + gate fix + SQUAD BAT public launch prep

**Context:** Full session. Rate limiting deployed to pathfinder-worker (feedback/process/chat endpoints). CORS locked to squad.wyerd.org. READMEs written for wyerd-squad and SQUAD. AGPL v3 + veteran data handling terms added to both repos. KNOWN_GAPS.md written pre-review. r/codereview post live. wyerd-squad repo made public. Broken copilot-setup-steps.yml removed from auernyx-agent-mk2 (PR #133). Gate self-register fix merged (PR #134) — no more manual re-trigger commits ever.

*No ÆSIR baseline run executed — PowerShell tool is Windows-only, Linux equivalent pending.*

**POST artifact hashes — Linux SHA-256 (end of session):**

| File | SHA-256 |
|------|---------|
| wyerd-squad/index.html | `c8f3f44f9e92b8d34c5a612651a85951e32609edfc9d9f8953f7e23b0b2c8281` |
| wyerd-squad/tool/index.html | `0527e03c349e593979c127873690579c21b2ac531d34a2d657f43cd321e9cb4b` |
| wyerd-squad/README.md | `ae58e171a013fa2090f0bf48ab9b10681c1c357622a56adb8918bcea4d2399b4` |
| wyerd-squad/LICENSE | `0121d86a3b699bebe5138c78a935c303ebc2bf20fb9ad46e3cdda26a6aae96ca` |
| pathfinder-worker/worker.js | `110ba3581b12f2ca7d2a2f3d47a39a4b2f41b57316519509d0bc544641f1517d` |
| pathfinder-worker/wrangler.toml | `5098f70cee73d7ceaeae8839bf533073d0640c1fc8c4c5ef143ceb51bff2f046` |
| SQUAD/README.md | `560e4bd89bebe0872acf6aee6d865d84d4a64472793948b812edff3c5108552d` |
| SQUAD/LICENSE | `f138a70d8014b941db806ed51afadd31ed6a921787c85d81163f740a4a0c9e8c` |
| SQUAD/KNOWN_GAPS.md | `df1103fa03422895ca78225e795c17568bc83180b0092a5967f2065ef6d75b00` |
| SQUAD/MODULES/RESOURCES_NONPROFITS/INDEX/index.us.json | `911e9fa2d4c8550cee09859ff186cc502922cd7bcc5ed5ce459ec7085fd474fc` |
| auernyx-agent-mk2/.github/workflows/mk2-alteration-gate.yml | `d081e78dbfff8dc2d22f35e867014d9307189ac77e5d9f12f51d45c605c0243c` |

**Git HEAD at close:**

| Repo | Commit |
|------|--------|
| wyerd-squad | `562d706c2d04` |
| SQUAD | `3bef7f99543b` |
| pathfinder-worker | `f5b026da875c` |
| auernyx-agent-mk2 | `79e04717be2d` |

- Drift: None. All changes committed and pushed. All repos green.

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
