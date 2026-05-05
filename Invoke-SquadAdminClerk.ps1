<#
.SYNOPSIS
  Squad Admin Clerk — project governance + safe routing tool. v1.3

.DESCRIPTION
  - Enforces Squad directory structure
  - Safe routing with CaseId override + human-verification guards
  - Full audit trail with rotation and optional hashing
  - Single-instance lock, export packaging, plan/preview mode
  - Uses SYSTEM\CONFIG\squad.config.json if present

.NOTES
  Keep isolated. Modifications only with intent.
#>

[CmdletBinding(SupportsShouldProcess=$true)]
param(
  [Parameter(Mandatory=$false)]
  [string]$SquadRoot = $(if ($env:SQUAD_ROOT -and $env:SQUAD_ROOT.Trim()) { $env:SQUAD_ROOT } else { "C:\Projects\SQUAD" }),

  # Create/repair folder tree
  [switch]$Init,

  # Create baseline scaffold files (README, config, templates, etc.)
  [switch]$Scaffold,

  # Overwrite scaffold files if they already exist
  [switch]$ForceScaffold,

  # Route one file or a folder into Squad structure
  [string]$InPath,

  # Preview routing totals without moving
  [switch]$Plan,

  # Optional Case ID for case isolation
  [ValidatePattern('^[A-Z0-9_]+$')]
  [string]$CaseId,

  # Git init in REPO (OFF by default)
  [switch]$InitGit,

  # Log SHA256 after move
  [switch]$LogHash,

  # Export a case to ZIP for handoff
  [string]$ExportCase,

  # Run Auernyx Pathfinder (PF-Core) on a Contract v1 input envelope
  [string]$PathfinderInput,

  # Run CRA (Claim Readiness Analysis) for a case (schema-only, no-fetch)
  [switch]$CRARun,
  [string]$CRAInput,

  # Quarantine legacy OUTPUTS/RUNS artifacts that are invalid under current schemas.
  # This is a governed move OUT of OUTPUTS (no in-place editing).
  [switch]$QuarantineLegacyOutputs,

  # Lock break requires explicit authorization + reason (never silent)
  [switch]$BreakLock,
  [string]$BreakLockReason
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# --------------------------
# Helpers
# --------------------------

function Ensure-Dir {
  param([Parameter(Mandatory=$true)][string]$Dir)
  if (-not (Test-Path -LiteralPath $Dir)) {
    New-Item -ItemType Directory -Path $Dir -Force | Out-Null
  }
}

function Get-UniquePath {
  param(
    [Parameter(Mandatory=$true)][string]$Path
  )

  if (-not (Test-Path -LiteralPath $Path)) { return $Path }

  $parent = Split-Path -Parent $Path
  $leaf = Split-Path -Leaf $Path

  $n = 1
  do {
    $candidate = Join-Path $parent ($leaf + '__' + $n)
    $n++
    if ($n -gt 999) { throw ('Collision limit exceeded for: {0}' -f $Path) }
  } while (Test-Path -LiteralPath $candidate)

  return $candidate
}

function Read-JsonFile {
  param([Parameter(Mandatory=$true)][string]$Path)
  $raw = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
  return ($raw | ConvertFrom-Json)
}

function Get-StringLengthOrMinus1 {
  param([object]$Value)
  if ($null -eq $Value) { return -1 }
  if (-not ($Value -is [string])) { return -1 }
  return $Value.Length
}

function Resolve-SafePath {
  param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$Path
  )
  $rootFull = [System.IO.Path]::GetFullPath($Root)
  $pathFull = [System.IO.Path]::GetFullPath($Path)

  if (-not $pathFull.StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw ("Unsafe path: {0} escapes root {1}." -f $Path, $Root)
  }
  return $pathFull
}

function Write-ClerkLog {
  param(
    [Parameter(Mandatory=$true)][string]$LogDir,
    [Parameter(Mandatory=$true)][string]$Message,
    [ValidateSet("INFO","WARN","ERROR")][string]$Level="INFO"
  )
  if ($script:ClerkPlanReadOnly) { return }
  Ensure-Dir $LogDir

  $logFile = Join-Path $LogDir "clerk.log"

  # Rotation at ~10MB, keep last 5 backups
  if ((Test-Path -LiteralPath $logFile) -and ((Get-Item -LiteralPath $logFile).Length -gt 10MB)) {
    $ts = (Get-Date).ToString("yyyyMMdd_HHmmss")
    $bak = Join-Path $LogDir ("clerk.log.{0}.bak" -f $ts)
    Rename-Item -LiteralPath $logFile -NewName (Split-Path -Leaf $bak) -Force

    Get-ChildItem -LiteralPath $LogDir -Filter "clerk.log.*.bak" |
      Sort-Object CreationTime -Descending |
      Select-Object -Skip 5 |
      ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
  }

  $ts2 = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
  Add-Content -LiteralPath $logFile -Value "[$ts2][$Level] $Message" -Encoding UTF8
}

