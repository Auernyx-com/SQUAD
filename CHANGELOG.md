# Changelog

## 2026-09-04 to 2026-09-08 — Independent Security & Correctness Audit

A multi-day, multi-round independent audit (fresh-agent cold reads, every finding
reproduced with a real probe before being called a bug, test coverage added
alongside every fix) across all 8 division routers, the intake/coordinator
bridge, the alteration-gate CI governance layer, and Obsidian Judgment's
provenance mechanism. 62 PRs (#13–#74), all merged. No high/mid-tier bugs
outstanding as of the last round.

**Division wiring & routing correctness**
- #13 — 3 of 8 divisions were silently non-functional since May (never wired
  into the coordinator's routing table)
- #16 — Marine Corps and Guard veterans got zero branch-specific emergency
  resources
- #17 — homeless women veterans got an enrollment nudge instead of the crisis
  hotline
- #19 — multi-need veterans in Medical & Disability lost earlier guidance
- #35, #39 — `women_veterans_router.py` read the wrong housing field name
  entirely, then a fix for #35 broke the CLI's own copy of the field
- #37 — previously-denied veterans never saw the 1-year appeal deadline
- #48 — a previously-denied veteran got "file initial claim" as their primary
  path instead of the appeal track (high)
- #50 — the bridge never set `has_denied_claim`, blocking LEGAL's real
  VA-appeal track from ever firing
- #51 — the transportation crisis path was silently masked by ordinary
  transport tracks (critical)
- #52 — ToxicExposure never disclosed discharge limits on VA compensation
  (high)
- #53 — BusinessOpportunity told blocked veterans to apply for the cert
  they're blocked from (high)
- #54 — CRA never read `claim_status`; denied veterans got no appeal-deadline
  flag (high)
- #57 — Legal Track 1 (discharge upgrade) masked VTC/appeal urgency (high)
- #58 — WomenVeterans healthcare enrollment masked MST/maternity/mental-health
  tracks (high)
- #60 — VaBenefits' adaptive-housing threshold mismatched Housing's own (low)
- #65 — Transportation hardcoded a DAV number that had drifted from
  `contacts.py`'s canonical value (high)

**Crisis detection**
- #21 — a smart/curly apostrophe evaded self-harm crisis detection entirely
- #45, #47 — `crisis_redirect.py` had the same phrase-list gaps as
  pathfinder-worker, then a round-2 pass found more method-specific phrases
  still missed
- #71 — combat-narrative false positives (a veteran describing their own
  service history) were being flagged as active crisis risk (medium)
- #72 — the do-not-guess intake gate's 2-need cap silently dropped "crisis"
  whenever it wasn't named among the first two needs (high)

**Intake / coordinator bridge**
- #14 — the real questionnaire-to-coordinator translation bridge
- #22 — the do-not-guess intake gate crashed instead of asking a clarifying
  question
- #33 — `questionnaire_intake_bridge_v1.py` never forwarded
  `va_facility_issues`
- #36 — the bridge never populated `need_branches` or
  `is_survivor_or_dependent`
- #61 — the coordinator crashed on malformed intake, which could take the
  crisis path down with it (high)
- #62 — the coordinator silently dropped colliding domains, and confidence
  scoring was order-dependent (high)
- #63 — the bridge crashed on malformed location/discharge shapes (high)
- #66 — `pf_core_runner_v1`'s schema-failure path bypassed graceful
  fail-closed output (low)

**Governance / Obsidian Judgment / alteration-gate**
- #15 — `clear_judgment()` ignored tamper evidence entirely
- #20 — `rotate_genesis_record()` could silently launder an active tamper
  judgment
- #24 — rotated genesis to resync the governance baseline after the
  Pathfinder rename
- #26 — adopted Mk2's alteration-gate CI pattern as an independent proof of
  concept
- #38 — a critical bypass in `clear_judgment()`'s restoration-proof check
- #46 — the restoration-proof gate only covered 1 of 4 real tamper codes
  (critical)
- #68 — alteration-gate script injection, mere-request auth bypass, a
  local-resource false-verified label, silent CLI crashes, and a QA scan
  undercount, all in one pass (high)
- #69 — authorization records were never verified as actually coming from the
  real auto-authorize job (critical)
- #70 — the governance hash never protected `allowlist.json` — a complete
  self-authorization bypass (critical)

**Local resource wiring**
- #40 — shared local-resource lookup helper (`MODULES/_shared/`)
- #41 — wired local-resource lookup into all 8 division routers
- #42 — 4 CLIs never prompted for county, one never prompted for location at
  all

**Ledger / data integrity**
- #18 — the nonprofit registry rejected every real shard; added mental-health
  crisis-widening
- #23 — unverified phone numbers, including a DV crisis line, were reaching
  search output
- #25 — Yggdrasil ledger crash recovery + full hash-chain verification
- #59 — `verify_before_production` exclusion only recognized one JSON shape
  (medium)
- #67 — `module.json` metadata drift; flagged a `contacts.py` duplicate
  number (low/medium)

**Security**
- #31 — `--case-id` path traversal in `pathfinder_cra/run_cra_v1.py`
- #32 — `-ExportCase` path traversal in `Invoke-SquadAdminClerk.ps1`

**Validation & QA**
- #27 — QA sweeps didn't exclude quarantine, and one only worked on Windows
  paths
- #44 — implemented VAL-007 (claims trace to inputs or verify-required)
- #49 — VAL-006's fraud branch used "warning" while the crisis branch uses
  "error" (high)
- #55 — VAL-008's invalid-confidence branch used "error" while config
  declares "warn" (medium)

**Housekeeping**
- #29 — `PathfinderHandshake`'s percent-sign out-of-scope regex never matched
- #30 — removed stale duplicate LOGIC files superseded by their live version
- #34 — removed a dead `_floor_contacts` list in `synthesize()`
- #56 — Clerk PowerShell `-join "\n"` bug and venv-python resolver
  inconsistency (low)

**Docs**
- #28 — README understated OBSIDIAN_JUDGMENT's actual scope
- #43 — corrected a stale `KNOWN_GAPS.md` test-suite claim, documented
  resource wiring
- #64 — logged INTAKE_DO_NOT_GUESS/coordinator-schema drift, corrected a
  stale JWT gap entry
- #73 — synced the governance-hash file list and `KNOWN_GAPS.md` with rounds
  8–12
- #74 — cross-referenced wyerd-squad's vault-XSS fix in `KNOWN_GAPS.md`
