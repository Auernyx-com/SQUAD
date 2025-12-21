#This repository is part of the ÆSIR governance toolchain and serves as the canonical baseline capture and verification layer for all ÆSIR-managed projects.#



\# Baseline Algorithms and Programs



\## Overview



This repository provides a \*\*repeatable, auditable baseline capture system\*\* used to detect and document system drift before and after work is performed.



It is designed for:

\- infrastructure work

\- forensic verification

\- governance enforcement

\- change accountability



This repository is \*\*foundational plumbing\*\*. Other projects depend on it.



---



\## What This System Does



The baseline system captures a snapshot of system state and produces:



\- Immutable, timestamped bundles

\- SHA-256 hash manifests

\- Drift reports comparing PRE → POST

\- Logs suitable for audit and review



It enforces \*\*verification over trust\*\*.



---



\## Core Concepts



\### PRE / POST Separation

\- \*\*PRE\*\* captures state \*before\* work begins.

\- \*\*POST\*\* captures state \*after\* work completes.

\- They are intentionally \*\*never run automatically together\*\*.



This prevents ambiguous or unsafe baselines.



\### Immutability

Each capture creates a new bundle.

Existing bundles are never modified.



\### Determinism

Given the same system state, captures are repeatable and verifiable.



---



\## Repository Layout

baseline.ps1 # Core baseline engine (single-phase execution)

Invoke-BaselineClerk.ps1 # Enforcement / coordination layer

Invoke-BaselineStateCapture.ps1 # Invocation wrapper



launchers/ # Double-clickable CMD entry points

docs/ # Documentation (workflow, design)

artifacts/ # Runtime output (gitignored)

logs/ # Runtime logs (gitignored)





---



\## Typical Workflow



\### 1. Run PRE (before work)

Double-click:



launchers/BASELINE\_PRE.cmd



This:

\- Captures current system state

\- Writes a PRE bundle under `artifacts/statecapture/`



---



\### 2. Perform Work

Make changes, edits, installs, or configuration updates.



---



\### 3. Run POST (after work)

Double-click:



launchers/BASELINE\_POST.cmd







This:

\- Captures post-work state

\- Verifies hashes

\- Generates drift reports

\- Flags unexpected changes



---



\## Expected Drift



Some files are expected to change between PRE and POST:



\- `manifest.json`

\- `hashes.sha256`

\- `run.log`

\- `processes.csv`

\- `systeminfo.txt`



The following should remain stable unless intentionally modified:



\- `env.txt`

\- `services.csv`

\- `scheduledtasks.csv`

\- `firewall\_profiles.txt`

\- `netip.csv`



Unexpected drift should be reviewed.



---



\## Security Notes



\- Windows Defender \*\*Controlled Folder Access\*\* may block baseline captures.

\- Allow-list `powershell.exe` and/or the repository path if needed.

\- All failures are logged in `run.log`.



---



\## What This Repository Is Not



\- Not application logic

\- Not CI/CD

\- Not a configuration manager

\- Not a replacement for version control



It exists to \*\*record truth\*\*, not interpret it.



---



\## Status



\- Operational

\- Mandatory for governed projects

\- Designed to be boring, reliable, and hard to misuse