function Get-FileSha256 {
  param([Parameter(Mandatory=$true)][string]$Path)
  (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Get-PythonExeForRuns {
  param([Parameter(Mandatory=$true)][string]$Root)

  $venvPy = Join-Path $Root '.venv\Scripts\python.exe'
  if (Test-Path -LiteralPath $venvPy) { return $venvPy }

  $pythonCmd = (Get-Command python -ErrorAction SilentlyContinue)
  if ($pythonCmd) { return 'python' }

  throw 'Python not found. Create .venv or add python to PATH.'
}

function Assert-ObsidianProvenanceOk {
  param(
    [Parameter(Mandatory=$true)][string]$Root
  )

  $check = Join-Path $Root 'tools\qa\check_obsidian_judgment.py'
  if (-not (Test-Path -LiteralPath $check)) {
    throw ('Missing provenance checker: {0}' -f $check)
  }

  $pythonExe = Get-PythonExeForRuns -Root $Root

  $out = & $pythonExe $check --root $Root --require-genesis 2>&1
  $code = $LASTEXITCODE

  if ($code -ne 0) {
    Write-Host '=== OBSIDIAN JUDGMENT / PROVENANCE REFUSAL ==='
    foreach ($line in $out) { Write-Host $line }

    # Attempt to print a single-line structured receipt for humans/automation.
    try {
      $raw = ($out | ForEach-Object { [string]$_ }) -join "\n"
      $parsed = $raw | ConvertFrom-Json

      $refusalCode = [string]$parsed.code
      if ($refusalCode -eq 'genesis_missing') { $refusalCode = 'MISSING_GENESIS' }
      elseif ($refusalCode -eq 'judgment_active') { $refusalCode = 'JUDGMENT_ACTIVE' }
      elseif ($refusalCode -eq 'governance_hash_mismatch') { $refusalCode = 'HASH_MISMATCH' }
      elseif ($refusalCode -eq 'genesis_hash_mismatch') { $refusalCode = 'GENESIS_HASH_MISMATCH' }
      elseif ($refusalCode -eq 'project_id_mismatch') { $refusalCode = 'PROJECT_ID_MISMATCH' }
      elseif ($refusalCode -eq 'genesis_parse_error') { $refusalCode = 'GENESIS_PARSE_ERROR' }

      $receipt = [pscustomobject]@{
        refusal_code = $refusalCode
        expected_baseline_hash = $parsed.expected_baseline_hash
        detected_hash = $parsed.detected_hash
        next_steps = $parsed.next_steps
      }

      Write-Host ('REFUSAL_RECEIPT: {0}' -f ($receipt | ConvertTo-Json -Compress))
    } catch {
      # best-effort only
    }

    throw 'Refused: provenance verification failed (or judgment active). If this is a first-time setup, run: python MODULES/OBSIDIAN_JUDGMENT/cli/obsidian_judgment_cli.py genesis --write'
  }
}

function Ensure-File {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [Parameter(Mandatory=$true)][string]$Content,
    [switch]$Force
  )
  $dir = Split-Path -Parent $Path
  Ensure-Dir $dir

  if ((Test-Path -LiteralPath $Path) -and (-not $Force)) { return $false }
  Set-Content -LiteralPath $Path -Value $Content -Encoding UTF8 -Force
  return $true
}

function Load-Config {
  param([Parameter(Mandatory=$true)][string]$Root)

  $cfgPath = Join-Path $Root "SYSTEM\CONFIG\squad.config.json"
  if (-not (Test-Path -LiteralPath $cfgPath)) {
    return $null
  }

  try {
    $raw = Get-Content -LiteralPath $cfgPath -Raw -Encoding UTF8
    return ($raw | ConvertFrom-Json)
  } catch {
    throw "Config exists but failed to parse: $cfgPath | $($_.Exception.Message)"
  }
}

function Scaffold-SquadFiles {
  param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$LogDir,
    [switch]$Force
  )

  $created = 0

  $files = @(
    @{
      Path = (Join-Path $Root "README.md")
      Content = @"
# SQUAD
Veteran-first case navigation engine.

- Modular agent architecture
- JSON-first outputs
- Ethical/operational guardrails
- Case artifacts saved under CASES\ and OUTPUTS\

Use the Admin Clerk to keep structure sane and auditable.
"@
    },
    @{
      Path = (Join-Path $Root "SYSTEM\CONFIG\squad.config.json")
      Content = @"
{
  "project": "SQUAD",
  "root": "C:\\\\Projects\\\\SQUAD",
  "version": "0.3.0",
  "ethics": {
    "no_fraud": true,
    "no_impersonation": true,
    "no_medical_or_legal_diagnosis": true
  },
  "case_defaults": {
    "max_actions_per_day": 3,
    "plan_horizon_days": 7
  },
  "git": {
    "repo_root": "REPO"
  }
}
"@
    },
    @{
      Path = (Join-Path $Root "AGENTS\PROMPTS\README.md")
      Content = @"
# PROMPTS
Store agent prompts here (versioned).

Keep prompts:
- role-specific
- JSON-output constrained
- minimal drift
"@
    },
    @{
      Path = (Join-Path $Root "AGENTS\SCHEMAS\README.md")
      Content = @"
# SCHEMAS
JSON schemas for each agent output (intake, hunter, strategist, etc.).

Goal: deterministic + auditable outputs.
"@
    },
    @{
      Path = (Join-Path $Root "AGENTS\CORE\README.md")
      Content = @"
# CORE
Agent runtime utilities and orchestration code live here.
"@
    },
    @{
      Path = (Join-Path $Root "DOCS\README.md")
      Content = @"
# DOCS
Project documentation, reference material, checklists, scripts.
"@
    },
    @{
      Path = (Join-Path $Root "CASES\TEMPLATES\case_template.json")
      Content = @"
{
  "case_id": "CASE_0000",
  "created_utc": null,
  "status": "active",
  "intake": {},
  "benefits": {},
  "strategy": {},
  "notes": ""
}
"@
    },
    @{
      Path = (Join-Path $Root "CASES\TEMPLATES\notes.md")
      Content = @"
# Case Notes

## Contacts
- VSO:
- Case manager:
- Legal aid:

## Timeline
- Day 1:
- Day 2:
- Day 3:

## Blockers
-

## Outcomes
-
"@
    },
    @{
      Path = (Join-Path $Root "OUTPUTS\README.md")
      Content = @"
# OUTPUTS
Generated run artifacts live here.

- RUNS: raw execution outputs
- EXPORTS: packaged outputs for sharing
"@
    },
    @{
      # Git ignore belongs in REPO (git root by design)
      Path = (Join-Path $Root "REPO\.gitignore")
      Content = @"
# Keep repo clean. Cases + generated outputs stay local.
..\CASES\
..\DATA\
..\OUTPUTS\
..\SYSTEM\LOGS\

# OS junk
Thumbs.db
.DS_Store
"@
    },
    @{
      Path = (Join-Path $Root "REPO\README.md")
      Content = @"
# SQUAD REPO
This folder is the Git root by design.

Reason:
- Keep CASES/DATA/OUTPUTS as local artifacts
- Track only code, schemas, prompts, and docs under version control
"@
    }
  )

  foreach ($f in $files) {
    if (Ensure-File -Path $f.Path -Content $f.Content -Force:$Force) {
      $created++
      Write-ClerkLog $LogDir "Scaffolded file: $($f.Path)" "INFO"
    }
  }

  return $created
}

