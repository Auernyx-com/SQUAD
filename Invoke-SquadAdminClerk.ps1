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

function Resolve-SafePath {
  param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$Path
  )
  $rootFull = [System.IO.Path]::GetFullPath($Root)
  $pathFull = [System.IO.Path]::GetFullPath($Path)

  if (-not $pathFull.StartsWith($rootFull, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsafe path: '$Path' escapes root '$Root'."
  }
  return $pathFull
}

function Write-ClerkLog {
  param(
    [Parameter(Mandatory=$true)][string]$LogDir,
    [Parameter(Mandatory=$true)][string]$Message,
    [ValidateSet("INFO","WARN","ERROR")][string]$Level="INFO"
  )
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
Ensure-Dir $logDir

# Normalize
if ($CaseId) { $CaseId = $CaseId.Trim().ToUpperInvariant() }
if ($ExportCase) { $ExportCase = $ExportCase.Trim().ToUpperInvariant() }

# Load config (optional)
$config = Load-Config -Root $SquadRoot
if ($config -and $config.root -and ($config.root -ne $SquadRoot)) {
  # Do NOT auto-switch roots silently. Log only.
  Write-ClerkLog $logDir "Config root differs from -SquadRoot. ConfigRoot='$($config.root)' ParamRoot='$SquadRoot' (no auto-switch)" "WARN"
}

# --------------------------
# Locking (single instance)
# --------------------------

$lockFile = Join-Path $logDir "clerk.lock"
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
    throw "-BreakLock requires -BreakLockReason (human authorization note)."
  }

  if (Test-Path -LiteralPath $lockFile) {
    Write-ClerkLog $logDir "AUTH_BREAK_LOCK requested. Reason: $BreakLockReason" "WARN"
    Remove-Item -LiteralPath $lockFile -Force
    Write-ClerkLog $logDir "AUTH_BREAK_LOCK executed. Lock removed. Reason: $BreakLockReason" "WARN"
    Write-Host "Lock removed (authorized)."
  } else {
    Write-Host "No lock present."
  }
  exit 0
}

try {
  $lockHandle = Acquire-Lock -LockFile $lockFile
} catch {
  Write-ClerkLog $logDir "Lock acquisition failed — concurrent run detected." "ERROR"
  Write-Host "Another Clerk instance is running (or a lock file exists)."
  Write-Host "If you verified it's stale and you authorize it, run:"
  Write-Host "  .\Invoke-SquadAdminClerk.ps1 -BreakLock -BreakLockReason ""<why this is authorized>"""
  exit 2
}

# Ensure lock release on exit
$null = Register-EngineEvent PowerShell.Exiting -Action { Release-Lock -Handle $lockHandle -LockFile $lockFile } | Out-Null

# --------------------------
# EXPORT MODE
# --------------------------

