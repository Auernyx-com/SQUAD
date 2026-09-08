# Known Gaps

This document tracks what we know is incomplete, unverified, or not yet built.
It exists so that anyone reviewing this project sees the honest state before they
have to dig for it. Last updated: 2026-09-08.

---

## Data gaps

**48 of 50 states are skeleton shards.**
Colorado (Western Slope, Front Range) and Washington (Puget Sound) have verified
regional data. Every other state has a statewide skeleton: state VSO name/URL and
primary VAMC name/city, no verified phone numbers, no local nonprofit contacts.
This is intentional — we do not ship guessed data. These shards exist to give the
AI routing context; veterans in those states receive a clear notice and are routed
through national lines (1-877-4AID-VET, 1-800-827-1000, etc.) until local data
is confirmed.

**Verified means primary source, not LLM-generated.**
Every phone number in a production shard was pulled from an official website or
confirmed by a person. Numbers marked `verify_before_production` have NOT been
confirmed and will not be surfaced to veterans.

**Mesa County PHA payment standard.**
The housing division has the full voucher screening pipeline configured for Mesa
County. The actual PHA payment standard dollar figures (what HUD-VASH covers per
bedroom size) have not been pulled from the current Mesa County PHA schedule.
The screening flags this correctly but cannot give a dollar figure until those
numbers are entered.

**Denver Metro shard is a placeholder.**
`DATA/US/CO/denver_metro.json` exists in the index but has not been built out.
Veterans in Denver Metro fall back to the CO statewide shard.