function Get-RouteTarget {
  param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$FilePath,
    [string]$CaseId
  )

  $name = [IO.Path]::GetFileName($FilePath)
  $ext  = ([IO.Path]::GetExtension($FilePath)).ToLowerInvariant()

  # Dotfiles go to a safe non-case location (except .gitkeep)
  if ($name.StartsWith(".") -and $name -ne ".gitkeep") {
    return (Join-Path $Root "SYSTEM\META\DOTFILES")
  }

  $destBase = Join-Path $Root "DATA\MISC"

  switch ($ext) {
    ".json" { $destBase = Join-Path $Root "DATA\INTAKE" }
    ".yaml" { $destBase = Join-Path $Root "AGENTS\SCHEMAS" }
    ".yml"  { $destBase = Join-Path $Root "AGENTS\SCHEMAS" }
    ".md"   { $destBase = Join-Path $Root "DOCS" }
    ".txt"  { $destBase = Join-Path $Root "DOCS" }
    ".pdf"  { $destBase = Join-Path $Root "DOCS\FORMS" }
    ".docx" { $destBase = Join-Path $Root "DOCS\FORMS" }
    ".ps1"  { $destBase = Join-Path $Root "SYSTEM\CLERK" }
    ".py"   { $destBase = Join-Path $Root "AGENTS\CORE" }
    ".csv"  { $destBase = Join-Path $Root "DATA" }
    default { $destBase = Join-Path $Root "DATA\MISC" }
  }

  # Case-aware routing override
  if ($CaseId -and $CaseId.Trim().Length -gt 0) {
    $caseRoot = Join-Path $Root ("CASES\ACTIVE\" + $CaseId)
    $destBase = Join-Path $caseRoot "ARTIFACTS"
  }

  return $destBase
}

# --------------------------
# Structure
# --------------------------

$dirs = @(
  "CASES\ACTIVE",
  "CASES\ARCHIVE",
  "CASES\TEMPLATES",
  "SYSTEM\CLERK",
  "SYSTEM\CONFIG",
  "SYSTEM\LOGS\CLERK",
  "SYSTEM\META\DOTFILES",
  "SYSTEM\META\QUARANTINE",
  "AGENTS\PROMPTS",
  "AGENTS\SCHEMAS",
  "AGENTS\CORE",
  "AGENTS\LOGIC",
  "DATA\INTAKE",
  "DATA\BENEFITS",
  "DATA\HOUSING",
  "DATA\INCOME",
  "DATA\LEGAL",
  "DATA\MISC",
  "DOCS\FORMS",
  "DOCS\CHECKLISTS",
  "DOCS\SCRIPTS",
  "DOCS\spec",
  "OUTPUTS\RUNS",
  "OUTPUTS\EXPORTS",
  "REPO"
)

