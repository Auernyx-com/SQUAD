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
