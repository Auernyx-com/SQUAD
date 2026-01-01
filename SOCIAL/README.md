# SOCIAL (governed)

This folder is a governed “social ops” workspace: it converts **local source text** into **policy-constrained drafts** and (optionally) a **scheduler-ready queue artifact**. The tool never posts, replies, scrapes, or calls external APIs; it only produces traceable artifacts from the files you provide under explicit policy constraints.

## Contract (one paragraph)
`Invoke-SocialDrafts.ps1` reads a single local source file, loads an account policy from `SOCIAL/policy.*.json`, generates deterministic draft text, and writes audit-friendly artifacts (draft markdown + receipts). Queue export is **blocked unless** `-Confirm APPLY`, and is **refused** if any draft fails policy checks. Draft headers include `source_sha256` and `policy_sha256` so a copied draft remains self-auditing.

## What is committed vs ignored
Committed (reviewable, long-lived):
- `SOCIAL/policy.squad.json`
- `SOCIAL/policy.auernyx.json`
- `SOCIAL/README.md`
- `SOCIAL/examples/` (static examples only)
- `Invoke-SocialDrafts.ps1` (repo root entrypoint)

Ignored by default (generated/local artifacts):
- `SOCIAL/DRAFTS/` (generated drafts)
- `SOCIAL/RECEIPTS/` (per-draft receipts)
- `SOCIAL/QUEUE/` (scheduler/export artifacts)
- `SOCIAL/SOURCES/` (local inputs)

(See `.gitignore` for the enforced ignore rules.)

## Folders
- `SOCIAL/SOURCES/` — inputs you draft from (local-only)
- `SOCIAL/DRAFTS/` — generated drafts with audit headers (local-only)
- `SOCIAL/RECEIPTS/` — JSON receipts with hashes + checks (local-only)
- `SOCIAL/QUEUE/` — export/scheduler artifacts (local-only; requires APPLY)
- `SOCIAL/examples/` — committed examples that demonstrate format