$logDir = Join-Path $SquadRoot "SYSTEM\LOGS\CLERK"

# Plan mode must be provably read-only (no directory creation, no logs, no lock file).
# Plan is allowed only for non-mutating previews (e.g., -InPath -Plan, -QuarantineLegacyOutputs -Plan).
$script:ClerkPlanReadOnly = $false
if ($Plan -and (-not $Init) -and (-not $ExportCase) -and (-not $PathfinderInput) -and (-not $CRARun) -and (-not $BreakLock)) {
  $script:ClerkPlanReadOnly = $true
}

if (-not $script:ClerkPlanReadOnly) {
  Ensure-Dir $logDir
}

# Normalize
if ($CaseId) { $CaseId = $CaseId.Trim().ToUpperInvariant() }
if ($ExportCase) { $ExportCase = $ExportCase.Trim().ToUpperInvariant() }

# Security gate: any mutating action requires verified provenance.
# This prevents silent drift in governance-critical files unless reverted to the last known-good hash.
$mutatingRequested = $false
if ($Init) { $mutatingRequested = $true }
if ($InPath -and (-not $Plan)) { $mutatingRequested = $true }
if ($ExportCase) { $mutatingRequested = $true }
if ($PathfinderInput) { $mutatingRequested = $true }
if ($CRARun) { $mutatingRequested = $true }
if ($QuarantineLegacyOutputs -and (-not $Plan)) { $mutatingRequested = $true }

# Load config (optional)
$config = Load-Config -Root $SquadRoot
if ($config -and $config.root -and ($config.root -ne $SquadRoot)) {
  # Do NOT auto-switch roots silently. Log only.
  Write-ClerkLog $logDir ("Config root differs from -SquadRoot. ConfigRoot={0} ParamRoot={1} (no auto-switch)" -f $config.root, $SquadRoot) "WARN"
}

# --------------------------
# Locking (single instance)
# --------------------------

$lockFile = Join-Path $logDir 'clerk.lock'
$lockHandle = $null