**Local resource database is now wired into all 8 division routers (as of 2026-09).**
Previously the verified resource shards existed but nothing called them --
every division's output was national-lines-only regardless of what local data
was on file. `MODULES/_shared/local_resources.py` now does state-scoped shard
lookup (exact county match, falling back to fuzzy match via stdlib `difflib`
for misspellings) and every division merges its results into a dedicated
`key_resources` field, tagged `Local (verified): ...` so it is never
confused with AI-generated or national-line text. It only ever reads
already-`verify_before_production`-cleared records (see "Verified means
primary source" above), so this does not weaken that guarantee -- it just
makes the two states with real data (CO, WA) actually reach veterans. A
crisis/self-harm flag widens the tag set (pulls in more resource categories)
but never narrows or blocks other results -- additive only, by design. This
does not reduce the 48-skeleton-state gap above; it makes the fix for that
gap (adding verified data to a shard) actually take effect once it happens.

---

## Technical gaps

**Only 2 of 8 division routers use `MODULES/_shared/contacts.py`.**
Found via independent audit (2026-09-08): `contacts.py`'s own documented
policy is "When a number changes, fix it here only. One edit, all
divisions update" — but only `Housing_v0_1.py` and `Legal_v0_1.py`
actually `from contacts import ...`; the other 6
(`BusinessOpportunity`/`MedDisability`/`ToxicExposure`/`Transportation`/
`VaBenefits`/`WomenVeterans`) hardcode their own copies of national
numbers. This already caused one confirmed, fixed drift (Transportation's
DAV number diverged from `contacts.py`'s `DAV_SERVICE_LINE` — see PR
history). Fixed for that one instance; the broader gap (5 remaining
divisions still hardcode rather than import) is not fixed here — auditing
and migrating every hardcoded number across 5 files is a larger effort
than this pass covers. Logged so future drift is tracked as a known risk
class, not rediscovered from scratch.

**Housing division has no `cli/` directory.**
Every other division (`VA_BENEFITS`, `LEGAL`, `TRANSPORTATION`,
`TOXIC_EXPOSURE`, `WOMEN_VETERANS`, `MEDICAL_DISABILITY`,
`BUSINESS_OPPORTUNITY`) has a `cli/*.py` entry point alongside its
`module.json`; Housing has neither a working command-line entry point
for manual/ops use, matching its siblings. `module.json` was added in
this pass (bringing Housing to parity on that front), but writing an
actual CLI wrapper is a small feature addition, not a bug fix, so it's
logged here rather than done silently. No runtime effect — the
coordinator resolves entrypoints from `config/divisions.json` directly,
never from `module.json`/CLI.

**Automated test suite (as of 2026-09).**
24 test files now exist under `tests/`, covering: the Pathfinder handshake
out-of-scope filter, CRA case-ID path traversal, Obsidian Judgment provenance
enforcement, the shared local-resources helper (`MODULES/_shared/`), and
per-division routing/resource-wiring tests for all 8 divisions. This closes
the largest gap previously logged here. Not yet covered: end-to-end coverage
of discharge-gate routing and era-specific program surfacing across every
division in one pass — current tests are per-module/per-router, not a single
full-pipeline regression suite. Still a gap worth closing, just a smaller one
than "zero tests."

**AI model confidence is not calibrated.**
The confidence score (0–100) is calculated from a formula in the prompt, not from
empirical calibration against real outcomes. A score of 65% means "65% of intake
fields were provided" — not "65% chance this routing is correct." This distinction
is explained internally but not yet surfaced to reviewers in the UI.

**Session vault encryption details.**
The client-side session vault uses localStorage encryption. The key derivation
method and encryption algorithm have not been audited externally. Veterans are
told their data stays on-device — this claim is structurally correct but has not
been verified by an independent security review.

**Rate limiting uses KV, not Durable Objects.**
The rate limiter is IP-based with sliding windows stored in KV. Under high
concurrent load from a single IP, there is a small race window where more than
the allowed number of requests could slip through before the count is written.
For a beta-scale deployment this is acceptable. At production scale, Durable
Objects would eliminate this race.

**KV index append has a race condition.**
The feedback index (the list of all feedback IDs) is maintained with a
read-modify-write pattern on a single KV key. Two simultaneous feedback
submissions could both read the same index, both append, and one could
overwrite the other's entry. The individual feedback records are written
atomically and are not lost — only the index entry could be missed. Rate
limiting makes this unlikely in practice. Fix at production scale: use
Durable Objects for the index, or drop the index entirely and use KV list().

**CF_Authorization JWT verification — RESOLVED.**
Previously noted here: the `parseAccessJWT` helper read the CF Access
session cookie without verifying its signature against Cloudflare's public
keys. As of the pathfinder-worker repo's `access-verify.js`, this has been
replaced entirely with real signature verification (JWKS fetch, RSASSA-
PKCS1-v1_5 signature check, issuer/audience/expiry validation, fails closed
on any error). Confirmed via repo-wide grep in both wyerd-squad and
pathfinder-worker: `parseAccessJWT` no longer exists in either codebase.
Left here, corrected, rather than deleted outright, so anyone who searched
for this specific gap by name still finds it and its resolution.

**`MODULES/INTAKE_DO_NOT_GUESS` is built and tested but not wired into the
live coordinator path.**
Found via independent audit (2026-09-07): the module (a gate meant to
"force missing basics" before routing proceeds) has its own working
Python API, CLI, and test suite (`tests/test_intake_gate.py`), but
`pf_coordinator_v1.py`, `questionnaire_intake_bridge_v1.py`,
`pf_core_runner_v1.py`, and all 8 division routers never import it —
confirmed via repo-wide grep. In the live path, the bridge instead
silently defaults missing fields (e.g. `housing_status`/`claim_stage`/
`employment_status` → `"unknown"`, `county` → `""`) rather than routing
to this module's clarifying-question gate. Not fixed by wiring it in as
part of that same audit pass — doing so would change what response a
veteran with an incomplete intake actually receives (a clarifying-
question gate instead of a routed-with-caveats result), which is a
product decision, not a narrow bug fix. Logged here so it's tracked as a
real, known gap rather than silently discovered again next round.

Update (2026-09-08, round 12): a real bug was found and fixed in this
module while it still sits unwired — `gate_intake()`'s 2-need cap
(`needs[:2]`) silently dropped `"crisis"` whenever it wasn't named among
the first two needs, with zero prioritization (PR #72). Fixed to always
keep `crisis` when present, regardless of ordering. Noted here so
whoever eventually wires this module in knows that specific landmine is
already cleared — the wiring decision above is still open.

**Coordinator result/intake JSON schemas have drifted from what the code
actually produces/consumes.**
Found via independent audit (2026-09-07): validating a real
`build_coordinator_intake()` output against
`AGENTS/SCHEMAS/Pathfinder_Coordinator_Intake_v1.schema.json` produces
violations (the schema's `Domain` enum is missing 7 of the ~12 domains
actually in use — `EMPLOYMENT`, `MEDICAL`, `CLAIMS`, `BUSINESS`,
`TRANSPORTATION`, `WOMEN_VETERANS`, `TOXIC_EXPOSURE`). Validating a real
`run_coordinator()` output against
`Pathfinder_Coordinator_Result_v1.schema.json` produces 9+ violations
(missing/renamed required keys, `confidence` typed as an int where the
schema wants an enum string, several unexpected top-level keys). Confirmed
via repo-wide grep that neither schema file is ever passed to
`jsonschema` anywhere in the codebase (the one real-validation tool,
`tools/qa/validate_pathfinder_contracts.py`, validates a *different*
schema, `Pathfinder_Contract_v1.schema.json`) — so this drift causes no
active bug today, but the two files provide zero real contract
protection and would reject virtually all real coordinator input/output
if validation were ever wired to them. Not fixed here — regenerating the
schemas from real output/input is straightforward but out of scope for
this pass; logged so it isn't silently rediscovered.

**No monitoring or alerting.**
There is no automated alerting if the worker errors, the AI binding returns
unexpected responses, or KV writes fail. Errors are logged to Cloudflare's
built-in log stream but not proactively surfaced.

**`validate_nonprofit_registry.py`'s --max-failures cap doesn't apply to
invalid-JSON shards.**
Found while fixing the adjacent scan-count bug (independent audit,
2026-09-07, round 7). The per-file loop's malformed-JSON branch does
`findings.append(...); continue` — that `continue` skips the
`len(findings) >= args.max_failures` check at the bottom of the loop
entirely, so a run of many unparseable shard files keeps scanning past
the cap (it never breaks early on JSON-parse failures alone, only on
`_validate_payload` findings). This doesn't undercount anything — if
anything it over-scans relative to the documented cap — so it wasn't
fixed as part of this pass's file-count fix, but the cap's behavior is
inconsistent between the two finding types and should be unified.

---

## Design gaps

**Congressional rep routing uses house.gov lookup — by design.**
Rep names are never hardcoded. This is correct and intentional, not a gap.
Noted here because reviewers sometimes flag it as missing data.

**The AI can still hallucinate phone numbers.**
The system prompt instructs the model to never give unverified numbers and to use
national routing lines when local numbers aren't known. This is enforced by
instruction, not by technical constraint. A sufficiently confident model response
can still produce a fabricated number. The VERIFY_BEFORE_PRODUCTION discipline in
the resource shards is the defense layer — if a number isn't in the shard, the
model is being asked to produce it from training data, which is unverified.
This is the most significant safety gap in the current architecture.

**Feedback loop is manual.**
When a veteran submits feedback flagging wrong or missing information, it goes to
a KV store and triggers an email. A human (currently just the project maintainer)
has to review it, verify the correction, and update the relevant shard. There is
no automated pipeline from feedback to shard update. This is appropriate for a
beta but will not scale.

---

## What is not a gap

- The `allowDirty` flag in wrangler config is an intentional dev bypass, not a
  security issue. Scheduled for removal before production.
- The landing page has no link to the tool. This is intentional — access is
  currently manually granted via email during the beta period.
- The 50-state statewide shards have no phone numbers. This is correct behavior,
  not missing data. National lines always work; local numbers are only added when
  confirmed from primary sources.
