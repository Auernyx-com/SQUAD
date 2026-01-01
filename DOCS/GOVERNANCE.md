# SQUAD Governance

## Clerk authority invariant
- **Authoritative entrypoint:** `Invoke-SquadAdminClerk.ps1` at repo root is the only source of truth.
- **Delegate shim rule:** `SYSTEM/CLERK/Invoke-SquadAdminClerk.ps1` must remain a pure delegation wrapper and must never contain divergent logic.
- **Reason:** prevents shadow execution paths and keeps auditability + governance boundaries intact.

## Editor config policy (.vscode)
Editor config policy (.vscode): .vscode/settings.json may be tracked only to enforce repository contracts (e.g., JSON schema bindings for governed artifacts). No other editor preferences (theme/UI, formatting opinions, keybindings, extensions, personal workflow settings) are permitted in tracked .vscode files. If a setting is not required to validate or enforce a governed contract, it must remain untracked.

## Quarantine invariant
`SYSTEM/META/QUARANTINE/` is append-only evidence storage and must never be treated as valid runtime output; validators and runners must exclude it from normal processing.

## Auernyx roadmap
- See: `DOCS/AUERNYX_Governance_Roadmap_v1.md`

## Repo boundary
- **Rule:** SQUAD must never have a git remote pointing at the baseline repository (`baseline-algorithms-and-programs`).
- **Default posture:** keep SQUAD local-only until the publish boundary is explicitly defined.
- Baseline can be public/private as required; treat it as the authoritative baseline source of truth.

## Push safety guardrail (local)
This repo uses a local git `pre-push` hook to prevent accidental pushes to baseline.

- Hook path (local-only): `.git/hooks/pre-push`
- Behavior: rejects `git push` if the remote URL contains `baseline-algorithms-and-programs`.

Note: Git hooks are not versioned by default. If you clone this repo to a new machine, you must re-install the hook (or implement an equivalent guardrail) locally.
