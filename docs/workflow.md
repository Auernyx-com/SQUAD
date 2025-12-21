\# Baseline PRE / POST Workflow



\## Purpose



This repository provides a \*\*repeatable, auditable baseline capture system\*\* for detecting system drift before and after work is performed.



The workflow is intentionally split into \*\*PRE\*\* and \*\*POST\*\* phases to preserve forensic integrity and prevent accidental or ambiguous captures.



---



\## Core Principles



\- \*\*Separation of phases\*\*  

&nbsp; PRE and POST are never run automatically together.



\- \*\*Immutability\*\*  

&nbsp; Each baseline capture produces a timestamped bundle that is never modified.



\- \*\*Verification over trust\*\*  

&nbsp; POST runs include hash verification and drift reporting.



\- \*\*Low cognitive load\*\*  

&nbsp; Operators should not need to remember flags or commands.



---



\## Directory Overview



launchers/ # Double-clickable CMD entry points

artifacts/ # Runtime capture output (ignored by git)

docs/ # Human-readable documentation

baseline.ps1 # Core baseline engine (single-phase execution)





---



\## Standard Daily Workflow



\### 1. PRE Capture (before work)



Run \*\*once\*\*, immediately before starting work.



\*\*Preferred method (recommended):\*\*

\- Double-click:

launchers/BASELINE\_PRE.cmd





\*\*What this does:\*\*

\- Captures current system state

\- Generates a PRE bundle under `artifacts/statecapture/`

\- Commits metadata if configured



---



\### 2. Perform Work



Make changes, edits, installs, or configuration updates.



Do \*\*not\*\* run POST until work is complete.



---



\### 3. POST Capture + Verification (after work)



Run \*\*once\*\*, after all work is finished.



\*\*Preferred method (recommended):\*\*

\- Double-click:



launchers/BASELINE\_POST.cmd







\*\*What this does:\*\*

\- Captures post-work system state

\- Verifies hashes against PRE

\- Generates a drift report

\- Flags unexpected changes



---



\## Expected Drift vs. Investigation



The following files commonly change between PRE and POST and are considered \*\*expected drift\*\*:



\- `manifest.json`

\- `hashes.sha256`

\- `run.log`

\- `processes.csv`

\- `systeminfo.txt`



The following files should remain stable unless intentional changes were made:



\- `env.txt`

\- `services.csv`

\- `scheduledtasks.csv`

\- `firewall\_profiles.txt`

\- `netip.csv`



Unexpected drift should be reviewed before proceeding.



---



\## Security Notes



\- Windows Defender \*\*Controlled Folder Access\*\* may block baseline captures.

\- Allow-list `powershell.exe` and/or the repository path if captures fail.

\- Failures and access issues are logged in `run.log`.



---



\## Design Notes



\- `baseline.ps1` executes \*\*one phase only\*\* (`pre` or `post`) by design.

\- Multi-phase automation is intentionally not implicit.

\- This prevents accidental POST runs and preserves audit clarity.



---



\## When to Commit



\- Source code and documentation are committed to git.

\- Runtime artifacts (`artifacts/`, `logs/`) are excluded via `.gitignore`.

\- Verification reports may be attached to PRs or exported separately.



---



\## Status



This workflow is \*\*mandatory\*\* for projects that require:

\- auditability

\- drift detection

\- forensic traceability







