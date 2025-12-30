# Baseline Ritual Checklist

Baseline artifacts are ledger-grade assets. Tooling convenience never overrides baseline authority.

## Daily ritual (end of day)

1. Baseline PRE check
   - `py_compile` / minimal demos for touched modules
   - Ensure no `__pycache__/` or build outputs are staged

2. Hash (PRE)
   - Generate SHA-256 manifest for the baseline subtree

3. Commit
   - Commit only intended baseline subtree changes
   - Review `git status` for scope creep

4. Baseline POST check
   - Re-run `py_compile` / minimal demos

5. Hash (POST)
   - Generate SHA-256 manifest again

6. Push
   - Push commits to the authoritative baseline remote

## Governance checkpoints

- License intent verification (required)
  - Confirm license matches governance intent (default: proprietary / all-rights-reserved)
  - Audit tool-generated files after repo initialization (GUI defaults can be wrong)

- Untracked files review
  - Untracked files do not block commits, but must be reviewed to prevent accidental inclusion
