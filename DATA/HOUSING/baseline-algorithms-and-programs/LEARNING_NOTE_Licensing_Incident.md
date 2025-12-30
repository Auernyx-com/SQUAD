# Auernyx Learning Note: Baseline Repo + Licensing Incident

## Context

A baseline repository (`baseline-algorithms-and-programs`) was created locally first and later published via GitHub Desktop.

GitHub Desktop auto-added an MIT license, which conflicted with the intended proprietary / all-rights-reserved status of baseline artifacts.

## What went wrong

- Tool default behavior (GitHub Desktop) introduced a permissive open-source license without explicit confirmation.
- Repo initialization tooling can override governance intent if not constrained.

## Corrective actions taken

- Removed the MIT license file.
- Added a proprietary license (`LICENSE.txt`) with All Rights Reserved language.
- Committed the proprietary license.
- Confirmed repo integrity before push.

## Key principles learned

- Licensing is governance, not metadata.
- Never allow tooling defaults to decide legal posture.
- Baseline artifacts default to closed/proprietary unless explicitly declared otherwise.

## Future safeguards

- Disable auto-license unless license intent is confirmed.
- Immediately audit generated files after repo creation.
- Add a pre-push checklist item: confirm license matches governance intent.

## Canonical rule

Baseline governs consumers. Consumers do not govern baseline.
Tooling convenience never overrides system authority.

## Action item

Add “License intent verification” to the baseline ritual checklist.
