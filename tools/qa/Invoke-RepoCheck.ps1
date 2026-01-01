<#!
.SYNOPSIS
  Repo-wide sanity checks (PowerShell parse, JSON parse, Python compile).

.DESCRIPTION
  Runs a minimal, repeatable repo check without writing to OUTPUTS/.
  Designed for PS 5.1 compatibility.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\qa\Invoke-RepoCheck.ps1

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\tools\qa\Invoke-RepoCheck.ps1 -IncludeOutputs
#>

[CmdletBinding()]
param(
  [switch]$IncludeOutputs,
  [int]$MaxFailures = 50,

  # Optional: validate CRA fixtures (schema-only). OFF by default.
  [switch]$ValidateCRA,

  # Phase 5 (opt-in): require explicit confirmation for governed writes
  [switch]$StrictGoverned,

  # Phase 5 (opt-in): explicit operator confirmation for governed changes
  [switch]$ConfirmGoverned
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-RepoRoot {
  $here = Resolve-Path -LiteralPath $PSScriptRoot
  return (Resolve-Path -LiteralPath (Join-Path $here '..\..')).Path
}

function Get-PythonPath([string]$Root) {
  $py = Join-Path $Root '.venv\Scripts\python.exe'
  if (Test-Path -LiteralPath $py) { return $py }

  throw "Python venv not found at: $py"
}

function Invoke-CraFixtureValidation {
  param(
    [Parameter(Mandatory = $true)][string]$Root,
    [Parameter(Mandatory = $true)][string]$PythonPath
  )

  $craValidator = Join-Path $Root 'tools\qa\validate_cra_fixtures.py'
  if (-not (Test-Path -LiteralPath $craValidator)) {
    throw "Missing CRA validator script: $craValidator"
  }

  & $PythonPath $craValidator
  if ($LASTEXITCODE -ne 0) {
    throw 'CRA fixture/schema validation failed (see output above).'
  }
}

function Invoke-Step([string]$Label, [scriptblock]$Action) {
  Write-Host ("[RUN] {0}" -f $Label)
  & $Action
  Write-Host ("[OK ] {0}" -f $Label)
}

$root = Get-RepoRoot
$py = Get-PythonPath -Root $root

# Optional CRA fixture validation enablement (OFF by default)
$craEnabled = $false
if ($ValidateCRA) { $craEnabled = $true }
elseif ($env:SQUAD_VALIDATE_CRA -eq '1') { $craEnabled = $true }

$jsonSweep = Join-Path $root 'tools\qa\json_sweep.py'
$pyCompile = Join-Path $root 'tools\qa\python_compile_sweep.py'
$moduleRegistryCheck = Join-Path $root 'tools\qa\validate_module_registries.py'
$repoIdentityCheck = Join-Path $root 'tools\qa\verify_squad_repo.py'
$changeClassifier = Join-Path $root 'tools\qa\classify_changes.py'
$battlebuddyContractCheck = Join-Path $root 'tools\qa\validate_battlebuddy_contracts.py'

if (-not (Test-Path -LiteralPath $jsonSweep)) { throw "Missing: $jsonSweep" }
if (-not (Test-Path -LiteralPath $pyCompile)) { throw "Missing: $pyCompile" }
if (-not (Test-Path -LiteralPath $moduleRegistryCheck)) { throw "Missing: $moduleRegistryCheck" }
if (-not (Test-Path -LiteralPath $repoIdentityCheck)) { throw "Missing: $repoIdentityCheck" }
if (-not (Test-Path -LiteralPath $changeClassifier)) { throw "Missing: $changeClassifier" }
if (-not (Test-Path -LiteralPath $battlebuddyContractCheck)) { throw "Missing: $battlebuddyContractCheck" }

$skipOutputs = -not $IncludeOutputs

$failures = New-Object System.Collections.Generic.List[object]

# 0) Repo identity / context check (Phase 1: Repo Awareness)
Invoke-Step 'Repo identity (SQUAD)' {
  & $py $repoIdentityCheck
  if ($LASTEXITCODE -ne 0) {
    $failures.Add([pscustomobject]@{ Type = 'repo-identity'; Path = $root; Detail = 'Repo is not recognized as SQUAD (see JSON output above).' })
  }
}

# 0.5) Phase 2: Artifact classification + boundary crossing warnings
Invoke-Step 'Artifact classification (working tree)' {
  if ($StrictGoverned) {
    $args = @('--plain', '--intent', '--require-governed-confirm')
    if ($ConfirmGoverned) { $args += '--confirm-governed' }

    & $py $changeClassifier @args
    if ($LASTEXITCODE -ne 0) {
      $failures.Add([pscustomobject]@{ Type = 'artifact-classification'; Path = $root; Detail = 'Strict governed mode: governed changes require explicit confirmation (--confirm-governed). See output above.' })
    }
  } else {
    & $py $changeClassifier
    if ($LASTEXITCODE -ne 0) {
      $failures.Add([pscustomobject]@{ Type = 'artifact-classification'; Path = $root; Detail = 'Artifact classification reported errors/warnings (see JSON output above).' })
    }
  }
}

# 1) PowerShell parse check
Invoke-Step 'PowerShell parse (.ps1)' {
  $ps1Files = Get-ChildItem -LiteralPath $root -Recurse -Filter *.ps1 -File |
    Where-Object {
      $_.FullName -notmatch '\\\.venv\\' -and
      $_.FullName -notmatch '\\\.git\\' -and
      $_.FullName -notmatch '\\node_modules\\' -and
      (-not $skipOutputs -or $_.FullName -notmatch '\\OUTPUTS\\')
    }

  foreach ($f in $ps1Files) {
    $tokens = $null
    $parseErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile($f.FullName, [ref]$tokens, [ref]$parseErrors)
    if ($parseErrors -and $parseErrors.Count -gt 0) {
      foreach ($e in $parseErrors) {
        $failures.Add([pscustomobject]@{
          Type = 'ps-parse'
          Path = $f.FullName
          Detail = $e.Message
        })
      }
    }
  }
}

# 2) JSON parse sweep (Python)
Invoke-Step 'JSON parse (.json)' {
  $jsonArgs = @(
    $jsonSweep,
    '--root', $root,
    '--max-failures', [string]$MaxFailures
  )
  if ($IncludeOutputs) {
    $jsonArgs += '--include-outputs'
  }

  & $py @jsonArgs
  if ($LASTEXITCODE -ne 0) {
    $failures.Add([pscustomobject]@{ Type = 'json-parse'; Path = $root; Detail = 'One or more JSON files failed to parse (see output above).' })
  }
}

# 2.5) Phase 3: BattleBuddy contract v1 schema-aware validation
Invoke-Step 'BattleBuddy contract validation (v1)' {
  $bbArgs = @(
    $battlebuddyContractCheck,
    '--root', $root,
    '--max-failures', [string]$MaxFailures
  )
  if ($IncludeOutputs) {
    $bbArgs += '--include-outputs'
  }

  & $py @bbArgs
  if ($LASTEXITCODE -ne 0) {
    $failures.Add([pscustomobject]@{ Type = 'bb-contract-schema'; Path = $root; Detail = 'One or more BattleBuddy contract envelopes failed validation (see output above).' })
  }
}

# 3) Python compile sweep
Invoke-Step 'Python compile (.py)' {
  & $py $pyCompile --root $root
  if ($LASTEXITCODE -ne 0) {
    $failures.Add([pscustomobject]@{ Type = 'py-compile'; Path = $root; Detail = 'One or more Python files failed to compile.' })
  }
}

# 4) Module registry entrypoint validation
Invoke-Step 'Module registry entrypoints' {
  & $py $moduleRegistryCheck
  if ($LASTEXITCODE -ne 0) {
    $failures.Add([pscustomobject]@{ Type = 'module-registry'; Path = $root; Detail = 'One or more module registry entrypoints are invalid/missing (see output above).' })
  }
}

# 5) Optional: CRA fixtures (schema-only, deterministic, offline)
if ($craEnabled) {
  Invoke-Step 'CRA fixture validation (optional)' {
    try {
      Invoke-CraFixtureValidation -Root $root -PythonPath $py
    } catch {
      $failures.Add([pscustomobject]@{ Type = 'cra-fixtures'; Path = $root; Detail = $_.Exception.Message })
    }
  }
}

Write-Host ''
Write-Host '=== SUMMARY ==='
Write-Host ("Root: {0}" -f $root)
Write-Host ("Failures: {0}" -f $failures.Count)

if ($failures.Count -gt 0) {
  Write-Host ''
  Write-Host '=== FAILURES (first 50) ==='
  $failures | Select-Object -First 50 | ForEach-Object {
    Write-Host ("{0} :: {1} :: {2}" -f $_.Type, $_.Path, $_.Detail)
  }
  exit 1
}

exit 0