if ($ExportCase) {
  $caseFolder = Join-Path $SquadRoot "CASES\ACTIVE\$ExportCase"
  if (-not (Test-Path -LiteralPath $caseFolder)) {
    throw "Case '$ExportCase' not found in CASES\ACTIVE."
  }

  $zipName = "CASE_$ExportCase`_$(Get-Date -Format yyyyMMdd_HHmm).zip"
  $zipPath = Join-Path $SquadRoot "OUTPUTS\EXPORTS\$zipName"
  Ensure-Dir (Split-Path -Parent $zipPath)

  if ($PSCmdlet.ShouldProcess($zipPath, "Export case '$ExportCase' to ZIP")) {
    Compress-Archive -Path (Join-Path $caseFolder "*") -DestinationPath $zipPath -Force
    $zipHash = Get-FileSha256 $zipPath
    Write-ClerkLog $logDir "Exported case $ExportCase -> $zipPath | SHA256=$zipHash" "INFO"
    Write-Host "Exported: $zipPath"
    Write-Host "SHA256:   $zipHash"
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
  Write-ClerkLog $logDir "Initialized/verified Squad structure at: $SquadRoot" "INFO"

  if ($Scaffold) {
    $count = Scaffold-SquadFiles -Root $SquadRoot -LogDir $logDir -Force:$ForceScaffold
    Write-ClerkLog $logDir "Scaffold complete. Files created/updated: $count (Force=$ForceScaffold)" "INFO"
    Write-Host "Scaffold complete. Files created/updated: $count"
  }

  if ($InitGit) {
    $repoPath = Join-Path $SquadRoot "REPO"
    Ensure-Dir $repoPath
    if (-not (Test-Path -LiteralPath (Join-Path $repoPath ".git"))) {
      Push-Location $repoPath
      git init | Out-Null
      Pop-Location
      Write-ClerkLog $logDir "Initialized git repo in: $repoPath" "INFO"
      Write-Host "Git initialized in: $repoPath"
    } else {
      Write-ClerkLog $logDir "Git repo already exists in: $repoPath" "WARN"
      Write-Host "Git already exists in: $repoPath"
    }
  }
}

# --------------------------
# ROUTING MODE
# --------------------------

if ($InPath) {
  # Ensure structure exists
  Ensure-Dir $SquadRoot
  foreach ($d in $dirs) { Ensure-Dir (Join-Path $SquadRoot $d) }

  $resolvedInput = [System.IO.Path]::GetFullPath($InPath)

  if (-not (Test-Path -LiteralPath $resolvedInput)) {
    Write-ClerkLog $logDir "Input path not found: $resolvedInput" "ERROR"
    throw "Input path not found: $resolvedInput"
  }

  $item = Get-Item -LiteralPath $resolvedInput
  $items = @()
  if ($item.PSIsContainer) {
    $items = Get-ChildItem -LiteralPath $resolvedInput -File -Recurse
  } else {
    $items = @($item)
  }

  # Case guard: allow typical case artifacts only
  $caseLikeExts = @(".json",".pdf",".docx",".txt",".md",".csv",".png",".jpg",".jpeg")
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
        $destPath = Join-Path $targetDir ("{0}__{1}{2}" -f $baseName, $n, $e)
        $n++
        if ($n -gt $maxCollisions) {
          throw "Collision limit exceeded ($maxCollisions) for: $($f.Name) in $targetDir"
        }
      } while (Test-Path -LiteralPath $destPath)
    }

    # CaseId guard for non-case extensions (human verification logged)
    if ($CaseId -and ($caseLikeExts -notcontains $ext)) {
      $msg = "CaseGuard: Non-case extension '$ext' would be routed into CASE '$CaseId'. Source='$($f.FullName)' Dest='$destPath'"
      Write-Host $msg
      $answer = Read-Host "Authorize this move? Type YES to proceed, NO to skip"
      $answerNorm = ($answer | ForEach-Object { $_.Trim().ToUpperInvariant() })

      Write-ClerkLog $logDir "HUMAN_VERIFY | $msg | ANSWER=$answerNorm" "WARN"

      if ($answerNorm -ne "YES") {
        Write-ClerkLog $logDir "SKIPPED by human verify: $($f.FullName)" "WARN"
        continue
      }
    }

    if ($PSCmdlet.ShouldProcess("$($f.FullName) -> $destPath", "Move file")) {
      Move-Item -LiteralPath $f.FullName -Destination $destPath -Force -WhatIf:$WhatIfPreference

      if (-not $WhatIfPreference) {
        $hashLog = ""
        if ($LogHash) {
          $hashLog = " | SHA256=$(Get-FileSha256 $destPath)"
        }
        Write-ClerkLog $logDir "Moved '$($f.FullName)' -> '$destPath'$hashLog" "INFO"
      } else {
        Write-ClerkLog $logDir "WHATIF: Would move '$($f.FullName)' -> '$destPath'" "INFO"
      }
    }
  }

  if ($Plan) {
    Write-Host ""
    Write-Host "=== ROUTE PLAN SUMMARY ==="
    $total = 0
    foreach ($k in ($planMap.Keys | Sort-Object)) {
      $c = $planMap[$k]
      $total += $c
      "{0,-6} {1}" -f $c, $k | Write-Host
    }
    Write-Host "TOTAL: $total files"
    Write-ClerkLog $logDir "PLAN: Route plan generated for InPath='$resolvedInput' CaseId='$CaseId' Total=$total" "INFO"
  }
}

# --------------------------
# Help / Default
# --------------------------

if (-not $Init -and -not $InPath -and -not $ExportCase -and -not $BreakLock) {
  Write-Host "Squad Admin Clerk v1.3"
  Write-Host ""
  Write-Host "Examples:"
  Write-Host "  .\Invoke-SquadAdminClerk.ps1 -Init -Scaffold -InitGit"
  Write-Host "  .\Invoke-SquadAdminClerk.ps1 -InPath C:\Temp\somefile.json"
  Write-Host "  .\Invoke-SquadAdminClerk.ps1 -InPath C:\Temp\CaseStuff -CaseId VET_0001"
  Write-Host "  .\Invoke-SquadAdminClerk.ps1 -InPath C:\Temp\CaseStuff -CaseId VET_0001 -Plan"
  Write-Host "  .\Invoke-SquadAdminClerk.ps1 -ExportCase VET_0001"
  Write-Host "  .\Invoke-SquadAdminClerk.ps1 -BreakLock -BreakLockReason ""Verified stale lock; authorized by operator"""
}

# Release lock
Release-Lock -Handle $lockHandle -LockFile $lockFile
