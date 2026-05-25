# Known Gaps

This document tracks what we know is incomplete, unverified, or not yet built.
It exists so that anyone reviewing this project sees the honest state before they
have to dig for it. Last updated: 2026-05-25.

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

---

## Technical gaps

**No automated test suite.**
There are no unit tests, integration tests, or routing regression tests. Routing
correctness is verified manually through test intakes. This is the largest
engineering gap. A test suite covering: discharge gate routing, era-specific
program surfacing, crisis additive behavior, and coverage gap notice accuracy
would significantly reduce the risk of silent regressions.

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

**CF_Authorization JWT is parsed without signature verification.**
The `parseAccessJWT` helper reads the CF Access session cookie and trusts
the payload to display session expiry info. The signature is not verified
against Cloudflare's public keys. This does not gate any access — it only
surfaces a session expiry notice to the user — so the security impact is
minimal. A spoofed JWT payload could only change what expiry message the
user sees. Noted for completeness.

**No monitoring or alerting.**
There is no automated alerting if the worker errors, the AI binding returns
unexpected responses, or KV writes fail. Errors are logged to Cloudflare's
built-in log stream but not proactively surfaced.

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
