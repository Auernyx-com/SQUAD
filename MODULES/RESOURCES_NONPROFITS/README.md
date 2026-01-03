# Resources — Nonprofits Module

Single responsibility: **store, validate, search, and return** nonprofit resource records.

Hard constraints (non-negotiable):
- No ranking, scoring, recommendation, or “best”.
- No eligibility assessment.
- No outcome promises.
- Read-only registry at runtime.

Scope enforcement source:
- `GOVERNANCE/auernyx.nonprofit.scope.json`

## Sharded data layout (avoid one-file-to-rule-them-all)
- Country/state shards under `DATA/` (example):
  - `DATA/US/CO/western_slope.json`
  - `DATA/US/CO/denver_metro.json`

Loading strategy:
- If user location is known, load only the shard(s) that match.
- If unknown, load `INDEX/index.us.json` (optional) and ask for state/county/city.

## Schemas
- `SCHEMAS/nonprofit_record.schema.json` — single provider record
- `SCHEMAS/nonprofit_registry.schema.json` — shard/registry container

## Validation
- `VALIDATION/validate_registry.py`
  - Blocks prohibited fields (rank/score/rating/etc)
  - Enforces service taxonomy (controlled vocab)
  - Rejects prohibited phrases embedded in factual text fields

## Notes
- This module is designed to be large **via shards**, not via one monolith file.
- Use filters, not rankings.
