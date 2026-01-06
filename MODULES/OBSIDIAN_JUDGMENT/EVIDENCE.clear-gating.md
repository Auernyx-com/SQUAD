# Evidence — Obsidian Judgment Clear-Gating

- clear_judgment() refuses to clear on core/author tamper unless restoration proof exists and sha256 matches local file.
- Emits audit event: judgment.clear_refused with reason codes:
  - restoration_proof_missing
  - restoration_proof_ref_missing
  - restoration_proof_hash_mismatch

Commit SHA: 583ab9d716632684bd957b78894df300fedf5c1f
