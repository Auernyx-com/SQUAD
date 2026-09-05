# Evidence — Obsidian Judgment Clear-Gating

- clear_judgment() refuses to clear on core/author tamper unless restoration proof exists and sha256 matches local file.
- Emits audit event: judgment.clear_refused with reason codes:
  - restoration_proof_missing
  - restoration_proof_ref_missing
  - restoration_proof_hash_mismatch

Originally written 2026-01-05 (commit `583ab9d716632684bd957b78894df300fedf5c1f`,
branch `governance/wip-provenance-mismatch`) but never merged. Found via a
top-down review of stale branches on 2026-09-05, verified the vulnerability
was still live in `main` with a direct probe (a `governance_hash_mismatch`
judgment — the most severe failure code this module has — could be cleared
with zero verification), and merged the fix.

## Follow-on: the same bypass was reachable through rotate_genesis_record()

Found later the same day during a full audit of this module. `clear_judgment()`
was gated correctly, but `rotate_genesis_record()` — the function that
rewrites the trusted genesis baseline to match whatever governance files
exist right now — had no gate at all beyond a `confirm=True` flag. Confirmed
with a direct probe: tamper a governance input file, activate the resulting
`governance_hash_mismatch` judgment, confirm `clear_judgment()` correctly
refuses with no proof (the fix above working as intended) — then call
`rotate_genesis_record(confirm=True)` anyway. It succeeded with zero
verification, silently rewriting the genesis record to accept the
*still-tampered* files as the new legitimate baseline. `verify_provenance()`
then reported `ok=True` on the very next call, while `judgment.v1.json`
was left behind with `active: true` — an orphaned, contradictory record
next to a system that now believed everything was fine.

Fixed by having `rotate_genesis_record()` refuse (raising `RuntimeError`,
audited as `genesis.rotate_refused`) whenever an active tamper-classified
judgment exists — the same `_restoration_required()` check `clear_judgment()`
already uses. Legitimate rotation (no active judgment, or a judgment already
cleared via a verified `restoration_proof`) is unaffected.
