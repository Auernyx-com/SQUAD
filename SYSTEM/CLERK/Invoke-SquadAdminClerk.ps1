<#
.SYNOPSIS
  SQUAD Admin Clerk — governance + safe routing + scaffolding tool.

.DESCRIPTION
  - Creates/repairs SQUAD directory structure under a defined root.
  - Safe routing by extension into project folders.
  - Optional case-aware routing into CASES\ACTIVE\<CaseId>\ARTIFACTS
  - Scaffolds baseline files (Scribe-style).
  - Logs all actions to SYSTEM\LOGS\CLERK\clerk.log
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory=$false)]
  [string]$SquadRoot = "C:\Projects\SQUAD",

  [switch]$Init,

  [switch]$Scaffold,

  [switch]$ForceScaffold,

  [string]$InPath,

  [string]$CaseId,

  [switch]$InitGit
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# --------------------------
# Helpers
# --------------------------

function Ensure-Dir {
  param([Parameter(Mandatory=$true)][string]$Dir)
  if (-not (Test-Path -LiteralPath $Dir)) {
    New-Item -ItemType Directory -Path $Dir | Out-Null
  }
}

function Write-ClerkLog {
  param(
    [Parameter(Mandatory=$true)][string]$LogDir,
    [Parameter(Mandatory=$true)][string]$Message,
    [ValidateSet("INFO","WARN","ERROR")][string]$Level="INFO"
  )
  Ensure-Dir $LogDir
  $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
  $line = "[$ts][$Level] $Message"
  $logFile = Join-Path $LogDir "clerk.log"
  Add-Content -LiteralPath $logFile -Value $line -Encoding UTF8
}

function Ensure-File {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [Parameter(Mandatory=$true)][string]$Content,
    [switch]$Force
  )
  $dir = Split-Path -Parent $Path
  Ensure-Dir $dir

  if ((Test-Path -LiteralPath $Path) -and (-not $Force)) {
    return $false
  }

  Set-Content -LiteralPath $Path -Value $Content -Encoding UTF8
  return $true
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

function Get-RouteTarget {
  param(
    [Parameter(Mandatory=$true)][string]$Root,
    [Parameter(Mandatory=$true)][string]$FilePath,
    [string]$CaseId
  )

  $ext = ([System.IO.Path]::GetExtension($FilePath)).ToLowerInvariant()

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

  if ($CaseId -and $CaseId.Trim().Length -gt 0) {
    $caseRoot = Join-Path $Root ("CASES\ACTIVE\" + $CaseId)
    $destBase = Join-Path $caseRoot "ARTIFACTS"
  }

  return $destBase
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

- Modular agent architecture (JSON-first)
- Legal/ethical guardrails
- Case artifacts saved under OUTPUTS\RUNS and CASES\ACTIVE\<caseId>\ARTIFACTS

Use the Clerk to keep structure sane.
"@
    },
    @{
      Path = (Join-Path $Root "SYSTEM\CONFIG\squad.config.json")
      Content = @"
{
  "project": "SQUAD",
  "root": "C:\\\\Projects\\\\SQUAD",
  "version": "0.1.0",
  "ethics": {
    "no_fraud": true,
    "no_impersonation": true,
    "no_medical_or_legal_diagnosis": true
  },
  "case_defaults": {
    "max_actions_per_day": 3,
    "plan_horizon_days": 7
  }
}
"@
    },
    @{
      Path = (Join-Path $Root "AGENTS\PROMPTS\README.md")
      Content = @"
# PROMPTS
Versioned system prompts per agent role.

Rules:
- role-specific
- JSON-output constrained
- minimal drift
"@
    },
    @{
      Path = (Join-Path $Root "AGENTS\SCHEMAS\README.md")
      Content = @"
# SCHEMAS
JSON schemas for each agent output (intake, hunter, strategist, docs, comms, feedback).

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
      Path = (Join-Path $Root "CASES\TEMPLATES\case_template.json")
      Content = @"
{
  "case_id": "CASE_0000",
  "created_utc": null,
  "status": "active",
  "intake": {},
  "benefits": {},
  "strategy": {},
  "docs": {},
  "comms": {},
  "history": []
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
      Path = (Join-Path $Root "DOCS\README.md")
      Content = @"
# DOCS
Project documentation, reference material, checklists, scripts.
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
  "OUTPUTS\EXPORTS"
)

$logDir = Join-Path $SquadRoot "SYSTEM\LOGS\CLERK"

# --------------------------
# INIT
# --------------------------

if ($Init) {
  Ensure-Dir $SquadRoot
  foreach ($d in $dirs) { Ensure-Dir (Join-Path $SquadRoot $d) }

  Write-ClerkLog $logDir "Initialized/verified SQUAD structure at: $SquadRoot" "INFO"

  if ($Scaffold) {
    $count = Scaffold-SquadFiles -Root $SquadRoot -LogDir $logDir -Force:$ForceScaffold
    Write-ClerkLog $logDir "Scaffold complete. Files created/overwritten: $count" "INFO"
  }

  if ($InitGit) {
    if (-not (Test-Path -LiteralPath (Join-Path $SquadRoot ".git"))) {
      Push-Location $SquadRoot
      git init | Out-Null
      Pop-Location
      Write-ClerkLog $logDir "Initialized git repo in: $SquadRoot" "INFO"
    } else {
      Write-ClerkLog $logDir "Git repo already exists in: $SquadRoot" "WARN"
    }
  }
}

# --------------------------
# ROUTE
# --------------------------

if ($InPath) {
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

  foreach ($f in $items) {
    $targetDir = Get-RouteTarget -Root $SquadRoot -FilePath $f.FullName -CaseId $CaseId
    Ensure-Dir $targetDir

    $destPath = Join-Path $targetDir $f.Name

    if (Test-Path -LiteralPath $destPath) {
      $baseName = [System.IO.Path]::GetFileNameWithoutExtension($f.Name)
      $ext = [System.IO.Path]::GetExtension($f.Name)
      $n = 1
      do {
        $destPath = Join-Path $targetDir ("{0}__{1}{2}" -f $baseName, $n, $ext)
        $n++
      } while (Test-Path -LiteralPath $destPath)
    }

    Move-Item -LiteralPath $f.FullName -Destination $destPath
    Write-ClerkLog $logDir ("Moved '{0}' -> '{1}'" -f $f.FullName, $destPath) "INFO"
  }
}

if (-not $Init -and -not $InPath) {
  Write-Host "SQUAD Admin Clerk"
  Write-Host "Examples:"
  Write-Host "  .\Invoke-SquadAdminClerk.ps1 -Init -Scaffold"
  Write-Host "  .\Invoke-SquadAdminClerk.ps1 -Init -Scaffold -ForceScaffold"
  Write-Host "  .\Invoke-SquadAdminClerk.ps1 -Init -InitGit"
  Write-Host "  .\Invoke-SquadAdminClerk.ps1 -InPath C:\Temp\somefile.json"
  Write-Host "  .\Invoke-SquadAdminClerk.ps1 -InPath C:\Temp\CaseStuff -CaseId VET_0001"
}
