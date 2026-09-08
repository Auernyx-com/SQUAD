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

## Follow-on: the restoration_proof check was itself a tautology (PR #38, critical)

Found later the same audit. The `restoration_proof` gate above (ref + SHA-256)
only proved some real file matched its own real hash — trivially true of
*any* file paired with its own digest. It never checked that the actual
tampered file had been restored to anything. Confirmed with a direct probe:
tamper a real governance file, let the judgment activate, then craft a
`restoration_proof` pointing to a completely unrelated, untouched file plus
that file's own real hash. `clear_judgment()` returned `True` and
`is_judgment_active()` went `False` — while `verify_provenance()` still
reported the same tamper immediately afterward. The alarm was silenced with
the tamper still in place, and `rotate_genesis_record()` would have laundered
it into a new trusted baseline on the next call.

Fixed by having `clear_judgment()` re-run `verify_provenance(repo_root)`
after the ref/sha checks and refuse unless governance state actually matches
genesis *right now*. ref/sha remain a required audit trail but no longer
stand in for verification. Verified both directions: the bypass scenario is
now correctly refused, and genuine byte-for-byte restoration still succeeds.

## Follow-on: the restoration-proof requirement only covered 1 of 4 real tamper codes (PR #46, critical)

Found later the same audit (2026-09-06). `_restoration_required()` — the
function both `clear_judgment()` and `rotate_genesis_record()`'s refusal
gate depend on — only special-cased the literal string
`"governance_hash_mismatch"`. `verify_provenance()` can also fail with
`genesis_hash_mismatch`, `project_id_mismatch`, or `genesis_parse_error` — all
of which fire on an *existing* genesis record and mean it was tampered with
or corrupted (`genesis_hash_mismatch` specifically means the trust anchor
itself doesn't match its own recorded hash), at least as severe as
`governance_hash_mismatch`. Those three previously required zero restoration
proof: `clear_judgment()` cleared them unconditionally, and
`rotate_genesis_record()` would then launder a still-tampered governance file
into a new "clean" baseline. Confirmed directly with a probe: forged a
self-consistent genesis record with `project_id` changed (hash recomputed to
match — a realistic attacker step, since the hash function is public source
in this file) alongside a tampered governance file; `clear_judgment()`
cleared it with no proof at all, and `verify_provenance()` reported `ok=True`
after rotation with the malicious content still on disk.

Fixed by extending `_restoration_required()` to treat any non-empty failure
code other than `genesis_missing` as tamper requiring proof.
`genesis_missing` stays deliberately excluded — an uninitialized repo (no
genesis record ever written) is not tamper. See `_restoration_required()`'s
own docstring in `src/obsidian_judgment.py` for the current, authoritative
version of this logic.
