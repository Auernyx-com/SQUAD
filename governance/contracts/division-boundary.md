# Division Boundary Contract

Mirrors the Mk2 branch-boundary contract one level down.

## Rules

- Divisions must not assume SQUAD Battalion internal paths.
- Divisions must not import SQUAD Battalion code directly.
- SQUAD Battalion must not vendor or copy Division code.
- All integration occurs via /consumers/divisions/*.
- Every Division invocation is receipted through the Ygg ledger.
- Every Division genesis record must carry the founding law SHA-256.

## Founding law reference

All Divisions are bound by `GOVERNANCE/LAWS/veteran_data_sovereignty.v1.md`
SHA-256: dc0fcb428e24948c5471798bf3c0b77cafade1c68e1aecb39aa13eef264f2f87

A Division without this reference in its genesis record is not recognized.