function Acquire-Lock {
  param([string]$LockFile)
  # CreateNew fails if exists (good)
  return [System.IO.File]::Open($LockFile, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
}

function Release-Lock {
  param($Handle, [string]$LockFile)
  if ($Handle) {
    $Handle.Close()
    Remove-Item -LiteralPath $LockFile -Force -ErrorAction SilentlyContinue
  }
}

# Handle explicit lock break (authorized only)
if ($BreakLock) {
  if (-not $BreakLockReason -or -not $BreakLockReason.Trim()) {
    throw '-BreakLock requires -BreakLockReason (human authorization note).'
  }

  if (Test-Path -LiteralPath $lockFile) {
    Write-ClerkLog $logDir ('AUTH_BREAK_LOCK requested. Reason: {0}' -f $BreakLockReason) 'WARN'
    Remove-Item -LiteralPath $lockFile -Force
    Write-ClerkLog $logDir ('AUTH_BREAK_LOCK executed. Lock removed. Reason: {0}' -f $BreakLockReason) 'WARN'
    Write-Host 'Lock removed (authorized).'
  } else {
    Write-Host 'No lock present.'
  }
  exit 0
}

try {
  if (-not $script:ClerkPlanReadOnly) {
    $lockHandle = Acquire-Lock -LockFile $lockFile
  }
} catch {
  Write-ClerkLog $logDir 'Lock acquisition failed - concurrent run detected.' 'ERROR'
  Write-Host 'Another Clerk instance is running (or a lock file exists).'
  Write-Host 'If you verified it is stale and you authorize it, run:'
  Write-Host '  .\Invoke-SquadAdminClerk.ps1 -BreakLock -BreakLockReason why_this_is_authorized'
  exit 2
}

# Enforce provenance only after we have a single-instance lock.
if ($mutatingRequested -and (-not $script:ClerkPlanReadOnly)) {
  Assert-ObsidianProvenanceOk -Root $SquadRoot
}

# Ensure lock release on exit (skip in read-only plan mode)
if (-not $script:ClerkPlanReadOnly) {
  $null = Register-EngineEvent PowerShell.Exiting -Action { Release-Lock -Handle $lockHandle -LockFile $lockFile } | Out-Null
}

# --------------------------
# EXPORT MODE
# --------------------------

if ($ExportCase) {
  $caseFolder = Join-Path $SquadRoot ('CASES\ACTIVE\' + $ExportCase)
  if (-not (Test-Path -LiteralPath $caseFolder)) {
    throw ('Case {0} not found in CASES\ACTIVE.' -f $ExportCase)
  }

  $zipName = ('CASE_{0}_{1}.zip' -f $ExportCase, (Get-Date -Format yyyyMMdd_HHmm))
  $zipPath = Join-Path $SquadRoot ('OUTPUTS\EXPORTS\' + $zipName)
  Ensure-Dir (Split-Path -Parent $zipPath)

  if ($PSCmdlet.ShouldProcess($zipPath, ('Export case {0} to ZIP' -f $ExportCase))) {
    Compress-Archive -Path (Join-Path $caseFolder '*') -DestinationPath $zipPath -Force
    $zipHash = Get-FileSha256 $zipPath
    Write-ClerkLog $logDir ('Exported case {0} -> {1} | SHA256={2}' -f $ExportCase, $zipPath, $zipHash) 'INFO'
    Write-Host ('Exported: {0}' -f $zipPath)
    Write-Host ('SHA256:   {0}' -f $zipHash)
  }

  Release-Lock -Handle $lockHandle -LockFile $lockFile
  exit 0
}

# --------------------------
# QUARANTINE LEGACY OUTPUTS MODE
# --------------------------

if ($QuarantineLegacyOutputs) {
  # Ensure structure exists (skip in plan-only read-only mode)
  if (-not $script:ClerkPlanReadOnly) {
    Ensure-Dir $SquadRoot
    foreach ($d in $dirs) { Ensure-Dir (Join-Path $SquadRoot $d) }
  }

  $runsDir = Join-Path $SquadRoot 'OUTPUTS\RUNS'
  if (-not (Test-Path -LiteralPath $runsDir)) {
    throw ('Missing runs directory: {0}' -f $runsDir)
  }

  $quarantineRoot = Join-Path $SquadRoot 'SYSTEM\META\QUARANTINE\legacy_outputs'
  if (-not $script:ClerkPlanReadOnly) {
    Ensure-Dir $quarantineRoot
  }

  # Only quarantine Pathfinder runs for now, based on current schema expectations.
  $candidates = Get-ChildItem -LiteralPath $runsDir -Directory -Filter 'pathfinder_run_*' -ErrorAction SilentlyContinue
  $qPlan = New-Object System.Collections.Generic.List[object]

  foreach ($dirItem in $candidates) {
    $inPath = Join-Path $dirItem.FullName 'pathfinder_input.contract.v1.json'
    if (-not (Test-Path -LiteralPath $inPath)) { continue }

    try {
      $contract = Read-JsonFile -Path $inPath
    } catch {
      # If it can't even parse, quarantine it.
      $qPlan.Add([pscustomobject]@{ RunDir = $dirItem.FullName; Reason = 'input JSON failed to parse' })
      continue
    }

    $state = $null
    try {
      $state = $contract.input.case.location.state
    } catch { $state = $null }

    $len = Get-StringLengthOrMinus1 $state
    if ($len -ne 2) {
      $qPlan.Add([pscustomobject]@{ RunDir = $dirItem.FullName; Reason = ('input.case.location.state invalid length ({0})' -f $len) })
    }
  }

  if ($Plan) {
    Write-Host ''
    Write-Host '=== QUARANTINE PLAN (legacy outputs) ==='
    if ($qPlan.Count -eq 0) {
      Write-Host 'No legacy outputs matched quarantine criteria.'
    } else {
      foreach ($p in $qPlan) {
        Write-Host ('MOVE  {0}' -f $p.RunDir)
        Write-Host ('  ->  {0}' -f (Join-Path $quarantineRoot (Split-Path -Leaf $p.RunDir)))
        Write-Host ('  WHY {0}' -f $p.Reason)
      }
      Write-Host ('TOTAL: {0} run folder(s)' -f $qPlan.Count)
    }

    Write-ClerkLog $logDir ('PLAN: QuarantineLegacyOutputs generated. Candidates={0}' -f $qPlan.Count) 'INFO'
    Release-Lock -Handle $lockHandle -LockFile $lockFile
    exit 0
  }

  if ($qPlan.Count -eq 0) {
    Write-Host 'No legacy outputs matched quarantine criteria.'
    Write-ClerkLog $logDir 'QuarantineLegacyOutputs: no candidates.' 'INFO'
    Release-Lock -Handle $lockHandle -LockFile $lockFile
    exit 0
  }

  foreach ($p in $qPlan) {
    $src = [string]$p.RunDir
    $destBase = Join-Path $quarantineRoot (Split-Path -Leaf $src)
    $dest = Get-UniquePath -Path $destBase

    if ($PSCmdlet.ShouldProcess(('{0} -> {1}' -f $src, $dest), 'Quarantine legacy output folder')) {
      Move-Item -LiteralPath $src -Destination $dest -Force -WhatIf:$WhatIfPreference
      if (-not $WhatIfPreference) {
        Write-ClerkLog $logDir ('Quarantined legacy output folder | From={0} To={1} | Reason={2}' -f $src, $dest, $p.Reason) 'WARN'
      } else {
        Write-ClerkLog $logDir ('WHATIF: Would quarantine legacy output folder | From={0} To={1} | Reason={2}' -f $src, $dest, $p.Reason) 'INFO'
      }
    }
  }

  Write-Host ('Quarantined {0} legacy output folder(s) to: {1}' -f $qPlan.Count, $quarantineRoot)

  Release-Lock -Handle $lockHandle -LockFile $lockFile
  exit 0
}

# --------------------------
# PATHFINDER RUN MODE
# --------------------------

if ($PathfinderInput) {
  if ($CRARun) {
    throw 'Use either -PathfinderInput or -CRARun (not both in the same run).'
  }

  # Ensure structure exists
  Ensure-Dir $SquadRoot
  foreach ($d in $dirs) { Ensure-Dir (Join-Path $SquadRoot $d) }

  $resolvedInput = [System.IO.Path]::GetFullPath($PathfinderInput)
  if (-not (Test-Path -LiteralPath $resolvedInput)) {
    Write-ClerkLog $logDir ('Pathfinder input not found: {0}' -f $resolvedInput) 'ERROR'
    throw ('Pathfinder input not found: {0}' -f $resolvedInput)
  }

  $pythonCmd = (Get-Command python -ErrorAction SilentlyContinue)
  if (-not $pythonCmd) {
    Write-ClerkLog $logDir 'Pathfinder run failed: python not found on PATH' 'ERROR'
    throw 'Pathfinder run failed: python not found on PATH. Install Python or add it to PATH.'
  }

  $runner = Join-Path $SquadRoot 'AGENTS\CORE\PATHFINDER\pf_core_runner_v1.py'
  if (-not (Test-Path -LiteralPath $runner)) {
    Write-ClerkLog $logDir ('Pathfinder runner missing: {0}' -f $runner) 'ERROR'
    throw ('Pathfinder runner missing: {0}' -f $runner)
  }

  $ts = Get-Date -Format yyyyMMdd_HHmmss
  $runDir = Join-Path $SquadRoot ('OUTPUTS\RUNS\pathfinder_run_' + $ts)
  Ensure-Dir $runDir

  $outPath = Join-Path $runDir 'pathfinder_output.contract.v1.json'
  $inCopyPath = Join-Path $runDir 'pathfinder_input.contract.v1.json'
  Copy-Item -LiteralPath $resolvedInput -Destination $inCopyPath -Force

  $cmd = @(
    'python',
    $runner,
    $inCopyPath,
    '--out',
    $outPath
  )

  if ($PSCmdlet.ShouldProcess($outPath, 'Run Pathfinder PF-Core')) {
    Write-ClerkLog $logDir ('Pathfinder run start | Input={0} | RunDir={1}' -f $resolvedInput, $runDir) 'INFO'

    & $cmd[0] $cmd[1] $cmd[2] $cmd[3] $cmd[4] | Out-Null

    if (-not (Test-Path -LiteralPath $outPath)) {
      Write-ClerkLog $logDir ('Pathfinder run failed: output not created | Expected={0}' -f $outPath) 'ERROR'
      throw ('Pathfinder run failed: output not created. Expected: {0}' -f $outPath)
    }

    $outHash = Get-FileSha256 $outPath
    Write-ClerkLog $logDir ('Pathfinder run complete | Output={0} | SHA256={1}' -f $outPath, $outHash) 'INFO'
    Write-Host ('Pathfinder output: {0}' -f $outPath)
    Write-Host ('SHA256:           {0}' -f $outHash)

    if ($CaseId -and $CaseId.Trim().Length -gt 0) {
      $caseArtifacts = Join-Path $SquadRoot ('CASES\ACTIVE\' + $CaseId + '\ARTIFACTS\PATHFINDER')
      Ensure-Dir $caseArtifacts
      $caseOut = Join-Path $caseArtifacts ('pathfinder_output_' + $ts + '.contract.v1.json')
      Copy-Item -LiteralPath $outPath -Destination $caseOut -Force
      Write-ClerkLog $logDir ('Pathfinder output copied to case artifacts | CaseId={0} | Path={1}' -f $CaseId, $caseOut) 'INFO'
      Write-Host ('Case artifact:    {0}' -f $caseOut)
    }
  }

  Release-Lock -Handle $lockHandle -LockFile $lockFile
  exit 0
}

# --------------------------
# CRA RUN MODE
# --------------------------

if ($CRARun) {
  # Ensure structure exists
  Ensure-Dir $SquadRoot
  foreach ($d in $dirs) { Ensure-Dir (Join-Path $SquadRoot $d) }

  if (-not $CaseId -or -not $CaseId.Trim()) {
    throw '-CRARun requires -CaseId (target case for artifacts).'
  }

  $caseFolder = Join-Path $SquadRoot ('CASES\ACTIVE\' + $CaseId)
  if (-not (Test-Path -LiteralPath $caseFolder)) {
    throw ('Case {0} not found in CASES\ACTIVE.' -f $CaseId)
  }

  $runner = Join-Path $SquadRoot 'pathfinder_cra\run_cra_v1.py'
  if (-not (Test-Path -LiteralPath $runner)) {
    throw ('CRA runner missing: {0}' -f $runner)
  }

  $pythonExe = Get-PythonExeForRuns -Root $SquadRoot

  # Resolve input
  $resolvedInput = $null
  if ($CRAInput -and $CRAInput.Trim()) {
    $resolvedInput = [System.IO.Path]::GetFullPath($CRAInput)
  } else {
    $resolvedInput = Join-Path $caseFolder 'ARTIFACTS\CRA\cra.input.v1.json'
  }

  if (-not (Test-Path -LiteralPath $resolvedInput)) {
    throw ('CRA input not found: {0}' -f $resolvedInput)
  }

  $ts = Get-Date -Format yyyyMMdd_HHmmss
  $runDir = Join-Path $SquadRoot ('OUTPUTS\RUNS\cra_run_' + $ts)
  Ensure-Dir $runDir

  $inCopyPath = Join-Path $runDir 'cra_input.v1.json'
  $outPath = Join-Path $runDir 'cra_report.v1.json'
  Copy-Item -LiteralPath $resolvedInput -Destination $inCopyPath -Force

  if ($PSCmdlet.ShouldProcess($outPath, 'Run CRA (Claim Readiness Analysis)')) {
    Write-ClerkLog $logDir ('CRA run start | CaseId={0} | Input={1} | RunDir={2}' -f $CaseId, $resolvedInput, $runDir) 'INFO'

    & $pythonExe $runner --input $inCopyPath --out $outPath | Out-Null
    if ($LASTEXITCODE -ne 0) {
      Write-ClerkLog $logDir ('CRA run failed: non-zero exit code {0}' -f $LASTEXITCODE) 'ERROR'
      throw ('CRA run failed: non-zero exit code {0}' -f $LASTEXITCODE)
    }

    if (-not (Test-Path -LiteralPath $outPath)) {
      Write-ClerkLog $logDir ('CRA run failed: output not created | Expected={0}' -f $outPath) 'ERROR'
      throw ('CRA run failed: output not created. Expected: {0}' -f $outPath)
    }

    $outHash = Get-FileSha256 $outPath
    Write-ClerkLog $logDir ('CRA run complete | Output={0} | SHA256={1}' -f $outPath, $outHash) 'INFO'
    Write-Host ('CRA output: {0}' -f $outPath)
    Write-Host ('SHA256:    {0}' -f $outHash)

    # Copy into case artifacts
    $caseArtifacts = Join-Path $caseFolder 'ARTIFACTS\CRA'
    Ensure-Dir $caseArtifacts
    $caseOut = Join-Path $caseArtifacts ('cra_report_' + $ts + '.v1.json')
    Copy-Item -LiteralPath $outPath -Destination $caseOut -Force
    Write-ClerkLog $logDir ('CRA output copied to case artifacts | CaseId={0} | Path={1}' -f $CaseId, $caseOut) 'INFO'
    Write-Host ('Case artifact: {0}' -f $caseOut)
  }

  Release-Lock -Handle $lockHandle -LockFile $lockFile
  exit 0
}

# --------------------------
# INIT MODE
# --------------------------

if ($Init) {
  Ensure-Dir $SquadRoot
  foreach ($d in $dirs) {
    Ensure-Dir (Join-Path $SquadRoot $d)
  }
  Write-ClerkLog $logDir ('Initialized/verified Squad structure at: {0}' -f $SquadRoot) 'INFO'

  if ($Scaffold) {
    $count = Scaffold-SquadFiles -Root $SquadRoot -LogDir $logDir -Force:$ForceScaffold
    Write-ClerkLog $logDir ('Scaffold complete. Files created/updated: {0} (Force={1})' -f $count, $ForceScaffold) 'INFO'
    Write-Host ('Scaffold complete. Files created/updated: {0}' -f $count)
  }

  if ($InitGit) {
    $repoPath = Join-Path $SquadRoot 'REPO'
    Ensure-Dir $repoPath
    if (-not (Test-Path -LiteralPath (Join-Path $repoPath '.git'))) {
      Push-Location $repoPath
      git init | Out-Null
      Pop-Location
      Write-ClerkLog $logDir ('Initialized git repo in: {0}' -f $repoPath) 'INFO'
      Write-Host ('Git initialized in: {0}' -f $repoPath)
    } else {
      Write-ClerkLog $logDir ('Git repo already exists in: {0}' -f $repoPath) 'WARN'
      Write-Host ('Git already exists in: {0}' -f $repoPath)
    }
  }
}

# --------------------------
# ROUTING MODE
# --------------------------

if ($InPath) {
  # Ensure structure exists (skip in plan-only read-only mode)
  if (-not $script:ClerkPlanReadOnly) {
    Ensure-Dir $SquadRoot
    foreach ($d in $dirs) { Ensure-Dir (Join-Path $SquadRoot $d) }
  }

  $resolvedInput = [System.IO.Path]::GetFullPath($InPath)

  if (-not (Test-Path -LiteralPath $resolvedInput)) {
    Write-ClerkLog $logDir ('Input path not found: {0}' -f $resolvedInput) 'ERROR'
    throw ('Input path not found: {0}' -f $resolvedInput)
  }

  $item = Get-Item -LiteralPath $resolvedInput
  $items = @()
  if ($item.PSIsContainer) {
    $items = Get-ChildItem -LiteralPath $resolvedInput -File -Recurse
  } else {
    $items = @($item)
  }

  # Case guard: allow typical case artifacts only
  $caseLikeExts = @('.json','.pdf','.docx','.txt','.md','.csv','.png','.jpg','.jpeg')
  $maxCollisions = 999

  # Plan mode summary buckets
  $planMap = @{}

  foreach ($f in $items) {
    $ext = ([IO.Path]::GetExtension($f.FullName)).ToLowerInvariant()
    $targetDir = Get-RouteTarget -Root $SquadRoot -FilePath $f.FullName -CaseId $CaseId

    if ($Plan) {
      if (-not $planMap.ContainsKey($targetDir)) { $planMap[$targetDir] = 0 }
      $planMap[$targetDir]++
      continue
    }

    Ensure-Dir $targetDir

    $destPath = Join-Path $targetDir $f.Name

    # Collision handling with hard cap
    if (Test-Path -LiteralPath $destPath) {
      $baseName = [IO.Path]::GetFileNameWithoutExtension($f.Name)
      $e = [IO.Path]::GetExtension($f.Name)
      $n = 1
      do {
        $destPath = Join-Path $targetDir ('{0}__{1}{2}' -f $baseName, $n, $e)
        $n++
        if ($n -gt $maxCollisions) {
          throw ('Collision limit exceeded ({0}) for: {1} in {2}' -f $maxCollisions, $f.Name, $targetDir)
        }
      } while (Test-Path -LiteralPath $destPath)
    }

    # CaseId guard for non-case extensions (human verification logged)
    if ($CaseId -and ($caseLikeExts -notcontains $ext)) {
      $msg = ('CaseGuard: Non-case extension {0} would be routed into CASE {1}. Source={2} Dest={3}' -f $ext, $CaseId, $f.FullName, $destPath)
      Write-Host $msg
      $answer = Read-Host 'Authorize this move? Type YES to proceed, NO to skip'
      $answerNorm = ($answer | ForEach-Object { $_.Trim().ToUpperInvariant() })

      Write-ClerkLog $logDir ('HUMAN_VERIFY :: {0} :: ANSWER={1}' -f $msg, $answerNorm) 'WARN'

      if ($answerNorm -ne 'YES') {
        Write-ClerkLog $logDir ('SKIPPED by human verify: {0}' -f $f.FullName) 'WARN'
        continue
      }
    }

    if ($PSCmdlet.ShouldProcess(('{0} -> {1}' -f $f.FullName, $destPath), 'Move file')) {
      Move-Item -LiteralPath $f.FullName -Destination $destPath -Force -WhatIf:$WhatIfPreference

      if (-not $WhatIfPreference) {
        $hashLog = ''
        if ($LogHash) {
          $hashLog = ' | SHA256=' + (Get-FileSha256 $destPath)
        }
        Write-ClerkLog $logDir ('Moved {0} -> {1}{2}' -f $f.FullName, $destPath, $hashLog) 'INFO'
      } else {
        Write-ClerkLog $logDir ('WHATIF: Would move {0} -> {1}' -f $f.FullName, $destPath) 'INFO'
      }
    }
  }

  if ($Plan) {
    Write-Host ''
    Write-Host '=== ROUTE PLAN SUMMARY ==='
    $total = 0
    foreach ($k in ($planMap.Keys | Sort-Object)) {
      $c = $planMap[$k]
      $total += $c
      '{0,-6} {1}' -f $c, $k | Write-Host
    }
    Write-Host ('TOTAL: {0} files' -f $total)
    Write-ClerkLog $logDir ('PLAN: Route plan generated for InPath={0} CaseId={1} Total={2}' -f $resolvedInput, $CaseId, $total) 'INFO'
  }
}

# --------------------------
# Help / Default
# --------------------------

if (-not $Init -and -not $InPath -and -not $ExportCase -and -not $BreakLock) {
  Write-Host 'Squad Admin Clerk v1.3'
  Write-Host ''
  Write-Host 'Examples:'
  Write-Host '  .\Invoke-SquadAdminClerk.ps1 -Init -Scaffold -InitGit'
  Write-Host '  .\Invoke-SquadAdminClerk.ps1 -InPath C:\Temp\CaseStuff -CaseId VET_0001 -Plan'
  Write-Host '  .\Invoke-SquadAdminClerk.ps1 -ExportCase VET_0001'
  Write-Host '  .\Invoke-SquadAdminClerk.ps1 -PathfinderInput .\AGENTS\CORE\PATHFINDER\example_input.contract.v1.json'
  Write-Host '  .\Invoke-SquadAdminClerk.ps1 -CRARun -CaseId VET_0001'
  Write-Host '  .\Invoke-SquadAdminClerk.ps1 -QuarantineLegacyOutputs -Plan'
  Write-Host '  .\Invoke-SquadAdminClerk.ps1 -BreakLock -BreakLockReason Verified_stale_lock_authorized_by_operator'
}

# Release lock
Release-Lock -Handle $lockHandle -LockFile $lockFile
