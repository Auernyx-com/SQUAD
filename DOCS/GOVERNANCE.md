# SQUAD Governance

## Repo boundary
- **Rule:** SQUAD must never have a git remote pointing at the baseline repository (`baseline-algorithms-and-programs`).
- **Default posture:** keep SQUAD local-only until the publish boundary is explicitly defined.
- Baseline can be public/private as required; treat it as the authoritative baseline source of truth.

## Push safety guardrail (local)
This repo uses a local git `pre-push` hook to prevent accidental pushes to baseline.

- Hook path (local-only): `.git/hooks/pre-push`
- Behavior: rejects `git push` if the remote URL contains `baseline-algorithms-and-programs`.

Note: Git hooks are not versioned by default. If you clone this repo to a new machine, you must re-install the hook (or implement an equivalent guardrail) locally.
